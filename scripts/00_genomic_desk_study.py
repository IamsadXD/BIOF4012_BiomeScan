#!/usr/bin/env python
"""
STAGE 00 — The genomic desk study.
==================================

Proposal §10, Next Action 0:

    "Run the genomic desk study. Analyse the published *M. micrantha* /
     *M. cordata* genomic and transcriptomic resources to produce a ranked,
     falsifiable list of spectral regions predicted to carry species signal
     (§3.3). Zero capital, a few weeks of analyst time, uses only open data, and
     it determines what the field campaign should measure. **This is now the
     true first action** — it should precede item 1 below, and it is the only
     item on this list that can be completed without anyone else's cooperation."

It is stage 00 rather than stage 01 for exactly that reason: it needs no
download, no instrument, no permit and no counterparty. It runs on a laptop on a
plane, and its output determines what the HK$400-500k field-spectroradiometer
campaign in §7.3 is pointed at.

What it produces
----------------
1. ``outputs/reports/genomic_priors.json`` — every prediction, its evidence
   chain back to a cited paper, its two scores, and its falsification test.
2. ``outputs/reports/band_prior_weights.json`` — the per-band weight vector that
   §3.3(a) proposes using instead of blind feature selection.
3. ``outputs/figures/fig00a_prediction_ranking.png`` and ``fig00b_band_priors.png``.

The finding this stage is built to surface
------------------------------------------
Two rankings come out of the same literature, and they disagree sharply. The
prediction best supported by published genomics (the NIR plateau, resting on
directly measured photosynthetic physiology) is close to useless operationally,
because leaf area index, leaf angle and slope move it far more than species
does. The predictions worth measuring are feature *positions*, whose biological
support is thinner.

A desk study reporting only "here is what the genomics says" would send the field
campaign to measure the wrong thing. That divergence is the actual deliverable.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mikania.config import PATHS, load_config, wavelengths
from mikania.genomics import band_prior_weights, desk_study, load_priors

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

# Evidence tiers, coloured by how far they are from a measurement.
TIER_COLOR = {
    "published_genomic": "#1f8a70",
    "published_physiological": "#2e8bc0",
    "published_transcriptomic": "#5b7fbd",
    "inferred_trait": "#d98c1f",
    "inferred_optical": "#c0392b",
}


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    pri = load_priors()
    study = desk_study(pri)

    print("\nSTAGE 00 — genomic desk study (proposal §3.3, Next Action 0)")
    print("=" * 78)
    print(f"  {study['n_findings']} published findings -> {study['n_traits']} inferred "
          f"trait chains -> {study['n_predictions']} spectral predictions")
    print(f"  open data only: {pri['meta']['open_data_only']}   capital required: none\n")

    # ---------------- the ranked table ----------------
    print("  Ranked by OPERATIONAL score (what is worth measuring in the field)")
    print("  " + "-" * 74)
    print(f"  {'#':<3}{'prediction':<28}{'window (nm)':<14}{'bio':>6}{'ops':>7}{'nuis':>7}  sensor")
    for i, p in enumerate(study["ranked_operational"], 1):
        lo, hi = p["window_nm"]
        print(f"  {i:<3}{p['id']:<28}{f'{lo:.0f}-{hi:.0f}':<14}"
              f"{p['biological_score']:>6.3f}{p['operational_score']:>7.3f}"
              f"{p['nuisance_exposure']:>7.2f}  {p['sensor_required']}")

    # ---------------- the divergence ----------------
    print("\n  Where the two rankings disagree most:")
    for d in study["rank_disagreement"][:3]:
        if d["shift"] == 0:
            continue
        arrow = "falls" if d["shift"] < 0 else "rises"
        print(f"    {d['id']:<28} biological #{d['biological_rank']} -> "
              f"operational #{d['operational_rank']}  ({arrow} {abs(d['shift'])} places)")

    worst = min(study["ranked_operational"], key=lambda p: p["operational_score"])
    print(f"\n  {worst['id']} is the worked example: the genomics behind it is as good as "
          f"\n  any in the set, and its operational score is {worst['operational_score']:.3f} "
          f"because nuisance\n  exposure is {worst['nuisance_exposure']:.2f}. Measuring it would "
          f"waste a field season.")

    # ---------------- the honesty check ----------------
    tiers = study["weakest_link_counts"]
    print(f"\n  Weakest link across all chains: {tiers}")
    if set(tiers) == {"inferred_optical"}:
        print("  Every chain terminates in an unmeasured optical inference. That is the")
        print("  Appendix B.8 position and it is not a hedge: no leaf-optical measurement")
        print("  linking these genes to reflectance exists for Hong Kong material.")

    # Biological scores clustering is itself worth stating: if every chain shares
    # the same weakest link, the biological ranking barely discriminates, and it
    # would be a mistake to present it as though it ordered the predictions.
    bios = [p["biological_score"] for p in study["ranked_biological"]]
    spread = max(bios) - min(bios)
    print(f"\n  Biological score spread: {spread:.3f} across {len(bios)} predictions.")
    if spread < 0.10:
        print("  The literature does not tell you WHICH band to measure — only that a")
        print("  mechanism plausibly exists. All discriminating information in the")
        print("  ranking comes from nuisance exposure, i.e. from remote-sensing physics")
        print("  rather than from genomics. Worth saying out loud to a genomics-literate")
        print("  evaluator who might expect the opposite.")

    # ---------------- acquisition constraints ----------------
    print("\n  Acquisition constraints implied by the genomics (not band choices):")
    for a in study["acquisition_constraints"]:
        print(f"    [{a['id']}] {a['constraint']}")
        print(f"           cost consequence: {a['cost_consequence']}")

    # ---------------- band prior weights ----------------
    wl = wavelengths(cfg)
    w_ops = band_prior_weights(wl, pri, by="operational_score")
    w_bio = band_prior_weights(wl, pri, by="biological_score")
    peak = float(wl[int(np.argmax(w_ops))])
    print(f"\n  Band prior weights over {wl[0]:.0f}-{wl[-1]:.0f} nm: peak at {peak:.0f} nm "
          f"(range {w_ops.min():.2f}-{w_ops.max():.2f}, floored so no band is excluded).")

    # ---------------- write reports ----------------
    rep = os.path.join(PATHS.reports, "genomic_priors.json")
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(study, fh, indent=1, default=float)

    bw = os.path.join(PATHS.reports, "band_prior_weights.json")
    with open(bw, "w", encoding="utf-8") as fh:
        json.dump({
            "wavelengths_nm": wl.round(2).tolist(),
            "weights_operational": np.round(w_ops, 5).tolist(),
            "weights_biological": np.round(w_bio, 5).tolist(),
            "peak_nm": peak,
            "floor": 0.25,
            "note": ("Normalised to mean 1.0. No band is ever zero-weighted: the priors "
                     "are hypotheses, and a hard zero would make them unfalsifiable by "
                     "preventing the data from contradicting them. Stage 10 measures "
                     "whether this weighting actually helps."),
        }, fh, indent=1)

    _figures(study, wl, w_ops, w_bio)

    print(f"\n  Report   -> {os.path.relpath(rep, PATHS.root)}")
    print(f"  Weights  -> {os.path.relpath(bw, PATHS.root)}")
    print(f"  Figures  -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig00*.png")
    print("\n  Next: stage 10 tests these predictions against the ground spectral library.")
    print("STAGE 00 complete.\n")
    return 0


def _figures(study, wl, w_ops, w_bio) -> None:
    # ---- fig00a: the two rankings side by side ----------------------------
    preds = study["ranked_operational"]
    names = [p["id"].split("_", 1)[1].replace("_", " ") for p in preds]
    y = np.arange(len(preds))[::-1]

    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.8),
                             gridspec_kw={"width_ratios": [1.25, 1]})

    ax = axes[0]
    ax.barh(y + 0.19, [p["biological_score"] for p in preds], height=0.36,
            color="#5b7fbd", label="biological support (literature)")
    ax.barh(y - 0.19, [p["operational_score"] for p in preds], height=0.36,
            color="#1f8a70", label="operational value (after nuisance)")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set(xlabel="score", title="Best-supported is not most-useful")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    for i, p in enumerate(preds):
        ax.annotate(f"×{1 - p['nuisance_exposure']:.2f}",
                    (p["biological_score"] + 0.006, y[i] + 0.16),
                    fontsize=6.5, color="#888", va="center")

    ax = axes[1]
    shift = [(p["id"], next(d for d in study["rank_disagreement"] if d["id"] == p["id"]))
             for p in preds]
    for pid, d in shift:
        col = "#c0392b" if d["shift"] < 0 else ("#1f8a70" if d["shift"] > 0 else "#888")
        ax.plot([0, 1], [d["biological_rank"], d["operational_rank"]],
                "-o", color=col, lw=1.4, ms=4)
        ax.annotate(pid.split("_", 1)[1].replace("_", " "), (1.03, d["operational_rank"]),
                    fontsize=6.8, va="center", color=col)
    ax.set_xlim(-0.08, 1.9)
    ax.set_ylim(len(preds) + 0.5, 0.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["biological\nrank", "operational\nrank"], fontsize=8)
    ax.set(ylabel="rank (1 = best)", title="Rank shift")
    ax.grid(axis="x", alpha=0)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig00a_prediction_ranking.png"))
    plt.close(fig)

    # ---- fig00b: band prior weights over the sensor range ------------------
    fig, ax = plt.subplots(figsize=(10.4, 4.2))
    for p in study["ranked_operational"]:
        lo, hi = p["window_nm"]
        ax.axvspan(lo, hi, color=TIER_COLOR["inferred_optical"],
                   alpha=0.05 + 0.22 * p["operational_score"] / max(
                       s["operational_score"] for s in study["ranked_operational"]))
    ax.plot(wl, w_ops, lw=2.0, color="#1f8a70", label="operational prior")
    ax.plot(wl, w_bio, lw=1.3, color="#5b7fbd", ls="--", label="biological prior")
    ax.axhline(1.0, color="#666", lw=0.9, ls=":")
    ax.annotate("uniform (no prior)", (408, 1.03), fontsize=7, color="#666")

    top = study["ranked_operational"][0]
    ax.annotate(top["id"].split("_", 1)[1].replace("_", " "),
                (np.mean(top["window_nm"]), w_ops.max() * 0.97),
                fontsize=7.5, ha="center", color="#8a1030")
    ax.set(xlabel="wavelength (nm)", ylabel="prior weight (mean = 1)",
           title="Hypothesis-driven band prioritisation (§3.3a)\n"
                 "shaded = predicted windows, shading depth = operational score")
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig00b_band_priors.png"))
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
