#!/usr/bin/env python
"""
STAGE 13 — What label error does, and what certification is worth.
==================================================================

Proposal §9, Risk 9:

    "Training labels corrupted by field misidentification | Critical |
     **High if unaddressed** | Barcode certification gates entry to the training
     set (§3.4). **This risk is severe precisely because it is silent — it
     inflates apparent accuracy while degrading real performance**"

"Silent" and "inflates" are the load-bearing words, and this stage tests both.
**The direction does not survive measurement.** Reporting that is more useful
than confirming it would have been, and it changes what the molecular workstream
should be sold on.

What is measured
----------------
Under site-disjoint validation at the §13.7 rates, label error **depresses** the
apparent Mikania-vs-native figure by ~15 pp while true performance stays near
0.93. The proposal's mechanism needs the model's errors to correlate with the
*validation set's* label errors; under a site-disjoint split they cannot, because
the validation catchment's misidentifications are drawn independently.

A random pixel split is run as well, on the theory that a corrupted patch
straddling the split boundary might be memorised and reproduced. It deflates too:
a mislabelled patch of *Bauhinia* is still spectrally *Bauhinia*, and it is
outvoted by every correctly-labelled *Bauhinia* patch in training.

So Risk 9 is real and severe, and stated backwards. The decision error it causes
is **spurious abandonment**: a programme with uncertified labels reads its own
§7.3 go/no-go test as a near-miss or a failure while the classifier is fine. For
a venture whose Phase 0 is explicitly structured around a kill criterion, that is
the more expensive of the two mistakes — HK$1.4M spent to reach a wrong stop
decision.

Four experiments
----------------
1. **Bias sweep** — error rate crossed with bias, symmetric noise as the control.
2. **Split comparison** — site-disjoint against random pixel split, to test
   whether the inflation appears under the regime §5.1(6) condemns.
3. **Kill-criterion distortion** — masking (Risk 9's prediction) and spurious
   failure (what occurs), both checked.
4. **What certification is worth** — §13.9 costs against avoided wrong clearance.

The corruption unit is a specimen block, not a pixel; see
:func:`mikania.labelerror.corrupt_labels` for why that decision reverses the
result.
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

from mikania.classify import scene_to_samples, stack_samples
from mikania.config import PATHS, load_config, rng, site_table
from mikania.io_hsi import load_cube_npz
from mikania.labelerror import certification_value, propagate_sweep

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

BIASES = (0.5, 0.65, 0.9)
BIAS_COLOR = {0.5: "#7a8894", 0.65: "#d98c1f", 0.9: "#c0392b"}


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=13)

    scenes_dir = os.path.join(PATHS.processed, "scenes")
    parts = []
    for st in site_table(cfg):
        p = os.path.join(scenes_dir, f"{st['key']}.npz")
        if os.path.exists(p):
            parts.append(scene_to_samples(load_cube_npz(p), cfg, gen, max_per_class=900))
    if len(parts) < 2:
        print("!! need at least two simulated scenes — run scripts/03_simulate_scenes.py first")
        return 1
    data = stack_samples(parts)

    print("\nSTAGE 13 — label error propagation (Risk 9, quantified)")
    print("=" * 78)
    print(f"  {data['y'].size} labelled pixels across {len(parts)} sites, "
          f"leave-one-site-out throughout\n")

    sweep = propagate_sweep(data, cfg, gen=gen, biases=BIASES)

    # ---------------- 1. the bias sweep ----------------
    print("  Apparent vs true accuracy on the Mikania-vs-native sub-problem")
    print("  " + "-" * 74)
    for curve in sweep["curves"]:
        print(f"\n  bias = {curve['bias']:.2f}  ({curve['label']})")
        print(f"    {'error rate':>11}{'apparent':>11}{'true':>9}{'app-true':>11}"
              f"{'true FPR':>10}")
        for p in curve["points"]:
            print(f"    {p['rate']:>11.0%}{p['apparent_climber_accuracy']:>11.3f}"
                  f"{p['true_climber_accuracy']:>9.3f}"
                  f"{p['apparent_minus_true_pp']:>+10.1f}pp"
                  f"{p['true_false_positive']:>10.3f}")

    control = next(c for c in sweep["curves"] if abs(c["bias"] - 0.5) < 1e-9)
    worst = max(sweep["curves"], key=lambda c: c["bias"])
    print(f"\n  max(apparent − true): symmetric control "
          f"{control['max_apparent_minus_true_pp']:+.1f} pp, "
          f"biased {worst['bias']:.0%} {worst['max_apparent_minus_true_pp']:+.1f} pp")
    if worst["max_apparent_minus_true_pp"] > 0.5:
        print("  Risk 9's direction is CONFIRMED: biased label error flatters the")
        print("  reportable number while real performance degrades.")
    else:
        print("  Risk 9's direction is NOT confirmed. The gap is negative throughout:")
        print("  corrupted labels make the programme look WORSE than it is, not better.")
        print("  The proposal's own reasoning shows why once stated precisely — the")
        print("  effect needs the model's errors to correlate with the VALIDATION set's")
        print("  label errors, and a site-disjoint split makes that impossible. The")
        print("  next experiment checks the one regime where it could happen.")

    # ---------------- 1b. does the random split produce the inflation? ----
    print("\n  Split comparison — is the inflation hiding in the leaky regime?")
    print("  " + "-" * 74)
    rand = propagate_sweep(data, cfg, gen=gen, biases=(sweep["nominal_bias"],),
                           split="random")
    rc = rand["curves"][0]
    site_pts = {p["rate"]: p for c in sweep["curves"]
                if abs(c["bias"] - sweep["nominal_bias"]) < 1e-9 for p in c["points"]}
    print(f"    {'error rate':>11}{'site-disjoint':>16}{'random split':>16}")
    for p in rc["points"]:
        sp = site_pts.get(p["rate"])
        sv = f"{sp['apparent_minus_true_pp']:+.1f}pp" if sp else "—"
        rv = f"{p['apparent_minus_true_pp']:+.1f}pp"
        print(f"    {p['rate']:>11.0%}{sv:>16}{rv:>16}")
    if rc["max_apparent_minus_true_pp"] > 0.5:
        print("    The inflation appears ONLY under the random pixel split — so Risk 9")
        print("    is real but conditional on the leakage §5.1(6) already condemns.")
    else:
        print("    The inflation does not appear under either split. A mislabelled patch")
        print("    of Bauhinia is still spectrally Bauhinia, and is outvoted by every")
        print("    correctly-labelled Bauhinia patch in training. The model does not")
        print("    learn the surveyor's bias; it overrides it.")

    # ---------------- 2. kill-criterion masking ----------------
    at = sweep["at_nominal"]
    print(f"\n  At the modelled field error rate ({sweep['nominal_rate']:.0%} on sterile")
    print(f"  specimens, bias {sweep['nominal_bias']:.0%}):")
    print(f"    apparent Mikania-vs-native  {at['apparent_climber_accuracy']:.3f}")
    print(f"    true                        {at['true_climber_accuracy']:.3f}")
    print(f"    §7.3 kill criterion         {sweep['kill_threshold']:.2f}")
    print(f"    apparent false positives    {at['apparent_false_positive']:.3f}")
    print(f"    true false positives        {at['true_false_positive']:.3f}"
          f"   (understated by {at['false_positive_understated_pp']:+.1f} pp)")
    if sweep["kill_criterion_masked"]:
        print("\n    !! KILL CRITERION MASKED. An uncertified programme would record a")
        print("       PASS on its own go/no-go test while actually failing it, and no")
        print("       metric available to that programme would reveal the difference.")
    elif sweep["kill_criterion_spuriously_failed"]:
        print("\n    !! KILL CRITERION SPURIOUSLY FAILED. The true classifier clears the")
        print(f"       §7.3 threshold at {at['true_climber_accuracy']:.3f}, but a programme")
        print(f"       scoring against its own uncertified labels reads")
        print(f"       {at['apparent_climber_accuracy']:.3f} and stops the project.")
        print("       HK$1.4M spent to reach a wrong STOP decision — the expensive")
        print("       failure mode for a venture built around a kill criterion, and the")
        print("       opposite of what §9 Risk 9 predicts.")
    else:
        print(f"\n    Verdicts agree at this rate (apparent margin over threshold: "
              f"{sweep['kill_margin_pp']:+.1f} pp), but the margin is thin: the")
        print("    apparent figure is depressed by the labels, not by the classifier.")
        print("    The false-positive understatement is the residual harm, and it lands")
        print("    on native climbers.")

    # ---------------- 3. what certification is worth ----------------
    val = certification_value(sweep, cfg)
    print("\n  Cost of certification vs cost of the errors it prevents")
    print("  " + "-" * 74)
    print(f"    vouchers ({val['n_vouchers']}) at HK${val['cost_per_voucher_hkd']:,}/voucher")
    print(f"    consumables      HK${val['consumables_hkd']:>10,}")
    print(f"    bioinformatics   HK${val['bioinformatics_hkd']:>10,}")
    print(f"    lab access       HK${val['lab_access_hkd']:>10,}")
    print(f"    TOTAL            HK${val['total_certification_cost_hkd']:>10,}"
          f"   (§7.3 line: HK${val['phase0_budget_line_hkd'][0]:,}"
          f"-{val['phase0_budget_line_hkd'][1]:,}"
          f" -> {'within' if val['within_budget_line'] else 'OUTSIDE'})")
    u, c = val["uncertified_programme"], val["certified_programme"]
    print(f"\n    on a {u['programme_area_ha']:,.0f} ha programme:")
    print(f"      uncertified: {u['wrongly_cleared_ha']:.1f} ha of native climber cleared "
          f"-> HK${u['total_cost_hkd']:,}")
    print(f"      certified:   {c['wrongly_cleared_ha']:.1f} ha "
          f"-> HK${c['total_cost_hkd']:,}")
    print(f"      avoided cost HK${val['avoided_cost_hkd_per_year']:,}/yr, "
          f"benefit:cost {val['benefit_cost_ratio']}")
    for cav in val["caveats"]:
        print(f"      caveat: {cav}")

    # ---------------- write ----------------
    out = {"sweep": sweep, "sweep_random_split": rand, "certification_value": val,
           "scope": ("Pixels come from the SIMULATED scenes of stage 03; the label-error "
                     "rates are MODELLED (§13.7). What is demonstrated is the mechanism "
                     "and its sign, not a Hong Kong magnitude. Phase 0 item 4 measures "
                     "the real concordance.")}
    rep = os.path.join(PATHS.reports, "label_error.json")
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=float)

    _figures(sweep, val)
    print(f"\n  Report   -> {os.path.relpath(rep, PATHS.root)}")
    print(f"  Figures  -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig13*.png")
    print("STAGE 13 complete.\n")
    return 0


def _figures(sweep, val) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.4))

    # ---- panel 1: apparent vs true, by bias ----
    ax = axes[0]
    for curve in sweep["curves"]:
        col = BIAS_COLOR.get(curve["bias"], "#333")
        r = [p["rate"] * 100 for p in curve["points"]]
        ax.plot(r, [p["apparent_climber_accuracy"] * 100 for p in curve["points"]],
                "-o", color=col, ms=3.5, lw=1.7,
                label=f"apparent, bias {curve['bias']:.0%}")
        ax.plot(r, [p["true_climber_accuracy"] * 100 for p in curve["points"]],
                "--s", color=col, ms=3.5, lw=1.4, alpha=0.75,
                label=f"true, bias {curve['bias']:.0%}")
    ax.axhline(sweep["kill_threshold"] * 100, color="#c0392b", ls=":", lw=1.3)
    ax.annotate(f"§7.3 kill criterion {sweep['kill_threshold']:.0%}",
                (0.4, sweep["kill_threshold"] * 100 + 1.2), fontsize=7, color="#c0392b")
    ax.set(xlabel="field misidentification rate (%)",
           ylabel="Mikania vs native (balanced acc., %)",
           title="Solid = what you could report\nDashed = what AFCD actually gets")
    ax.annotate("spurious STOP zone:\ntrue passes, apparent fails",
                (0.35, sweep["kill_threshold"] * 100 - 9), fontsize=6.4, color="#c0392b")
    ax.legend(fontsize=6.2, frameon=False, ncol=2, loc="lower left")

    # ---- panel 2: the silent inflation itself ----
    ax = axes[1]
    for curve in sweep["curves"]:
        col = BIAS_COLOR.get(curve["bias"], "#333")
        ax.plot([p["rate"] * 100 for p in curve["points"]],
                [p["apparent_minus_true_pp"] for p in curve["points"]],
                "-o", color=col, ms=4, lw=1.9, label=curve["label"])
    ax.axhline(0, color="#333", lw=0.9)
    ax.set(xlabel="field misidentification rate (%)",
           ylabel="apparent − true (pp)",
           title="apparent − true\nnegative = the programme understates itself")
    ax.legend(fontsize=6.6, frameon=False, loc="upper left")

    # ---- panel 3: cost ----
    ax = axes[2]
    u, c = val["uncertified_programme"], val["certified_programme"]
    labels = ["certification\ncost", "uncertified:\nwrong clearance",
              "certified:\nwrong clearance"]
    vals = [val["total_certification_cost_hkd"] / 1e3,
            u["total_cost_hkd"] / 1e3, c["total_cost_hkd"] / 1e3]
    cols = ["#5b7fbd", "#c0392b", "#1f8a70"]
    ax.bar(range(3), vals, color=cols, edgecolor="white", linewidth=0.7)
    for i, v in enumerate(vals):
        ax.annotate(f"HK${v:,.0f}k", (i, v + max(vals) * 0.025), ha="center", fontsize=7.5)
    ax.set_xticks(range(3))
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set(ylabel="HK$ thousand",
           title=f"Benefit:cost {val['benefit_cost_ratio']}\n"
                 f"on a {u['programme_area_ha']:,.0f} ha programme")
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig13a_label_error.png"))
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
