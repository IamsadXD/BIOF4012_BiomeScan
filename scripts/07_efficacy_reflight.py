#!/usr/bin/env python
"""
STAGE 07 — Post-treatment efficacy verification.
================================================

Deliverable 3, and the one proposal §3.1 calls "the recurring-revenue engine and
the deliverable AFCD currently cannot produce at all."

The measurement loop
--------------------
1. Baseline survey identifies treatment units (stage 06).
2. AFCD treats them — different methods on different severity bands, which is
   what a real programme does.
3. Six months later the same ground is re-flown.
4. Change is measured on the continuous abundance fraction, per unit, against
   each unit's own detection floor.
5. Re-emergence rates aggregate per method, producing the table that answers
   "which clearance methods and which sites are failing?"

The confound this stage refuses to hide
---------------------------------------
Treatments are not randomly assigned: the expensive method goes to the worst
sites. So a naive comparison makes the expensive method look ineffective, when
in fact it was handed the hardest ground. The report states the confound
explicitly and reports severity-stratified rates alongside the raw ones.

Getting this wrong in front of a client who holds the actual treatment records
would be worse than not offering the product.
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
import joblib
from scipy import ndimage

from mikania.change import (apply_treatment_outcome, assign_treatments, change_map,
                            method_summary, minimum_detectable_change, unit_efficacy)
from mikania.config import PATHS, class_ids, load_config, rng, site_table
from mikania.io_hsi import load_cube_npz, save_png, write_geotiff
from mikania.preprocess import brightness_mask, build_feature_stack
from mikania.severity import severity_map, treatment_units
from mikania.simulate import simulate_site
from mikania.spectral_library import apply_season, load_library
from mikania.unmixing import coverage_fraction, unmix_cube

plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 160, "font.size": 8.5,
                     "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white"})


def season_endmembers(lib, cfg, wl, season_key):
    """Season-matched endmember set (see stage 06 for why this is mandatory)."""
    season = cfg["phenology"]["seasons"][season_key]
    em = dict(lib["endmembers"])
    for key in list(em):
        if key in cfg["species_spectra"]:
            em[key] = apply_season(em[key], wl, season,
                                   cfg["phenology"]["flower_reflectance"],
                                   is_target=(key == cfg["confusable_pair"]["target"]))
    return em


def measure_fraction(cube, wl, model, cfg, lib, season_key, ids):
    """Classify + unmix a cube into a Mikania coverage-fraction raster."""
    h, w, _ = cube.shape
    X, _ = build_feature_stack(cube.reshape(h * w, -1), wl, cfg["preprocess"])
    pred = model.predict(X).reshape(h, w).astype(np.uint8)
    valid = brightness_mask(cube, wl, min_reflectance=cfg["preprocess"]["brightness_mask_min"])
    pred = np.where(valid, pred, 0).astype(np.uint8)

    A, rmse = unmix_cube(cube, season_endmembers(lib, cfg, wl, season_key),
                         cfg["unmixing"]["endmembers"],
                         method=cfg["unmixing"]["method"],
                         sum_to_one_weight=cfg["unmixing"]["sum_to_one_weight"],
                         mask=valid)
    frac = coverage_fraction(A, cfg["unmixing"]["endmembers"], target_key="mikania",
                             min_report=cfg["unmixing"]["min_abundance_report"])
    frac = np.nan_to_num(frac, nan=0.0)
    frac = np.where(pred == ids["mikania"], frac, 0.0)
    return pred, frac, valid, float(np.nanmean(rmse))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()
    ids = class_ids(cfg)
    months = args.months or cfg["efficacy"]["reflight_interval_months"]

    bundle = joblib.load(os.path.join(PATHS.models, "operational_model.joblib"))
    model = bundle["model"]
    lib = load_library(os.path.join(PATHS.processed, "spectral_library.npz"))

    val = json.load(open(os.path.join(PATHS.reports, "validation.json"), encoding="utf-8"))
    clf_acc = val["kill_criterion"]["measured_accuracy"]

    outdir = os.path.join(PATHS.outputs, "deliverables")
    os.makedirs(outdir, exist_ok=True)

    print("\nSTAGE 07 — post-treatment efficacy verification")
    print("=" * 78)
    print(f"re-flight interval: {months} months   "
          f"classifier accuracy used for the detection floor: {clf_acc*100:.1f}%")

    all_records, all_units = [], []
    per_site = []

    for i, site in enumerate(site_table(cfg)):
        p = os.path.join(PATHS.processed, "scenes", f"{site['key']}.npz")
        if not os.path.exists(p):
            continue
        base = load_cube_npz(p)
        cube, wl, meta = base["cube"], base["wavelengths"], base["meta"]

        # ---------- epoch 1: baseline, as measured ----------
        pred0, frac0, valid0, rmse0 = measure_fraction(
            cube, wl, model, cfg, lib, meta["season"], ids)
        sev0, comps0 = severity_map(cube, wl, pred0, frac0, cfg, meta)
        units = treatment_units(sev0, frac0, cfg, meta, components=comps0)
        if not units:
            continue

        labels, _ = ndimage.label(frac0 > cfg["unmixing"]["min_abundance_report"])
        assignment = assign_treatments(units, cfg, rng(cfg, offset=800 + i))

        # ---------- treatment applied to the TRUE state ----------
        gen = rng(cfg, offset=850 + i)
        true_frac0 = base["mikania_fraction"]
        true_frac1, treated_mask = apply_treatment_outcome(
            true_frac0, labels, units, assignment, cfg, gen)

        # ---------- epoch 2: re-flight of the same ground ----------
        # Re-simulated from the treated truth, with a fresh noise draw — the
        # re-flight is a genuinely independent acquisition, not the same cube
        # with pixels edited, so measurement error enters both epochs.
        # Layout generator is the SAME as the baseline (offset 300 + i*7, matching
        # stage 03) so the re-flight covers identical ground; only the acquisition
        # generator differs, giving a fresh sun angle and noise realisation.
        scene1 = simulate_site(site, lib, cfg,
                               gen=rng(cfg, offset=300 + i * 7),
                               noise_gen=rng(cfg, offset=900 + i),
                               fraction_override=true_frac1,
                               epoch=f"re-flight +{months}mo")
        pred1, frac1, valid1, rmse1 = measure_fraction(
            scene1["cube"], wl, model, cfg, lib, meta["season"], ids)

        # ---------- change ----------
        floor = minimum_detectable_change(clf_acc, n_pixels=1)
        ch = change_map(frac0, frac1, floor=cfg["unmixing"]["min_abundance_report"])
        records = unit_efficacy(units, frac0, frac1, labels, assignment, clf_acc, cfg)
        for r in records:
            r["site_name"] = site["name"]
        all_records += records
        all_units += units

        geo = meta["geo"]
        stem = os.path.join(outdir, site["key"])
        write_geotiff(stem + "_change.tif", ch["delta"].astype(np.float32), geo,
                      band_descriptions=["delta_coverage_fraction"])
        save_png(stem + "_change.png",
                 plt.get_cmap("RdBu_r")((ch["delta"] + 1) / 2)[:, :, :3])

        n_sig = sum(1 for r in records if r["significant"])
        n_re = sum(1 for r in records if r.get("reemerged"))
        per_site.append({
            "site": site["key"], "name": site["name"], "role": site["role"],
            "n_units": len(records), "n_significant": n_sig, "n_reemerged": n_re,
            "cleared_ha": round(float(ch["cleared"].sum()) *
                                (cfg["scene"]["demo_gsd_m"] ** 2) / 1e4, 3),
            "emerged_ha": round(float(ch["emerged"].sum()) *
                                (cfg["scene"]["demo_gsd_m"] ** 2) / 1e4, 3),
            "treatment_cost_hkd": sum(r["cost_hkd"] for r in records),
        })
        print(f"\n  {site['name']:<30} {len(records):>2} units treated   "
              f"{n_sig:>2} with significant change   {n_re:>2} re-emerged")
        print(f"    cleared {per_site[-1]['cleared_ha']:.3f} ha   "
              f"new/regrowth {per_site[-1]['emerged_ha']:.3f} ha   "
              f"cost HK${per_site[-1]['treatment_cost_hkd']:,}")

    # ------------------------------------------------------------------
    # Per-method aggregation
    # ------------------------------------------------------------------
    summary = method_summary(all_records, cfg)
    print("\n" + "=" * 78)
    print("RE-EMERGENCE BY TREATMENT METHOD")
    print("-" * 78)
    print(f"  {'method':<22} {'units':>6} {'signif':>7} {'re-emerged':>11} "
          f"{'observed rate':>14} {'cost/ha':>9}")
    for m, v in summary["by_method"].items():
        rate = v["observed_reemergence_rate"]
        rate_s = f"{rate*100:.0f}%" if rate is not None else "n/a"
        print(f"  {m:<22} {v['n_units']:>6} {v['n_significant']:>7} "
              f"{v['n_reemerged']:>11} {rate_s:>14} "
              f"HK${v['cost_per_ha_hkd']:>7,}")

    if summary["recommended_order"]:
        print(f"\n  Ranked by measured re-emergence, then cost: "
              f"{' > '.join(summary['recommended_order'])}")

    # The confound, stated rather than buried.
    print("\n  CONFOUND (stated, not corrected away)")
    print("    Treatments were assigned by severity band, not at random: the")
    print("    expensive cut-stump-herbicide method went to the worst units.")
    print("    Comparing raw re-emergence rates therefore penalises it for")
    print("    having been given the hardest ground. A real efficacy contract")
    print("    needs either randomised assignment or severity stratification;")
    print("    the severity-stratified breakdown is in the JSON report.")

    # Severity-stratified rates
    strat = {}
    for r in all_records:
        u = next((x for x in all_units if x["unit_id"] == r["unit_id"]), None)
        if u is None or not r["significant"]:
            continue
        band = u["band"]
        strat.setdefault(r["treatment"], {}).setdefault(band, {"n": 0, "re": 0})
        strat[r["treatment"]][band]["n"] += 1
        strat[r["treatment"]][band]["re"] += int(r["delta"] > 0)

    report = {
        "reflight_interval_months": months,
        "classifier_accuracy_used": clf_acc,
        "per_site": per_site,
        "per_unit": all_records,
        "by_method": summary["by_method"],
        "recommended_order": summary["recommended_order"],
        "severity_stratified": strat,
        "confound_note": (
            "Treatment assignment is severity-driven, not randomised, so raw "
            "per-method rates are confounded with baseline severity. Reported "
            "because that is how a real programme allocates, and flagged because "
            "an unflagged comparison would be misleading."
        ),
        "caveat": (
            "Simulated epochs. What is demonstrated is the measurement loop and "
            "its detection floor, not any real treatment's efficacy."
        ),
    }
    rp = os.path.join(PATHS.reports, "efficacy.json")
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=float)

    # ------------------------------------------------------------------
    # Figure
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))

    methods = [m for m in summary["by_method"] if m != "no_treatment"]
    rates = [(summary["by_method"][m]["observed_reemergence_rate"] or 0) * 100 for m in methods]
    conf = [summary["by_method"][m]["configured_reemergence_rate"] * 100 for m in methods]
    xs = np.arange(len(methods))
    axes[0].bar(xs - 0.19, conf, 0.38, label="true (simulator input)", color="#9aa5b1")
    axes[0].bar(xs + 0.19, rates, 0.38, label="measured by re-flight", color="#1f8a70")
    axes[0].set_xticks(xs)
    axes[0].set_xticklabels([m.replace("_", "\n") for m in methods], fontsize=7)
    axes[0].set(ylabel="re-emergence rate (%)",
                title="What the measurement loop recovers\n(gap = detection limits, not error)")
    axes[0].legend(fontsize=7, frameon=False)

    costs = [summary["by_method"][m]["cost_per_ha_hkd"] / 1000 for m in methods]
    axes[1].scatter(costs, rates, s=90, color="#c0392b", zorder=3)
    for m, c, r in zip(methods, costs, rates):
        axes[1].annotate(m.replace("_", " "), (c, r), fontsize=6.5,
                         xytext=(4, 4), textcoords="offset points")
    axes[1].set(xlabel="cost (HK$ thousand / ha)", ylabel="re-emergence rate (%)",
                title="Cost vs efficacy\n(bottom-left is what AFCD wants)")

    sites_n = [p["name"][:16] for p in per_site]
    cle = [p["cleared_ha"] for p in per_site]
    eme = [p["emerged_ha"] for p in per_site]
    ys = np.arange(len(sites_n))
    axes[2].barh(ys - 0.19, cle, 0.38, color="#1f8a70", label="cleared")
    axes[2].barh(ys + 0.19, eme, 0.38, color="#c0392b", label="re-emerged / new")
    axes[2].set_yticks(ys); axes[2].set_yticklabels(sites_n, fontsize=7)
    axes[2].set(xlabel="hectares", title="Per-site outcome\nafter one treatment cycle")
    axes[2].legend(fontsize=7, frameon=False)

    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig07_efficacy.png"))
    plt.close(fig)

    print(f"\nReport   -> {os.path.relpath(rp, PATHS.root)}")
    print(f"Figure   -> outputs/figures/fig07_efficacy.png")
    print("STAGE 07 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
