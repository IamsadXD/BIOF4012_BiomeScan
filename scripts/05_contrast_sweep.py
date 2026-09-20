#!/usr/bin/env python
"""
STAGE 05 — Accuracy as a function of real species separability.
===============================================================

This is the stage that turns the pipeline into a decision tool for the Phase 0
go/no-go, and it exists because of proposal Appendix B.5:

    "Mikania is separable from *Bauhinia glauca* and *Byttneria aspera* in real
     canopy conditions. **This is the central scientific assumption and is
     unproven for Hong Kong.**"

Any single accuracy figure from a simulator is a function of the simulator's own
parameters. Quoting one as though it predicted field performance would be
exactly the inflation the proposal criticises. So instead of asserting a number,
this stage sweeps the underlying unknown — how spectrally distinct the species
actually are — and reports the accuracy CURVE, with the §7.3 kill criterion drawn
across it.

The output answers a question AFCD can actually act on:

    "How separable do these species have to be, in reality, for this to work?"

And correspondingly, what the Phase 0 field spectroradiometer campaign has to
demonstrate before any aerial capital is committed.

Two controls make the curve trustworthy:

* **contrast = 0** — the species are made spectrally identical. Accuracy on the
  Mikania-versus-native sub-problem MUST collapse to chance. If it does not,
  something is leaking and every other number in this study is void.
* **the leakage gap** — the random-split accuracy is tracked alongside at every
  contrast, showing that the inflation is not a one-off artefact.
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

from mikania.classify import (leave_one_site_out, random_split_leakage_demo,
                              scene_to_samples, stack_samples)
from mikania.config import PATHS, load_config, rng, site_table
from mikania.simulate import simulate_site
from mikania.spectral_library import load_library

plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
                     "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white"})


def run_one_contrast(contrast: float, cfg, lib, args) -> dict:
    """Simulate every site at this contrast, then validate leave-one-site-out."""
    parts = []
    for i, site in enumerate(site_table(cfg)):
        gen = rng(cfg, offset=300 + i * 7)          # same seed as stage 03
        scene = simulate_site(site, lib, cfg, gen, contrast=contrast)
        sgen = rng(cfg, offset=500 + i)
        parts.append(scene_to_samples(scene, cfg, sgen, max_per_class=args.max_per_class))

    data = stack_samples(parts)
    gen = rng(cfg, offset=600)
    loso = leave_one_site_out(data, cfg, model_name=args.model, gen=gen)
    leak = random_split_leakage_demo(data, cfg, model_name=args.model)

    return {
        "contrast": contrast,
        "n_pixels": int(data["X"].shape[0]),
        "overall_accuracy": loso["overall_accuracy_ci"],
        "kappa": loso["kappa_ci"],
        "climber_accuracy": loso["climber_balanced_accuracy_ci"],
        "climber_false_positive": loso["climber_false_positive_ci"],
        "random_split_overall": leak["overall_accuracy"],
        "random_split_climber": leak["climber"].get("balanced_accuracy", float("nan")),
        "per_site": {f["held_out_site"]: {
            "overall_accuracy": f["overall_accuracy"],
            "kappa": f["kappa"],
            "climber_accuracy": f["climber"].get("balanced_accuracy"),
        } for f in loso["folds"]},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="plsda", choices=["plsda", "rf", "svm"])
    ap.add_argument("--max-per-class", type=int, default=1100,
                    help="pixels per class per site (lower than stage 04 — this "
                         "runs the whole pipeline once per contrast level)")
    ap.add_argument("--contrasts", default=None,
                    help="comma-separated override of species_contrast.sweep")
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()
    lib = load_library(os.path.join(PATHS.processed, "spectral_library.npz"))

    sweep = ([float(x) for x in args.contrasts.split(",")] if args.contrasts
             else list(cfg["species_contrast"]["sweep"]))

    print("\nSTAGE 05 — accuracy vs true species separability")
    print("=" * 76)
    print(f"model: {args.model}   sites: {len(site_table(cfg))}   "
          f"contrast levels: {sweep}")
    print("\n  contrast   overall acc         Mikania-vs-native      FP     random-split")
    print("  " + "-" * 72)

    rows = []
    for c in sweep:
        r = run_one_contrast(c, cfg, lib, args)
        rows.append(r)
        oa, oal, oah = r["overall_accuracy"]
        cb, cbl, cbh = r["climber_accuracy"]
        print(f"  {c:>6.2f}   {oa*100:5.1f}% [{oal*100:4.1f}-{oah*100:4.1f}]   "
              f"{cb*100:5.1f}% [{cbl*100:4.1f}-{cbh*100:4.1f}]   "
              f"{r['climber_false_positive'][0]*100:4.1f}%   "
              f"{r['random_split_overall']*100:5.1f}%")

    # ------------------------------------------------------------------
    # Control check: contrast 0 must collapse to chance
    # ------------------------------------------------------------------
    zero = next((r for r in rows if abs(r["contrast"]) < 1e-9), None)
    control = {}
    if zero is not None:
        cb = zero["climber_accuracy"][0]
        # Binary sub-problem -> chance is 0.5 for balanced accuracy.
        ok = cb < 0.60
        control = {
            "contrast_zero_climber_accuracy": cb,
            "expected": "~0.50 (chance)",
            "passed": bool(ok),
            "meaning": (
                "At contrast 0 the climber species are spectrally identical, so "
                "any accuracy above chance would indicate the classifier is "
                "exploiting something other than species spectra — spatial "
                "position, illumination or a simulator artefact — and would "
                "invalidate every other figure in this study."
            ),
        }
        print("\n  CONTROL — contrast 0 (species made spectrally identical)")
        print(f"    Mikania-vs-native accuracy = {cb*100:.1f}%   "
              f"expected ~50%   ->  {'PASS' if ok else 'FAIL — INVESTIGATE'}")

    # ------------------------------------------------------------------
    # What contrast is required to pass the kill criterion?
    # ------------------------------------------------------------------
    kc = cfg["kill_criteria"]["mikania_vs_native_min_accuracy"]
    cs = np.array([r["contrast"] for r in rows])
    ca = np.array([r["climber_accuracy"][0] for r in rows])
    cl = np.array([r["climber_accuracy"][1] for r in rows])   # lower CI

    def _crossing(y):
        above = np.where(y >= kc)[0]
        if above.size == 0:
            return None
        i = above[0]
        if i == 0:
            return float(cs[0])
        x0, x1, y0, y1 = cs[i - 1], cs[i], y[i - 1], y[i]
        return float(x0 + (kc - y0) * (x1 - x0) / max(y1 - y0, 1e-9))

    req_mean = _crossing(ca)
    req_conservative = _crossing(cl)

    print(f"\n  Contrast required to reach the {kc*100:.0f}% kill criterion")
    print("  " + "-" * 72)
    print(f"    on the mean estimate            : "
          f"{req_mean if req_mean is not None else 'not reached in sweep'}")
    print(f"    on the lower 95% CI bound       : "
          f"{req_conservative if req_conservative is not None else 'not reached in sweep'}")
    print("\n    Read this as: Phase 0's field spectroradiometer campaign must")
    print("    demonstrate at least this much real spectral contrast between")
    print("    Mikania and the native climbers before aerial capital is committed.")

    report = {
        "model": args.model,
        "sweep": rows,
        "control_contrast_zero": control,
        "kill_criterion": kc,
        "contrast_required_mean": req_mean,
        "contrast_required_lower_ci": req_conservative,
        "interpretation": (
            "Contrast 1.0 is the nominal configuration, in which every species "
            "deviation in config.species_spectra is applied at full strength. "
            "The scale is relative, not physical: it is meaningful for comparing "
            "how much separability is NEEDED against how much Phase 0 MEASURES, "
            "once the same operators are fitted to real field spectra."
        ),
        "caveat": (
            "Simulated scenes throughout. The curve characterises the pipeline's "
            "sensitivity to separability; it does not predict Hong Kong field "
            "accuracy, which remains unmeasured (proposal Appendix B.5)."
        ),
    }
    rp = os.path.join(PATHS.reports, "contrast_sweep.json")
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=float)

    # ------------------------------------------------------------------
    # Figure
    # ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.4))

    ax = axes[0]
    ax.fill_between(cs, [r["climber_accuracy"][1] * 100 for r in rows],
                    [r["climber_accuracy"][2] * 100 for r in rows],
                    color="#1f8a70", alpha=0.16, label="95% CI (over sites)")
    ax.plot(cs, ca * 100, "o-", color="#1f8a70", lw=2, label="leave-one-site-out")
    ax.plot(cs, [r["random_split_climber"] * 100 for r in rows], "s--",
            color="#c0392b", lw=1.4, ms=4, label="random split (leaky)")
    ax.axhline(kc * 100, color="#c0392b", ls="--", lw=1.2)
    ax.annotate(f"§7.3 kill criterion {kc*100:.0f}%", (cs.min(), kc * 100 + 1.5),
                fontsize=7, color="#c0392b")
    ax.axhline(50, color="#888", ls=":", lw=1.0)
    ax.annotate("chance", (cs.min(), 51.4), fontsize=7, color="#888")
    if req_mean is not None:
        ax.axvline(req_mean, color="#4a6fa5", ls="-.", lw=1.2)
        ax.annotate(f"required\ncontrast\n{req_mean:.2f}", (req_mean + 0.04, 56),
                    fontsize=7, color="#4a6fa5")
    ax.set(xlabel="species contrast scale  (1.0 = nominal configuration)",
           ylabel="Mikania vs native climber (balanced acc., %)",
           ylim=(40, 104),
           title="How separable must the species really be?")
    ax.legend(fontsize=7, frameon=False, loc="lower right")

    ax = axes[1]
    for key in sorted(rows[0]["per_site"]):
        ys = [r["per_site"].get(key, {}).get("climber_accuracy") for r in rows]
        ys = [np.nan if v is None else v * 100 for v in ys]
        ax.plot(cs, ys, "o-", lw=1.3, ms=3.5, label=key)
    ax.axhline(kc * 100, color="#c0392b", ls="--", lw=1.2)
    ax.set(xlabel="species contrast scale", ylabel="balanced accuracy (%)",
           ylim=(30, 104),
           title="Per held-out site\n(spread is why 3 sites is not enough)")
    ax.legend(fontsize=6.5, frameon=False, ncol=2)

    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig05_contrast_sweep.png"))
    plt.close(fig)

    print(f"\nReport   -> {os.path.relpath(rp, PATHS.root)}")
    print(f"Figure   -> outputs/figures/fig05_contrast_sweep.png")
    print("STAGE 05 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
