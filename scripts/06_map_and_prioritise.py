#!/usr/bin/env python
"""
STAGE 06 — Produce the deliverables.
====================================

Takes the trained model and turns each scene into the three things proposal §3.1
actually promises AFCD:

**1. Baseline distribution map** — species-level classification, delivered as a
georeferenced GeoTIFF with per-polygon confidence.

**2. Severity-ranked treatment prioritisation** — the abundance product from
spectral unmixing, scored on the five weighted factors, polygonised into ranked
treatment units, exported as GeoJSON with an action column.

**3.** (stage 07 handles post-treatment efficacy.)

The hold-out sites are classified here by a model that never saw them, so the
map quality shown is the map quality a new catchment would actually get.

Outputs per site
----------------
``<site>_classified.tif``   class map, uint8, EPSG:4326
``<site>_abundance.tif``    per-endmember fractions, float32
``<site>_severity.tif``     severity score, float32
``<site>_units.geojson``    ranked treatment units with actions and costs
``<site>_units.csv``        the same table, for anyone who prefers a spreadsheet
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import joblib

from mikania.config import (PATHS, class_colors, class_ids, class_labels, color_lut,
                            load_config, rng, site_table)
from mikania.economics import (coverage_model, programme_cost,
                               proposal_table_consistency_check)
from mikania.io_hsi import (load_cube_npz, rgb_composite, save_png, write_geotiff)
from mikania.preprocess import brightness_mask, build_feature_stack
from mikania.severity import severity_map, treatment_units, units_to_geojson
from mikania.unmixing import coverage_fraction, endmember_condition_report, unmix_cube
from mikania.spectral_library import apply_season, load_library

plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 160, "font.size": 8.5,
                     "figure.facecolor": "white"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unmix-stride", type=int, default=1,
                    help="subsample factor for FCLS unmixing (1 = every pixel)")
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=700)

    bundle = joblib.load(os.path.join(PATHS.models, "operational_model.joblib"))
    model = bundle["model"]
    lib = load_library(os.path.join(PATHS.processed, "spectral_library.npz"))

    ctx_path = os.path.join(PATHS.interim, "site_occurrence_context.json")
    occurrence = json.load(open(ctx_path, encoding="utf-8")) if os.path.exists(ctx_path) else {}

    outdir = os.path.join(PATHS.outputs, "deliverables")
    os.makedirs(outdir, exist_ok=True)

    ids = class_ids(cfg)
    lut = color_lut(cfg)
    em_keys = cfg["unmixing"]["endmembers"]

    print("\nSTAGE 06 — classification, unmixing, severity, prioritisation")
    print("=" * 78)
    print(f"model: {bundle['model_name']}  trained on: {', '.join(bundle['trained_on_sites'])}")

    # The §3.2 band-count argument, quantified.
    cond = endmember_condition_report(lib["endmembers"], em_keys)
    print(f"\nUnmixing conditioning ({cond['n_endmembers']} endmembers)")
    print(f"  {cond['n_bands_hyperspectral']:>3} hyperspectral bands -> condition number "
          f"{cond['condition_hyperspectral']:8.1f}")
    print(f"  {cond['n_bands_multispectral']:>3} multispectral bands -> condition number "
          f"{cond['condition_multispectral']:8.1f}"
          f"   (square system: {'unfalsifiable fit' if not cond['multispectral_overdetermined'] else 'ok'})")

    all_units, summary = [], []
    for site in site_table(cfg):
        p = os.path.join(PATHS.processed, "scenes", f"{site['key']}.npz")
        if not os.path.exists(p):
            continue
        scene = load_cube_npz(p)
        cube, wl, meta = scene["cube"], scene["wavelengths"], scene["meta"]
        gt = scene["gt"]
        h, w, _ = cube.shape
        stem = os.path.join(outdir, site["key"])

        # ---------- classify ----------
        X, _ = build_feature_stack(cube.reshape(h * w, -1), wl, cfg["preprocess"])
        pred = model.predict(X).reshape(h, w).astype(np.uint8)

        # Mask pixels too dark to classify honestly, and say how many.
        valid = brightness_mask(cube, wl, min_reflectance=cfg["preprocess"]["brightness_mask_min"])
        pred_masked = np.where(valid, pred, 0).astype(np.uint8)
        masked_pct = 100.0 * (~valid).mean()

        # ---------- unmix ----------
        # Endmembers MUST be season-matched. The library stores foliage-only
        # means; in the autumn window Mikania carries a 22% white bloom, and
        # unmixing a flowering scene against a non-flowering endmember drives
        # the fitted Mikania abundance toward zero — which is exactly what
        # happened on the first run here (a 13%-infested scene reported 0.24 ha).
        season = cfg["phenology"]["seasons"][meta["season"]]
        em_season = dict(lib["endmembers"])
        for key in em_season:
            if key in cfg["species_spectra"]:
                em_season[key] = apply_season(
                    em_season[key], wl, season,
                    cfg["phenology"]["flower_reflectance"],
                    is_target=(key == cfg["confusable_pair"]["target"]))

        A, rmse = unmix_cube(cube, em_season, em_keys,
                             method=cfg["unmixing"]["method"],
                             sum_to_one_weight=cfg["unmixing"]["sum_to_one_weight"],
                             mask=valid, stride=args.unmix_stride)
        frac = coverage_fraction(A, em_keys, target_key="mikania",
                                 min_report=cfg["unmixing"]["min_abundance_report"])
        frac = np.nan_to_num(frac, nan=0.0)
        # Only claim Mikania where the classifier agrees — abundance alone will
        # put a little "Mikania" almost everywhere, and a prioritisation map full
        # of spurious 12% patches is worse than no map.
        frac = np.where(pred_masked == ids["mikania"], frac, 0.0)

        # ---------- severity ----------
        sev, comps = severity_map(cube, wl, pred_masked, frac, cfg, meta,
                                  occurrence_context=occurrence.get(site["key"]))
        units = treatment_units(sev, frac, cfg, meta, components=comps)

        # ---------- accuracy on this scene (hold-out sites are the honest ones) ----------
        m = valid & (gt > 0)
        acc = float((pred_masked[m] == gt[m]).mean()) if m.any() else float("nan")
        mik_m = m & np.isin(gt, [ids["mikania"]] + [ids[k] for k in cfg["confusable_pair"]["natives"]])
        climber_acc = (float(((pred_masked[mik_m] == ids["mikania"]) ==
                              (gt[mik_m] == ids["mikania"])).mean())
                       if mik_m.any() else float("nan"))

        # ---------- export ----------
        geo = meta["geo"]
        write_geotiff(stem + "_classified.tif", pred_masked, geo, nodata=0,
                      band_descriptions=["class_id"])
        write_geotiff(stem + "_abundance.tif", np.nan_to_num(A, nan=0.0).astype(np.float32),
                      geo, band_descriptions=list(em_keys))
        write_geotiff(stem + "_severity.tif", sev.astype(np.float32), geo,
                      band_descriptions=["severity_0_1"])
        save_png(stem + "_classified.png", lut[pred_masked] / 255.0)
        save_png(stem + "_severity.png",
                 plt.get_cmap("inferno")(sev)[:, :, :3])
        save_png(stem + "_rgb.png", rgb_composite(cube, wl))

        gj = units_to_geojson(units, geo, sev, frac, cfg)
        with open(stem + "_units.geojson", "w", encoding="utf-8") as fh:
            json.dump(gj, fh)
        if units:
            cols = ["rank", "unit_id", "site_name", "area_ha", "severity", "band",
                    "action", "mean_coverage_fraction", "survey_cost_hkd"]
            with open(stem + "_units.csv", "w", newline="", encoding="utf-8") as fh:
                wcsv = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                wcsv.writeheader()
                for u in units:
                    wcsv.writerow(u)

        for u in units:
            u["role"] = site["role"]
        all_units += units

        infested_ha = sum(u["area_ha"] for u in units)
        summary.append({
            "site": site["key"], "name": site["name"], "role": site["role"],
            "season": meta["season_label"],
            "overall_accuracy": acc, "climber_accuracy": climber_acc,
            "masked_pct": masked_pct,
            "n_units": len(units), "infested_ha": infested_ha,
            "urgent_units": sum(1 for u in units if u["band"] == "Urgent"),
            "priority_units": sum(1 for u in units if u["band"] == "Priority"),
            "mean_unmix_rmse": float(np.nanmean(rmse)),
            "subcanopy_occluded_pct": 100 * meta["subcanopy_occluded_fraction"],
        })

        flag = "HOLD-OUT" if site["role"] == "holdout" else "train   "
        print(f"\n  {site['name']:<30} [{flag}]  {meta['season_label']}")
        print(f"    overall acc {acc*100:5.1f}%   Mikania-vs-native {climber_acc*100:5.1f}%   "
              f"masked (too dark) {masked_pct:4.1f}%")
        print(f"    {len(units):>3} treatment units, {infested_ha:6.2f} ha infested   "
              f"unmix RMSE {np.nanmean(rmse):.4f}")

    # ------------------------------------------------------------------
    # Territory-level work plan
    # ------------------------------------------------------------------
    all_units.sort(key=lambda u: -(u["severity"] * u["area_ha"]))
    for i, u in enumerate(all_units, 1):
        u["territory_rank"] = i

    with open(os.path.join(outdir, "work_plan.json"), "w", encoding="utf-8") as fh:
        json.dump({"units": all_units, "site_summary": summary}, fh, indent=2, default=float)

    print("\n" + "=" * 78)
    print("TOP 10 TREATMENT UNITS (the actual work plan)")
    print("-" * 78)
    print(f"  {'#':<3} {'site':<22} {'ha':>6} {'severity':>9}  {'band':<10} action")
    for u in all_units[:10]:
        print(f"  {u['territory_rank']:<3} {u['site_name'][:21]:<22} {u['area_ha']:>6.2f} "
              f"{u['severity']:>9.3f}  {u['band']:<10} {u['action']}")

    bands = {}
    for u in all_units:
        bands.setdefault(u["band"], {"n": 0, "ha": 0.0})
        bands[u["band"]]["n"] += 1
        bands[u["band"]]["ha"] += u["area_ha"]
    print("\n  Work summary by action band")
    for b in cfg["severity"]["bands"]:
        v = bands.get(b["label"], {"n": 0, "ha": 0.0})
        print(f"    {b['label']:<10} {v['n']:>3} units  {v['ha']:>7.2f} ha   {b['action']}")

    # ------------------------------------------------------------------
    # Economics
    # ------------------------------------------------------------------
    cov = coverage_model(cfg)
    print("\n  Coverage economics (proposal §5.3, computed not quoted)")
    print(f"    raw rate       {cov['raw_ha_per_hr']:6.1f} ha/hr   "
          f"(swath {cov['swath_m']:.0f} m x {cov['ground_speed_ms']:.0f} m/s)")
    print(f"    effective rate {cov['effective_ha_per_hr']:6.1f} ha/hr   "
          f"after {cov['sidelap_frac']*100:.0f}% sidelap and "
          f"{cov['operational_efficiency']*100:.0f}% operational efficiency")
    print(f"    field day      {cov['ha_per_field_day']:6.1f} ha/day  "
          f"({cov['hours_per_field_day']:.0f} h operations)")

    chk = proposal_table_consistency_check(cfg)
    print("\n  !! §5.3 table does not reconcile with itself — flagged, not silently patched")
    for d in chk["discrepancies"]:
        print(f"     - {d['item']}: {d['detail']}")
    print(f"     implied operational efficiency to match the stated field day: "
          f"{chk['implied_operational_efficiency_to_match_field_day'][0]:.2f}-"
          f"{chk['implied_operational_efficiency_to_match_field_day'][1]:.2f} "
          f"(config assumes {cfg['platform']['operational_efficiency']:.2f})")
    with open(os.path.join(PATHS.reports, "economics.json"), "w", encoding="utf-8") as fh:
        json.dump({"coverage_model": cov, "consistency_check": chk,
                   "programme_3000ha": programme_cost(3000.0, cfg)}, fh, indent=2, default=float)

    # ------------------------------------------------------------------
    # Figure
    # ------------------------------------------------------------------
    sites = [s for s in site_table(cfg)
             if os.path.exists(os.path.join(PATHS.processed, "scenes", f"{s['key']}.npz"))]
    fig, axes = plt.subplots(3, len(sites), figsize=(3.0 * len(sites), 8.8))
    for j, site in enumerate(sites):
        stem = os.path.join(outdir, site["key"])
        axes[0, j].imshow(plt.imread(stem + "_rgb.png"))
        axes[0, j].set_title(f"{site['name']}\n{site['role']}", fontsize=8)
        axes[1, j].imshow(plt.imread(stem + "_classified.png"))
        axes[2, j].imshow(plt.imread(stem + "_severity.png"))
        for a in axes[:, j]:
            a.set_xticks([]); a.set_yticks([])
    axes[0, 0].set_ylabel("RGB", fontsize=8)
    axes[1, 0].set_ylabel("predicted class", fontsize=8)
    axes[2, 0].set_ylabel("severity", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig06_deliverables.png"), bbox_inches="tight")
    plt.close(fig)

    print(f"\nDeliverables -> {os.path.relpath(outdir, PATHS.root)}/")
    print(f"Figure       -> outputs/figures/fig06_deliverables.png")
    print("STAGE 06 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
