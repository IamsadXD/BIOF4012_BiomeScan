#!/usr/bin/env python
"""
STAGE 03 — Generate the Tier-2 survey scenes.
=============================================

Produces one hyperspectral acquisition per configured catchment (proposal §7.3
Phase 0 / Phase 1 multi-site), in three delivery formats:

* ``.npz``     — internal working format, carries cube + truth + metadata
* ``.hdr/.img``— ENVI, the pushbroom vendor's native format, openable in QGIS,
                 ENVI or SPy by anyone who wants to check our arithmetic
* ``.tif``     — georeferenced RGB quicklook at the site's real HK coordinates

Three sites are flagged ``train`` and two ``holdout``. The holdout sites are
never seen by any model in any stage; they are the only source of a number that
may be quoted externally (proposal §5.1, mitigation 6).

Run with ``--contrast`` to regenerate the whole set at a different species
separability, which is what stage 05's sweep does.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mikania.config import (PATHS, class_colors, class_ids, class_labels, color_lut,
                            load_config, rng, site_table)
from mikania.io_hsi import (geotransform_for_site, rgb_composite, save_cube_npz,
                            save_png, write_envi, write_geotiff)
from mikania.simulate import simulate_site
from mikania.spectral_library import load_library

plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 160, "font.size": 8.5,
                     "figure.facecolor": "white"})


def scene_dir(cfg) -> str:
    return os.path.join(PATHS.processed, "scenes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contrast", type=float, default=None,
                    help="override species_contrast.scale (default: config value)")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--no-envi", action="store_true", help="skip ENVI export")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()
    lib = load_library(os.path.join(PATHS.processed, "spectral_library.npz"))
    outdir = args.outdir or scene_dir(cfg)
    os.makedirs(outdir, exist_ok=True)

    contrast = args.contrast if args.contrast is not None else cfg["species_contrast"]["scale"]
    ids = class_ids(cfg)
    lut = color_lut(cfg)

    if not args.quiet:
        print("\nSTAGE 03 — simulating Tier-2 acquisitions")
        print("=" * 74)
        print(f"contrast scale = {contrast:.2f}   "
              f"({cfg['scene']['lines']}x{cfg['scene']['samples']} px, "
              f"{len(lib['wavelengths'])} bands)")

    manifest = []
    for i, site in enumerate(site_table(cfg)):
        gen = rng(cfg, offset=300 + i * 7)
        scene = simulate_site(site, lib, cfg, gen, contrast=contrast)
        meta = scene["meta"]

        geo = geotransform_for_site(site["centroid"], scene["gt"].shape,
                                    cfg["scene"]["demo_gsd_m"])
        meta["geo"] = geo

        stem = os.path.join(outdir, f"{site['key']}")
        save_cube_npz(stem + ".npz", scene["cube"], scene["wavelengths"],
                      gt=scene["gt"], meta=meta,
                      mikania_fraction=scene["mikania_fraction"],
                      occluded=scene["occluded"].astype(np.uint8),
                      gt_full=scene["gt_full"])

        if not args.no_envi:
            write_envi(stem + ".hdr", scene["cube"], scene["wavelengths"],
                       description=f"{site['name']} — simulated Tier-2 VNIR ({meta['season_label']})")

        # Deliverable-format exports: georeferenced RGB + class map.
        rgb = rgb_composite(scene["cube"], scene["wavelengths"])
        write_geotiff(stem + "_rgb.tif", (rgb * 255).astype(np.uint8), geo,
                      band_descriptions=["red_660nm", "green_550nm", "blue_470nm"])
        write_geotiff(stem + "_truth.tif", scene["gt"], geo, nodata=0,
                      band_descriptions=["class_id"])
        save_png(stem + "_rgb.png", rgb)
        save_png(stem + "_truth.png", lut[scene["gt"]] / 255.0)

        manifest.append({
            "site": site["key"], "name": site["name"], "role": site["role"],
            "season": meta["season"], "npz": os.path.relpath(stem + ".npz", PATHS.root),
            "mikania_pct": 100 * meta["mikania_prevalence_observed"],
            "occluded_pct": 100 * meta["subcanopy_occluded_fraction"],
            "shadow_pct": 100 * meta["shadow_fraction"],
        })

        if not args.quiet:
            print(f"  {site['name']:<30} {site['role']:<8} {meta['season_label']:<20} "
                  f"Mikania {100*meta['mikania_prevalence_observed']:5.1f}%  "
                  f"occluded {100*meta['subcanopy_occluded_fraction']:4.1f}%  "
                  f"shadow {100*meta['shadow_fraction']:4.1f}%")

    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"contrast_scale": contrast, "scenes": manifest}, fh, indent=2)

    # ------------------------------------------------------------------
    # Overview figure
    # ------------------------------------------------------------------
    if not args.quiet:
        sites = site_table(cfg)
        fig, axes = plt.subplots(3, len(sites), figsize=(3.0 * len(sites), 8.6))
        labels = class_labels(cfg)
        for j, site in enumerate(sites):
            z = np.load(os.path.join(outdir, f"{site['key']}.npz"))
            cube, gt = z["cube"], z["gt"]
            frac = z["mikania_fraction"]
            wl = z["wavelengths"]

            axes[0, j].imshow(rgb_composite(cube, wl))
            axes[0, j].set_title(f"{site['name']}\n{site['role']} · "
                                 f"{cfg['phenology']['seasons'][site['season']]['label']}",
                                 fontsize=8)
            axes[1, j].imshow(lut[gt])
            im = axes[2, j].imshow(frac, cmap="inferno", vmin=0, vmax=1)
            for a in axes[:, j]:
                a.set_xticks([]); a.set_yticks([])
        axes[0, 0].set_ylabel("RGB composite", fontsize=8)
        axes[1, 0].set_ylabel("class truth", fontsize=8)
        axes[2, 0].set_ylabel("Mikania fraction", fontsize=8)
        fig.colorbar(im, ax=axes[2, :].tolist(), fraction=0.02, pad=0.01)

        handles = [plt.Rectangle((0, 0), 1, 1, color=np.array(lut[c]) / 255.0)
                   for c in sorted(labels) if c != 0]
        fig.legend(handles, [labels[c] for c in sorted(labels) if c != 0],
                   loc="lower center", ncol=8, fontsize=7, frameon=False,
                   bbox_to_anchor=(0.5, -0.005))
        fig.savefig(os.path.join(PATHS.figures, "fig03_scenes.png"),
                    bbox_inches="tight")
        plt.close(fig)

        print(f"\nScenes   -> {os.path.relpath(outdir, PATHS.root)}/")
        print(f"Figure   -> outputs/figures/fig03_scenes.png")
        print("STAGE 03 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
