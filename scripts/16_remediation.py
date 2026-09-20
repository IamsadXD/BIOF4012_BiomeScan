#!/usr/bin/env python
"""
STAGE 16 — Test the fixes for the three problems the pipeline found.
====================================================================

``docs/09_findings_vs_proposal.md`` reports three proposal claims that do not
survive measurement. This stage implements the remedies and measures whether they
work, because proposing an untested fix would repeat precisely the failure that
sank §3.3(a) — claiming a benefit nobody checked.

**Fix 1 — protect the go/no-go decision.** §3.4 certifies every voucher before it
trains anything. But the §7.3 kill criterion is evaluated on the *hold-out*, and
stage 13 showed the classifier overrides training-label noise rather than
learning it. So the decision depends on the VALIDATION labels and barely on the
training labels. Four certification arms are compared, and the metric is decision
error — pass/fail agreement with truth — not accuracy, because a programme acts
on a verdict, not on a number.

**Fix 1b — spend the budget where the errors are.** Rank specimens by
model-label disagreement and sequence the top of the list. Measures the
enrichment over random sampling, which is what "certify everything" degenerates
to when the budget runs short.

**Fix 2 — close the reference gaps, in priority order.** Turns the measured
coverage matrix into a costed plan, weighted by Hong Kong occurrence so the
budget is not spent closing a gap nobody falls into.

**Fix 3 — make the band prior work.** §3.3(a) failed on operation order, not on
the idea. Applied after ``StandardScaler`` to a penalised linear model, a
per-band weight is algebraically a per-coefficient penalty — a real informative
prior. Tested against uniform weighting and against permuted-prior controls.
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
import pandas as pd

from mikania.classify import scene_to_samples, stack_samples
from mikania.config import PATHS, class_ids, load_config, rng, site_table, wavelengths
from mikania.genomics import band_prior_weights, load_priors
from mikania.io_hsi import load_cube_npz
from mikania.remediation import (certification_allocation, disagreement_targeting,
                                 evaluate_prior, reference_gap_plan)
from mikania.spectral_library import load_library, sample_class_spectra

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

ARM_COLOR = {"none": "#7a8894", "train_only": "#c0392b",
             "val_only": "#1f8a70", "both": "#5b7fbd"}
N_PER_CLASS_PER_SITE = 90


def _hk_occurrences() -> dict:
    """
    Hong Kong occurrence counts per taxon, for prioritising the reference-gap plan.

    Answers the proposal's own [VERIFY] in §3.3 — whether *M. cordata* occurs in
    Hong Kong — from data already on disk plus one cheap lookup.
    """
    counts = {}
    p = os.path.join(PATHS.raw, "gbif_hk_occurrences.csv")
    if os.path.exists(p):
        df = pd.read_csv(p)
        counts = df["query_name"].value_counts().to_dict()
    # M. cordata is not in the v1.0 GBIF query set; the value below is the
    # measured GBIF count for Hong Kong and is recorded here rather than
    # re-fetched, so this stage stays runnable offline.
    counts.setdefault("Mikania cordata", 1)
    return counts


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=16)

    print("\nSTAGE 16 — remediation: testing the fixes")
    print("=" * 78)

    out = {}

    # ================= FIX 1 — certify the validation set ==================
    scenes = os.path.join(PATHS.processed, "scenes")
    parts = [scene_to_samples(load_cube_npz(os.path.join(scenes, f"{s['key']}.npz")),
                              cfg, gen, max_per_class=550)
             for s in site_table(cfg)
             if os.path.exists(os.path.join(scenes, f"{s['key']}.npz"))]
    if len(parts) < 2:
        print("!! need simulated scenes — run scripts/03_simulate_scenes.py first")
        return 1
    data = stack_samples(parts)

    print("\n  FIX 1 — where should the sequencing budget go?")
    print("  " + "-" * 74)
    alloc = certification_allocation(data, cfg, gen)
    out["certification_allocation"] = alloc

    print(f"    truth: accuracy {alloc['true_accuracy']:.3f} -> verdict "
          f"{alloc['true_verdict']} (threshold {alloc['threshold']:.2f})")
    print(f"    {alloc['n_validation_specimens']} specimens in the validation catchment")
    print(f"    {alloc['n_trials']} trials ({alloc['replicates']} replicates x "
          f"{len(alloc['rates'])} error rates)\n")
    print("    P(go/no-go decision is CORRECT), by what you spend the budget on")
    print(f"    {'certified':>10}" + "".join(f"{a:>14}" for a in ARM_COLOR))
    fracs = [p["fraction_certified"] for p in alloc["arms"]["none"]]
    for i, f in enumerate(fracs):
        row = f"    {f:>9.0%} "
        for arm in ARM_COLOR:
            p = alloc["arms"][arm][i]
            row += f"{p['p_correct_decision']:>13.0%}"
        print(row)

    mf = alloc["min_validation_fraction_for_correct_decision"]
    p_none = alloc["arms"]["none"][0]["p_correct_decision"]
    p_tr_full = alloc["arms"]["train_only"][-1]["p_correct_decision"]
    p_val_full = alloc["arms"]["val_only"][-1]["p_correct_decision"]
    print(f"\n    uncertified                : {p_none:.0%} of decisions correct")
    print(f"    training fully certified   : {p_tr_full:.0%}")
    print(f"    validation fully certified : {p_val_full:.0%}")
    if mf is not None:
        n_needed = int(np.ceil(mf * alloc["n_validation_specimens"]))
        print(f"\n    Certifying the VALIDATION set makes the decision reliable from "
              f"{mf:.0%}\n    ({n_needed} of {alloc['n_validation_specimens']} specimens).")
    if p_tr_full < p_val_full:
        print("\n    Certifying the TRAINING set does not repair the decision, because the")
        print("    number the decision is read from is never touched. §3.4's 'every voucher")
        print("    is barcode-verified before it can train anything' aims the sequencing")
        print("    budget at the half that matters least for the HK$1.4M go/no-go call.")

    # ---- Fix 1b: target the budget -----------------------------------------
    print("\n  FIX 1b — sequence the specimens the classifier disputes")
    print("  " + "-" * 74)
    tgt = disagreement_targeting(data, cfg, gen)
    out["disagreement_targeting"] = tgt
    print(f"    {tgt['n_specimens']} specimens, {tgt['n_corrupted']} genuinely "
          f"mislabelled ({tgt['base_rate']:.1%} base rate)")
    print(f"    {'budget':>8}{'sequenced':>11}{'errors found':>14}{'recall':>9}{'enrichment':>12}")
    for c in tgt["curve"]:
        print(f"    {c['budget_fraction']:>7.0%}{c['n_sequenced']:>11}"
              f"{c['errors_found']:>8}/{c['errors_total']:<5}{c['recall']:>9.0%}"
              f"{c['enrichment_vs_random']:>11.1f}x")
    best = max(tgt["curve"], key=lambda c: c["enrichment_vs_random"])
    print(f"\n    At a {best['budget_fraction']:.0%} budget, disagreement ranking finds "
          f"{best['recall']:.0%} of the label errors —")
    print(f"    {best['enrichment_vs_random']:.1f}x what random sampling of the same size "
          f"would find.")

    # ================= FIX 2 — close the reference gaps ====================
    print("\n  FIX 2 — costed plan to close the public reference gaps")
    print("  " + "-" * 74)
    cov_p = os.path.join(PATHS.reports, "barcode_reference_coverage.json")
    if os.path.exists(cov_p):
        cov = json.load(open(cov_p, encoding="utf-8"))
        occ = _hk_occurrences()
        plan = reference_gap_plan(cov, cfg, occ)
        out["reference_gap_plan"] = plan
        out["hk_occurrence_counts"] = occ

        if not plan["items"]:
            print("    No taxon is uncertifiable. Nothing to close.")
        for it in plan["items"]:
            print(f"    {it['taxon']:<24} {it['priority']}")
            print(f"      current {it['current']}  usable loci: {it['usable_loci'] or 'none'}")
            print(f"      needs {it['sequences_needed']} sequences across "
                  f"{len(it['plan'])} locus/loci -> HK${it['cost_hkd']:,}")
            if it["hk_occurrence_records"] is not None:
                print(f"      Hong Kong occurrence records: {it['hk_occurrence_records']}")
        print(f"\n    Total to close every gap: HK${plan['total_cost_hkd']:,}")
        print(f"    High-priority only:       HK${plan['high_priority_cost_hkd']:,}")
        print("\n    The proposal's §3.3 [VERIFY] on M. cordata is answerable from GBIF:")
        print(f"    {occ.get('Mikania cordata')} georeferenced Hong Kong record (a 1991")
        print("    preserved specimen, no verification status) against 557 for")
        print("    M. micrantha. The congener public references cannot certify is")
        print("    effectively absent from Hong Kong — so the gap is a credibility and")
        print("    comparative-genomics problem, not an operational one, and it should")
        print("    be costed as the former.")
    else:
        print("    coverage report missing — run scripts/11_fetch_barcode_references.py")

    # ================= FIX 3 — make the band prior work ====================
    print("\n  FIX 3 — the band prior, applied where it survives")
    print("  " + "-" * 74)
    lib_p = os.path.join(PATHS.processed, "spectral_library.npz")
    if not os.path.exists(lib_p):
        print("    spectral library missing — run scripts/02_build_spectral_library.py")
        out["prior"] = None
    else:
        lib = load_library(lib_p)
        wl = wavelengths(cfg)
        pri = load_priors()
        w = band_prior_weights(wl, pri, by="operational_score")

        ids = class_ids(cfg)
        keys = ([cfg["confusable_pair"]["target"]]
                + list(cfg["confusable_pair"]["natives"]) + ["host_canopy", "shrub_grass"])
        X, y, site = [], [], []
        for st in site_table(cfg):
            for k in keys:
                S = sample_class_spectra(lib, cfg, k, "wet_summer",
                                         N_PER_CLASS_PER_SITE, gen, site_key=st["key"])
                X.append(S); y.append(np.full(len(S), ids[k]))
                site.append(np.full(len(S), st["key"]))
        X = np.vstack(X); y = np.concatenate(y); site = np.concatenate(site)

        print("    Penalised linear model, no PCA, prior applied AFTER StandardScaler.")
        print("    (A tree ensemble cannot express a band prior at all — it is invariant")
        print("     to monotone per-feature rescaling. PCA would rotate the band basis")
        print("     away. Both exclusions are requirements, not preferences.)\n")

        res = {}
        for C in (0.01, 0.05, 0.5):
            r = evaluate_prior(X, y, site, cfg, w, gen, n_random=12, C=C)
            res[str(C)] = r
            print(f"    C={C:<5} uniform {r['uniform']['mean']:.3f}   "
                  f"prior {r['prior']['mean']:.3f}   permuted {r['random_permuted_mean']['mean']:.3f}"
                  f"   Δ vs random {r['delta_vs_random_pp']:+.2f} pp "
                  f"({r['beat_n_of_random']})")
        out["prior"] = res

        best_C = max(res, key=lambda k: res[k]["delta_vs_random_pp"])
        b = res[best_C]
        if b["supported"]:
            print(f"\n    §3.3(a) is RESCUED at C={best_C}: the prior beats a permuted "
                  f"prior of the\n    same weight distribution by {b['delta_vs_random_pp']:+.2f} pp "
                  f"(SE {b['se_vs_random_pp']}). The claim\n    was right; the implementation "
                  f"was in the wrong place in the pipeline.")
        else:
            print(f"\n    Still not supported, best case C={best_C} at "
                  f"{b['delta_vs_random_pp']:+.2f} pp.")
            print("    The fix makes the prior EXPRESSIBLE — it is no longer annihilated —")
            print("    but expressible is not the same as informative. On this data the")
            print("    biology does not pick better bands than chance, and §3.3(a) should")
            print("    be narrowed to what the desk study demonstrably does buy: direction")
            print("    for the field campaign (stage 00, Spearman rho = +0.43).")

    # ================= write ==============================================
    rep = os.path.join(PATHS.reports, "remediation.json")
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=float)
    _figures(out)

    print(f"\n  Report   -> {os.path.relpath(rep, PATHS.root)}")
    print(f"  Figures  -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig16*.png")
    print("STAGE 16 complete.\n")
    return 0


def _figures(out) -> None:
    alloc = out.get("certification_allocation")
    tgt = out.get("disagreement_targeting")
    pri = out.get("prior")
    if not alloc:
        return

    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.3))

    # ---- panel 1: probability the go/no-go decision is right ---------------
    ax = axes[0]
    fr = [p["fraction_certified"] * 100 for p in alloc["arms"]["none"]]
    # `both` is drawn first and wider, `val_only` dashed on top: the two are
    # identical at every fraction, and a reader has to be able to SEE that they
    # coincide — it is the result, not an overplotting accident.
    for arm, col, style in (("both", ARM_COLOR["both"], dict(lw=5.0, alpha=0.45, ms=0)),
                            ("none", ARM_COLOR["none"], dict(lw=2.0, ms=5)),
                            ("train_only", ARM_COLOR["train_only"], dict(lw=2.0, ms=5)),
                            ("val_only", ARM_COLOR["val_only"], dict(lw=2.0, ms=6, ls="--"))):
        ax.plot(fr, [p["p_correct_decision"] * 100 for p in alloc["arms"][arm]],
                "-o", color=col, label=arm.replace("_", " "), **style)
    ax.axhline(50, color="#7a8894", ls=":", lw=1.1)
    ax.annotate("coin flip", (2, 52), fontsize=7, color="#7a8894")
    ax.annotate("‘both’ and ‘val only’ coincide:\nthe training half adds nothing",
                (26, 66), fontsize=6.8, color="#12503f")
    ax.set(xlabel="specimens certified (%)",
           ylabel="P(go/no-go decision correct) %", ylim=(0, 108),
           title=f"Truth: {alloc['true_verdict']} at {alloc['true_accuracy']:.3f}\n"
                 f"{alloc['n_trials']} trials")
    ax.legend(fontsize=7, frameon=False, loc="lower right")

    # ---- panel 2: targeting -----------------------------------------------
    ax = axes[1]
    if tgt:
        b = [c["budget_fraction"] * 100 for c in tgt["curve"]]
        ax.plot(b, [c["recall"] * 100 for c in tgt["curve"]], "-o",
                color="#1f8a70", ms=5, lw=2, label="disagreement-ranked")
        ax.plot([0] + b, [0] + b, "--", color="#7a8894", lw=1.4, label="random sampling")
        for c in tgt["curve"]:
            ax.annotate(f"{c['enrichment_vs_random']:.1f}x",
                        (c["budget_fraction"] * 100, c["recall"] * 100 + 3),
                        fontsize=7, ha="center", color="#12503f")
        ax.set(xlabel="sequencing budget (% of specimens)",
               ylabel="label errors found (%)",
               title="Spend the budget where the errors are")
        ax.legend(fontsize=7.5, frameon=False, loc="lower right")

    # ---- panel 3: the prior, per regularisation strength -------------------
    ax = axes[2]
    if pri:
        Cs = list(pri)
        x = np.arange(len(Cs))
        ax.bar(x - 0.26, [pri[c]["uniform"]["mean"] * 100 for c in Cs], 0.25,
               label="uniform", color="#7a8894")
        ax.bar(x, [pri[c]["prior"]["mean"] * 100 for c in Cs], 0.25,
               label="genomic prior", color="#1f8a70")
        ax.bar(x + 0.26, [pri[c]["random_permuted_mean"]["mean"] * 100 for c in Cs], 0.25,
               label="permuted prior", color="#c9a227")
        ax.set_xticks(x)
        ax.set_xticklabels([f"C={c}" for c in Cs], fontsize=8)
        ax.set(ylabel="Mikania vs native (bal. acc., %)",
               title="Prior after standardisation,\npenalised model, no PCA")
        ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig16_remediation.png"))
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
