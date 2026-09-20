#!/usr/bin/env python
"""
STAGE 15 — Assemble the platform data bundle.
=============================================

The web platform is deliberately a *static consumer* of pipeline outputs: it
reads one JSON bundle plus a folder of PNG layers, and computes nothing
scientific of its own. That separation matters. A dashboard that recomputes
metrics in JavaScript is a second implementation nobody validates, and the two
will disagree the day before a client meeting.

Everything the UI shows therefore traces to a file written by stages 00-14, and
the bundle records which stage produced each block so the provenance chain
survives into the browser.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from mikania.config import (PATHS, class_table, load_config, site_table, wavelengths)
from mikania.economics import (coverage_model, phase0_budget_check,
                               proposal_table_consistency_check, revenue_model,
                               three_tier_funnel)
from mikania.io_hsi import load_cube_npz
from mikania.spectral_library import load_library

UI_DATA = os.path.join(PATHS.root, "platform", "ui", "data")
UI_LAYERS = os.path.join(UI_DATA, "layers")


def _read_json(path, default=None):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default if default is not None else {}


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    os.makedirs(UI_LAYERS, exist_ok=True)

    print("\nSTAGE 15 — assembling platform bundle")
    print("=" * 68)

    reports = PATHS.reports
    deliv = os.path.join(PATHS.outputs, "deliverables")

    bundle = {
        "project": {
            "name": cfg["project"]["name"],
            "subtitle": cfg["project"]["subtitle"],
            "phase": cfg["project"]["phase"],
            "seed": cfg["project"]["random_seed"],
        },
        "classes": class_table(cfg),
        "wavelengths": wavelengths(cfg).round(2).tolist(),
        "sensor": cfg["sensor"],
        "platform": cfg["platform"],
        "severity_bands": cfg["severity"]["bands"],
        "severity_weights": cfg["severity"]["weights"],
        "kill_criteria": cfg["kill_criteria"],
        "economics_config": cfg["economics"],
    }

    # ---------- spectral library ----------
    lib_p = os.path.join(PATHS.processed, "spectral_library.npz")
    if os.path.exists(lib_p):
        lib = load_library(lib_p)
        bundle["library"] = {
            "endmembers": {k: np.asarray(v).round(5).tolist()
                           for k, v in lib["endmembers"].items()},
            "provenance": lib.get("per_endmember", {}),
            "measured_sources": lib.get("measured_sources", []),
            "n_measured_spectra": lib.get("n_measured_spectra", 0),
            # A thinned sample of the real measured bank, for the "these are real
            # leaves" panel. Full bank is 242 x 121 and would bloat the bundle.
            "measured_sample": np.asarray(lib["measured_bank"])[::6].round(4).tolist(),
        }
        print(f"  library      {len(lib['endmembers'])} endmembers, "
              f"{lib.get('n_measured_spectra', 0)} measured spectra")

    # ---------- reports ----------
    # The molecular block (v2.0) is loaded on the same footing as the spectral
    # one: a missing report degrades a view rather than breaking the build, so an
    # evaluator who ran only the spectral stages still gets a working platform.
    for key, fname in [
        ("separability", "separability.json"),
        ("validation", "validation.json"),
        ("contrast_sweep", "contrast_sweep.json"),
        ("efficacy", "efficacy.json"),
        ("benchmark", "benchmark_botswana.json"),
        ("genomic_priors", "genomic_priors.json"),
        ("genomic_validation", "genomic_validation.json"),
        ("band_prior_weights", "band_prior_weights.json"),
        ("barcode_coverage", "barcode_reference_coverage.json"),
        ("barcode_verification", "barcode_verification.json"),
        ("label_error", "label_error.json"),
        ("reference_database", "reference_database.json"),
        ("remediation", "remediation.json"),
    ]:
        bundle[key] = _read_json(os.path.join(reports, fname))
        print(f"  {key:<20} {'ok' if bundle[key] else 'MISSING'}")

    # The certificate list is large and only its decision fields are displayed;
    # the per-locus hit dumps stay in outputs/reports for auditing.
    bv = bundle.get("barcode_verification") or {}
    if bv.get("certificates"):
        keep = ("voucher_id", "status", "certified_taxon", "certified_class",
                "true_taxon", "true_class", "field_call", "sterile", "site_key",
                "season", "confidence", "loci_used", "n_loci_agreeing", "reasons",
                "correct", "proposed_taxon", "n_loci_attempted")
        bv["certificates"] = [{k: c.get(k) for k in keep} for c in bv["certificates"]]
    bundle["molecular_config"] = {
        "loci": cfg["molecular"]["loci"],
        "identification": cfg["molecular"]["identification"],
        "release": cfg["molecular"]["release"],
        "qc": cfg["molecular"]["qc"],
        "field_error": cfg["molecular"]["field_error"],
        "voucher_plan": cfg["molecular"]["voucher_plan"],
        "deposition": cfg["molecular"]["deposition"],
        "costs_hkd": cfg["molecular"]["costs_hkd"],
    }
    bundle["reference_database_config"] = cfg["reference_database"]

    # ---------- economics, recomputed here so the UI never has to ----------
    bundle["economics"] = {
        "coverage": coverage_model(cfg),
        "funnel": three_tier_funnel(cfg),
        "revenue": revenue_model(cfg),
        "phase0": phase0_budget_check(cfg),
        "consistency_check": proposal_table_consistency_check(cfg),
    }

    # ---------- sites, layers, work plan ----------
    work = _read_json(os.path.join(deliv, "work_plan.json"), {"units": [], "site_summary": []})
    bundle["work_plan"] = work.get("units", [])
    summary_by_site = {s["site"]: s for s in work.get("site_summary", [])}

    occ = _read_json(os.path.join(PATHS.interim, "site_occurrence_context.json"))

    sites = []
    for site in site_table(cfg):
        npz = os.path.join(PATHS.processed, "scenes", f"{site['key']}.npz")
        if not os.path.exists(npz):
            continue
        scene = load_cube_npz(npz)
        meta = scene["meta"]

        layers = {}
        for tag, src in [
            ("rgb", f"{site['key']}_rgb.png"),
            ("truth", None),
            ("classified", f"{site['key']}_classified.png"),
            ("severity", f"{site['key']}_severity.png"),
            ("change", f"{site['key']}_change.png"),
        ]:
            if src is None:
                src = f"{site['key']}_truth.png"
                srcpath = os.path.join(PATHS.processed, "scenes", src)
            else:
                srcpath = os.path.join(deliv, src)
            if os.path.exists(srcpath):
                shutil.copy(srcpath, os.path.join(UI_LAYERS, src))
                layers[tag] = f"data/layers/{src}"

        # A coarse spectral sample so the browser can draw pixel spectra without
        # shipping the full 220 x 200 x 121 cube. Step 10 gives a 22 x 20 grid
        # per site — one probe every ~16 m on the ground, which is ample for an
        # interactive explorer and keeps the whole bundle near 2 MB instead of
        # 33 MB. Three decimals is well below the sensor's noise floor, so the
        # rounding discards nothing real.
        cube = scene["cube"]
        step = 10
        sub = cube[::step, ::step, :].astype(np.float32)

        sites.append({
            **{k: site[k] for k in ("key", "name", "role", "centroid", "area_ha",
                                     "mikania_prevalence", "season")},
            "season_label": meta["season_label"],
            "geo": meta["geo"],
            "shape": [int(cube.shape[0]), int(cube.shape[1])],
            "spectra_grid": {
                "step": step,
                "shape": [int(sub.shape[0]), int(sub.shape[1])],
                "data": np.round(sub, 3).ravel().tolist(),
            },
            "layers": layers,
            "metrics": summary_by_site.get(site["key"], {}),
            "occurrence": occ.get(site["key"], {}),
            "occluded_pct": 100 * meta["subcanopy_occluded_fraction"],
            "limitation_note": meta["limitation_note"],
        })
        print(f"  site         {site['name']:<30} layers: {', '.join(layers)}")

    bundle["sites"] = sites

    # ---------- real GBIF occurrences for the territory map ----------
    gbif_p = os.path.join(PATHS.raw, "gbif_hk_occurrences.csv")
    if os.path.exists(gbif_p):
        df = pd.read_csv(gbif_p)
        bundle["occurrences"] = {
            "n": int(len(df)),
            "source": "GBIF.org occurrence search, Hong Kong, coordinate uncertainty <= 1 km",
            "points": [
                {"lat": round(float(r.lat), 5), "lon": round(float(r.lon), 5),
                 "cls": str(r.class_key), "year": int(r.year) if pd.notna(r.year) else None}
                for r in df.itertuples()
            ],
            "by_taxon": df["query_name"].value_counts().to_dict(),
        }
        print(f"  occurrences  {len(df)} real GBIF records")

    bundle["provenance"] = _read_json(os.path.join(PATHS.raw, "PROVENANCE.json"), [])

    out = os.path.join(UI_DATA, "bundle.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, separators=(",", ":"), default=float)

    size_mb = os.path.getsize(out) / 1e6
    print(f"\nBundle -> {os.path.relpath(out, PATHS.root)}  ({size_mb:.2f} MB)")
    print("STAGE 15 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
