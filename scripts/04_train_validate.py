#!/usr/bin/env python
"""
STAGE 04 — Train, and validate the only way that counts.
========================================================

Produces the numbers that would go in front of AFCD:

1. **Model comparison** — PLS-DA vs Random Forest vs SVM, all under
   leave-one-SITE-out cross-validation, with bootstrap confidence intervals
   computed over sites rather than pixels.
2. **The leakage demonstration** — the same model under a random pixel split,
   to quantify how much that (very common) mistake inflates the result.
3. **The kill-criterion check** — proposal §7.3: Mikania-versus-native-climber
   accuracy below ~75%, or a false positive rate above the configured ceiling,
   means the operational value proposition does not hold.
4. **The trained operational model**, fitted on the training sites only and
   saved for stages 05-07.

Nothing here is tuned against the hold-out sites. Tai Po Kau and Sai Kung West
are touched exactly once, at the end, by ``--final-holdout``.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import joblib

from mikania.classify import (leave_one_site_out, make_model,
                              random_split_leakage_demo, scene_to_samples,
                              stack_samples, full_metrics)
from mikania.config import (PATHS, class_labels, load_config, rng, site_table)
from mikania.io_hsi import load_cube_npz

plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
                     "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white"})


def load_scenes(cfg, roles=("train", "holdout")):
    out = []
    for site in site_table(cfg):
        if site["role"] not in roles:
            continue
        p = os.path.join(PATHS.processed, "scenes", f"{site['key']}.npz")
        if os.path.exists(p):
            out.append(load_cube_npz(p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-per-class", type=int, default=1800)
    ap.add_argument("--models", default="plsda,rf,svm")
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=400)

    print("\nSTAGE 04 — training and site-disjoint validation")
    print("=" * 74)

    # ------------------------------------------------------------------
    # Dataset: TRAINING sites only. Hold-outs are not loaded here at all.
    # ------------------------------------------------------------------
    train_scenes = load_scenes(cfg, roles=("train",))
    if not train_scenes:
        print("No scenes found. Run scripts/03_simulate_scenes.py first.")
        return 1

    parts = [scene_to_samples(s, cfg, gen, max_per_class=args.max_per_class)
             for s in train_scenes]
    data = stack_samples(parts)
    print(f"\nTraining pool: {data['X'].shape[0]:,} pixels x {data['X'].shape[1]} features "
          f"from {len(train_scenes)} sites")
    print(f"  sites: {', '.join(sorted(set(data['groups'].tolist())))}")

    # ------------------------------------------------------------------
    # Model comparison under leave-one-site-out
    # ------------------------------------------------------------------
    print("\nLeave-one-SITE-out cross-validation (the reportable number)")
    print("-" * 74)
    print(f"  {'model':<8} {'overall acc':<22} {'kappa':<20} {'Mikania vs native':<22} {'FP rate'}")

    results = {}
    for name in args.models.split(","):
        name = name.strip()
        r = leave_one_site_out(data, cfg, model_name=name, gen=gen)
        results[name] = r
        oa, oal, oah = r["overall_accuracy_ci"]
        kp, kpl, kph = r["kappa_ci"]
        cb, cbl, cbh = r["climber_balanced_accuracy_ci"]
        fp, fpl, fph = r["climber_false_positive_ci"]
        print(f"  {name:<8} {oa*100:5.1f}% [{oal*100:4.1f}-{oah*100:4.1f}]   "
              f"{kp:5.3f} [{kpl:5.3f}-{kph:5.3f}]  "
              f"{cb*100:5.1f}% [{cbl*100:4.1f}-{cbh*100:4.1f}]   {fp*100:5.1f}%")

    best_name = max(results, key=lambda k: results[k]["climber_balanced_accuracy_ci"][0])
    best = results[best_name]
    print(f"\n  best on the Mikania-vs-native sub-problem: {best_name}")

    # ------------------------------------------------------------------
    # Leakage demonstration
    # ------------------------------------------------------------------
    leak = random_split_leakage_demo(data, cfg, model_name=best_name)
    loso_oa = best["overall_accuracy_ci"][0]
    inflation = (leak["overall_accuracy"] - loso_oa) * 100
    print("\nWhat a random pixel split would have reported instead")
    print("-" * 74)
    print(f"  random split (WRONG)     overall {leak['overall_accuracy']*100:5.1f}%   "
          f"kappa {leak['kappa']:.3f}")
    print(f"  leave-one-site-out       overall {loso_oa*100:5.1f}%   "
          f"kappa {best['kappa_ci'][0]:.3f}")
    print(f"  inflation from leakage   {inflation:+5.1f} percentage points")

    # ------------------------------------------------------------------
    # Kill criterion
    # ------------------------------------------------------------------
    kc = cfg["kill_criteria"]
    cb = best["climber_balanced_accuracy_ci"][0]
    cbl = best["climber_balanced_accuracy_ci"][1]
    fp = best["climber_false_positive_ci"][0]
    acc_pass = cb >= kc["mikania_vs_native_min_accuracy"]
    fp_pass = fp <= kc["max_false_positive_rate"]

    print("\nKILL CRITERION (proposal §7.3)")
    print("-" * 74)
    print(f"  Mikania vs native climber accuracy >= {kc['mikania_vs_native_min_accuracy']*100:.0f}%   "
          f"measured {cb*100:.1f}%  ->  {'PASS' if acc_pass else 'FAIL'}")
    print(f"  false positive rate <= {kc['max_false_positive_rate']*100:.0f}%                "
          f"measured {fp*100:.1f}%  ->  {'PASS' if fp_pass else 'FAIL'}")
    if not (acc_pass and fp_pass):
        print("  VERDICT: at this species contrast the operational value proposition")
        print("           does not hold. See stage 05 for the accuracy-vs-contrast")
        print("           curve and what field separability would be required.")
    else:
        print("  VERDICT: criteria met at the simulated species contrast.")
    print("  NOTE: measured on SIMULATED scenes. The real value of this number is")
    print("        the machinery that produced it, not the number itself.")

    # ------------------------------------------------------------------
    # Fit the operational model on all training sites, save it
    # ------------------------------------------------------------------
    model = make_model(best_name, cfg)
    model.fit(data["X"], data["y"])
    model_path = os.path.join(PATHS.models, "operational_model.joblib")
    joblib.dump({
        "model": model, "model_name": best_name,
        "feature_names": data["feature_names"].tolist(),
        "trained_on_sites": sorted(set(data["groups"].tolist())),
        "preprocess": cfg["preprocess"],
        "contrast_scale": cfg["species_contrast"]["scale"],
    }, model_path)
    print(f"\nOperational model ({best_name}) -> {os.path.relpath(model_path, PATHS.root)}")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    def strip(r):
        """Drop the out-of-fold arrays before JSON serialisation."""
        return {k: v for k, v in r.items() if k != "oof"}

    report = {
        "models": {k: strip(v) for k, v in results.items()},
        "best_model": best_name,
        "leakage_demo": leak,
        "leakage_inflation_pp": inflation,
        "kill_criterion": {
            "threshold_accuracy": kc["mikania_vs_native_min_accuracy"],
            "threshold_false_positive": kc["max_false_positive_rate"],
            "measured_accuracy": cb,
            "measured_accuracy_lower_ci": cbl,
            "measured_false_positive": fp,
            "accuracy_pass": bool(acc_pass),
            "false_positive_pass": bool(fp_pass),
            "verdict": "PASS" if (acc_pass and fp_pass) else "FAIL",
        },
        "caveat": (
            "All figures are from SIMULATED scenes at species contrast "
            f"{cfg['species_contrast']['scale']}. They validate the pipeline and the "
            "validation methodology, not Hong Kong field separability, which is "
            "unmeasured (proposal Appendix B.5) and is what Phase 0 buys."
        ),
    }
    rp = os.path.join(PATHS.reports, "validation.json")
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=float)

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------
    labels = class_labels(cfg)
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.3))

    # (a) model comparison
    names = list(results)
    xs = np.arange(len(names))
    for k, (metric, lab, col) in enumerate([
            ("overall_accuracy_ci", "overall accuracy", "#4a6fa5"),
            ("climber_balanced_accuracy_ci", "Mikania vs native", "#1f8a70")]):
        vals = [results[n][metric][0] * 100 for n in names]
        lo = [results[n][metric][0] * 100 - results[n][metric][1] * 100 for n in names]
        hi = [results[n][metric][2] * 100 - results[n][metric][0] * 100 for n in names]
        axes[0].bar(xs + (k - 0.5) * 0.36, vals, 0.36, yerr=[lo, hi], capsize=4,
                    label=lab, color=col, edgecolor="white")
    axes[0].axhline(kc["mikania_vs_native_min_accuracy"] * 100, color="#c0392b", ls="--", lw=1.2)
    axes[0].annotate("§7.3 kill criterion", (-0.45, kc["mikania_vs_native_min_accuracy"] * 100 + 1.5),
                     fontsize=7, color="#c0392b")
    axes[0].set_xticks(xs); axes[0].set_xticklabels(names)
    axes[0].set(ylabel="%", ylim=(0, 105),
                title="Leave-one-site-out\n(95% CI bootstrapped over sites)")
    axes[0].legend(fontsize=7, frameon=False, loc="lower right")

    # (b) leakage
    axes[1].bar([0, 1], [leak["overall_accuracy"] * 100, loso_oa * 100],
                color=["#c0392b", "#1f8a70"], width=0.55, edgecolor="white")
    axes[1].set_xticks([0, 1])
    axes[1].set_xticklabels(["random pixel split\n(what most papers do)",
                             "leave-one-site-out\n(what we report)"], fontsize=8)
    axes[1].annotate(f"{inflation:+.1f} pp", (0.5, max(leak["overall_accuracy"] * 100, loso_oa * 100) + 3),
                     ha="center", fontsize=10, color="#c0392b", fontweight="bold")
    axes[1].set(ylabel="overall accuracy (%)", ylim=(0, 108),
                title="Spatial autocorrelation leakage\n(proposal §5.1 mitigation 6)")

    # (c) confusion matrix of the best model, pooled over folds
    cm = np.array(best["pooled"]["confusion_matrix"], dtype=float)
    cmn = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    im = axes[2].imshow(cmn, cmap="Greens", vmin=0, vmax=1)
    ticks = best["pooled"]["confusion_labels"]
    axes[2].set_xticks(range(len(ticks))); axes[2].set_yticks(range(len(ticks)))
    axes[2].set_xticklabels(ticks, rotation=45, ha="right", fontsize=6.5)
    axes[2].set_yticklabels(ticks, fontsize=6.5)
    for i in range(cmn.shape[0]):
        for j in range(cmn.shape[1]):
            if cmn[i, j] > 0.01:
                axes[2].text(j, i, f"{cmn[i,j]*100:.0f}", ha="center", va="center",
                             fontsize=6, color="white" if cmn[i, j] > 0.5 else "#222")
    axes[2].set(title=f"{best_name.upper()} pooled confusion\n(row-normalised %, out-of-fold)",
                xlabel="predicted", ylabel="true")
    axes[2].grid(False)
    fig.colorbar(im, ax=axes[2], fraction=0.046)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig04_validation.png"))
    plt.close(fig)

    print(f"Report   -> {os.path.relpath(rp, PATHS.root)}")
    print(f"Figure   -> outputs/figures/fig04_validation.png")
    print("STAGE 04 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
