#!/usr/bin/env python
"""
STAGE 10 — Falsify the genomic predictions against measured spectra.
====================================================================

Stage 00 produced eight ranked, signed, falsifiable predictions from the
published genomics. This stage tries to break them.

Proposal §3.2, on the mechanism table those predictions come from:

    "The 'candidate molecular basis' column states hypotheses, not established
     leaf-optical measurements ... Phase 0's ground spectral library is what
     converts each row from hypothesis to measurement, and **rows that fail
     should be struck rather than quietly retained.**"

Two experiments
---------------
**1. Direct falsification, in two seasons.** Each prediction's named feature is
measured on Mikania and on native climbers, site-blocked, once with the autumn
bloom present and once on foliage only.

Running both is not thoroughness for its own sake — it is the test of constraint
A2, which stage 00 derived from the genomics before any spectrum was measured:

    "A constitutive photosystem signal should be measured OUT of the flowering
     window to be worth anything ... Measuring in bloom and inferring the rest
     would be assuming the conclusion."

If A2 is right, predictions grounded in constitutive photosystem architecture
should behave differently in the two seasons, and the in-bloom measurement should
be the misleading one. That is a prediction about the *experiment*, made in
advance, and it is checked here.

**2. Does the prior actually help the classifier?** §3.3(a) claims biology-informed
band prioritisation beats blind feature selection on a small training set. The
first version of this experiment applied the prior as per-band feature weights
and measured **exactly zero** effect — because every sensible pipeline puts a
``StandardScaler`` in front of the model, and standardising each band to unit
variance annihilates any constant per-band weight applied beforehand. Random
forests are additionally invariant to monotone per-feature rescaling, so the
result was doubly void.

That is a real methodological catch and §3.3(a) glosses over it: "we can weight
and interrogate the regions the biology predicts" is not implementable as a
weight. A prior over bands has to enter as **selection** — which bands are
retained — and that is what is tested here, against a random-subset control of
identical size.

Scope
-----
The spectra come from the stage-02 library, whose species contrasts are
**modelled** (config §3, swept in stage 05) on top of a real measured leaf base.
This stage validates the falsification machinery and shows the shape of the
Phase 0 deliverable. It establishes nothing about Hong Kong material.
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

from mikania.classify import make_model
from mikania.config import (PATHS, class_ids, load_config, rng, site_table, wavelengths)
from mikania.genomics import (NOT_SUPPORTED, REFUTED, SUPPORTED, UNDERPOWERED,
                              band_prior_weights, evaluate_predictions, load_priors)
from mikania.spectral_library import load_library, sample_class_spectra

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

VERDICT_COLOR = {SUPPORTED: "#1f8a70", NOT_SUPPORTED: "#d98c1f",
                 REFUTED: "#c0392b", UNDERPOWERED: "#7a8894"}

# Phase 0 sample size per class per site. Deliberately small: §5.1(7) puts this
# project in the p >> n regime ("the number of independent field samples will be
# in the hundreds at best"), and that is the regime where a prior either helps or
# does not. Testing with 5,000 samples per class would answer a question nobody
# is asking.
N_PER_CLASS_PER_SITE = 90

# Bands retained by each selection scheme in experiment 2. One third of 121 is
# aggressive enough to matter and leaves enough spectrum to be a fair test.
K_BANDS = 40
N_RANDOM_DRAWS = 12          # the random-subset control is averaged over draws

FOLIAGE_SEASON = "wet_summer"
BLOOM_SEASON = "autumn_flower"


def _ranks(a: np.ndarray) -> np.ndarray:
    """Ranks for a Spearman correlation, averaging ties."""
    order = np.argsort(a)
    r = np.empty_like(order, dtype=float)
    r[order] = np.arange(a.size, dtype=float)
    for v in np.unique(a):
        m = a == v
        if m.sum() > 1:
            r[m] = r[m].mean()
    return r


def _draw(cfg, lib, gen, season_key, n=N_PER_CLASS_PER_SITE):
    """
    Sample spectra for every vegetation class at every site, in one season.

    The season is imposed on *all* sites rather than taken from the site table.
    The config assigns each catchment a different season so that stage 04 is
    forced to confront classifier drift; here that would confound season with
    site and make the two-season comparison uninterpretable. Holding season
    constant across sites is what lets the site-blocked effect sizes be compared
    between panels.
    """
    ids = class_ids(cfg)
    keys = ([cfg["confusable_pair"]["target"]] + list(cfg["confusable_pair"]["natives"])
            + ["host_canopy", "shrub_grass"])

    X, y, site = [], [], []
    for st in site_table(cfg):
        for k in keys:
            S = sample_class_spectra(lib, cfg, k, season_key, n, gen, site_key=st["key"])
            X.append(S)
            y.append(np.full(len(S), ids[k]))
            site.append(np.full(len(S), st["key"]))
    return np.vstack(X), np.concatenate(y), np.concatenate(site)


def _falsify(cfg, lib, gen, pri, season_key):
    """Run every prediction's falsification test in one season."""
    X, y, site = _draw(cfg, lib, gen, season_key)
    ids = class_ids(cfg)
    tgt = ids[cfg["confusable_pair"]["target"]]
    nat = [ids[k] for k in cfg["confusable_pair"]["natives"]]
    mt, mn = y == tgt, np.isin(y, nat)
    res = evaluate_predictions(X[mt], X[mn], wavelengths(cfg), pri,
                               site_target=site[mt], site_native=site[mn])
    return res, (X, y, site)


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    pri = load_priors()
    gen = rng(cfg, offset=10)
    wl = wavelengths(cfg)

    lib_p = os.path.join(PATHS.processed, "spectral_library.npz")
    if not os.path.exists(lib_p):
        print("!! spectral_library.npz missing — run scripts/02_build_spectral_library.py first")
        return 1
    lib = load_library(lib_p)

    print("\nSTAGE 10 — falsifying the §3.3 genomic predictions")
    print("=" * 78)

    # ================= experiment 1: falsification, two seasons ============
    foliage, (Xf, yf, sitef) = _falsify(cfg, lib, gen, pri, FOLIAGE_SEASON)
    bloom, _ = _falsify(cfg, lib, gen, pri, BLOOM_SEASON)
    bloom_by_id = {r["id"]: r for r in bloom}

    print(f"  {len(set(sitef.tolist()))} sites, {N_PER_CLASS_PER_SITE} spectra per class "
          f"per site, site-blocked effect sizes\n")
    print("  Constraint A2 (stage 00) says the constitutive signal must be measured")
    print("  OUT of bloom. Both seasons are therefore run, and A2 is itself on trial.\n")
    print("  " + "-" * 74)
    print(f"  {'prediction':<26}{'pred':<10}{'d foliage':>11}{'d in-bloom':>12}  verdict (foliage)")

    def _d(v):
        return "—" if v is None else f"{v:+.2f}"

    for r in foliage:
        b = bloom_by_id[r["id"]]
        print(f"  {r['id']:<26}{r['direction']:<10}"
              f"{_d(r['test']['cohens_d_site_blocked']):>11}"
              f"{_d(b['test']['cohens_d_site_blocked']):>12}"
              f"  {r['test']['verdict']}")

    counts = {v: sum(1 for r in foliage if r["test"]["verdict"] == v)
              for v in (SUPPORTED, NOT_SUPPORTED, REFUTED, UNDERPOWERED)}
    print(f"\n  Foliage-only season: {counts[SUPPORTED]} supported, "
          f"{counts[NOT_SUPPORTED]} not supported, {counts[REFUTED]} refuted, "
          f"{counts[UNDERPOWERED]} underpowered")

    struck = [r["id"] for r in foliage if r["test"]["verdict"] == REFUTED]
    if struck:
        print(f"  STRIKE from the §3.2 mechanism table: {', '.join(struck)}")

    # ---- A2 on trial: how many verdicts does the bloom change? ------------
    flipped = [(r["id"], r["test"]["verdict"], bloom_by_id[r["id"]]["test"]["verdict"])
               for r in foliage
               if r["test"]["verdict"] != bloom_by_id[r["id"]]["test"]["verdict"]]
    sign_flips = [r["id"] for r in foliage
                  if (r["test"]["cohens_d_site_blocked"] or 0)
                  * (bloom_by_id[r["id"]]["test"]["cohens_d_site_blocked"] or 0) < 0]

    print(f"\n  A2 verdict: {len(flipped)} of {len(foliage)} predictions change verdict "
          f"between seasons,")
    print(f"  and {len(sign_flips)} reverse the SIGN of their effect: "
          f"{', '.join(sign_flips) if sign_flips else 'none'}")
    if sign_flips:
        print("  The autumn bloom adds a bright, spectrally flat floral component that")
        print("  fills the red absorption well and lifts the NIR plateau. Features built")
        print("  on those two quantities inherit the flower rather than the photosystem.")
        print("  Stage 00 derived this constraint from the genomics BEFORE any spectrum")
        print("  was measured; measuring in bloom alone would have produced confident,")
        print("  wrongly-signed conclusions about a constitutive trait.")

    # ---- was the desk study's RANKING worth anything? --------------------
    # The single most useful thing to know about stage 00: did its ordering
    # predict which effects turn out to be measurable? A desk study that ranks
    # predictions no better than alphabetically has cost a few weeks and bought
    # nothing, and that is a cheap thing to check.
    ops_rank = np.array([r["operational_score"] for r in foliage])
    obs_eff = np.array([abs(r["test"]["cohens_d_site_blocked"] or 0.0) for r in foliage])
    rho = float(np.corrcoef(_ranks(ops_rank), _ranks(obs_eff))[0, 1]) if len(foliage) > 2 else float("nan")
    top = max(foliage, key=lambda r: r["operational_score"])
    print(f"\n  Did the stage-00 ranking predict measurability?")
    print(f"    Spearman rho(operational score, |observed d|) = {rho:+.2f} over "
          f"{len(foliage)} predictions")
    print(f"    top-ranked prediction {top['id']} -> "
          f"d = {top['test']['cohens_d_site_blocked']:+.2f} ({top['test']['verdict']})")
    if rho > 0.3:
        print("    The ranking carries real information: the predictions the desk study")
        print("    said were worth measuring are the ones with measurable effects.")
    else:
        print("    The ranking carries little information about measurability on this")
        print("    data. Its defensible value is the evidence chain and the falsification")
        print("    specification, not the ordering.")

    # ================= experiment 2: does the prior help? ==================
    print(f"\n  Testing §3.3(a): does the prior select better bands than chance?")
    print("  " + "-" * 74)
    print("  NOTE: applying the prior as per-band WEIGHTS measures exactly zero effect —")
    print("  StandardScaler restores unit variance per band and annihilates it, and RF is")
    print("  invariant to monotone rescaling anyway. A band prior has to enter as")
    print("  SELECTION. §3.3(a)'s wording ('weight and interrogate') is not implementable.")

    w_ops = band_prior_weights(wl, pri, by="operational_score")
    prior_bands = np.argsort(w_ops)[::-1][:K_BANDS]
    even_bands = np.linspace(0, wl.size - 1, K_BANDS).round().astype(int)

    ids = class_ids(cfg)
    tgt = ids[cfg["confusable_pair"]["target"]]
    nat = [ids[k] for k in cfg["confusable_pair"]["natives"]]
    sites = sorted(set(sitef.tolist()))

    def _loso(Xsub):
        """Leave-one-site-out balanced accuracy on the Mikania-vs-native sub-problem."""
        out = []
        for s in sites:
            te = sitef == s
            model = make_model("rf", cfg)
            model.fit(Xsub[~te], yf[~te])
            pred = model.predict(Xsub[te])
            m = np.isin(yf[te], [tgt] + nat)
            if not m.any():
                continue
            t = (yf[te][m] == tgt).astype(int)
            p = (pred[m] == tgt).astype(int)
            tp = int(((p == 1) & (t == 1)).sum()); fn = int(((p == 0) & (t == 1)).sum())
            fp = int(((p == 1) & (t == 0)).sum()); tn = int(((p == 0) & (t == 0)).sum())
            out.append(0.5 * (tp / max(tp + fn, 1) + tn / max(tn + fp, 1)))
        return np.asarray(out)

    bench = {}
    bench["all_bands"] = {"per_site": _loso(Xf).round(4).tolist(), "k": int(wl.size)}
    bench["prior_topk"] = {"per_site": _loso(Xf[:, prior_bands]).round(4).tolist(), "k": K_BANDS}
    bench["evenly_spaced"] = {"per_site": _loso(Xf[:, even_bands]).round(4).tolist(), "k": K_BANDS}

    rgen = np.random.default_rng(cfg["project"]["random_seed"] + 101)
    draws = [_loso(Xf[:, rgen.choice(wl.size, K_BANDS, replace=False)])
             for _ in range(N_RANDOM_DRAWS)]
    bench["random_topk"] = {
        "per_site": np.mean(draws, axis=0).round(4).tolist(), "k": K_BANDS,
        "n_draws": N_RANDOM_DRAWS,
        "draw_means": [round(float(d.mean()), 4) for d in draws],
    }

    for name, b in bench.items():
        arr = np.asarray(b["per_site"])
        b["mean"], b["sd"] = round(float(arr.mean()), 4), round(float(arr.std()), 4)
        print(f"  {name:<16} k={b['k']:>3}   {b['mean']:.3f} ± {b['sd']:.3f}")

    paired = (np.asarray(bench["prior_topk"]["per_site"])
              - np.asarray(bench["random_topk"]["per_site"]))
    delta_pp = 100.0 * float(paired.mean())
    se_pp = 100.0 * float(np.std(paired, ddof=1) / np.sqrt(paired.size)) if paired.size > 1 else float("nan")
    helps = bool(delta_pp > 0 and np.isfinite(se_pp) and delta_pp > 2 * se_pp)

    print(f"\n  prior-selected vs random-selected ({K_BANDS} bands each): "
          f"{delta_pp:+.2f} pp ± {se_pp:.2f} (SE, paired over {paired.size} sites)")
    beat_random_draws = sum(
        1 for m in bench["random_topk"]["draw_means"] if bench["prior_topk"]["mean"] > m)
    print(f"  the prior beat {beat_random_draws}/{N_RANDOM_DRAWS} individual random draws")
    if helps:
        print("  §3.3(a) holds when implemented as SELECTION: the biology picks better")
        print("  bands than chance at Phase 0 sample sizes.")
    else:
        print("  §3.3(a) is NOT supported on this data even as selection. Reported as")
        print("  measured. The prior's demonstrated value is in directing the field")
        print("  campaign (stage 00), not in classifier performance — and the proposal")
        print("  should make that narrower claim.")

    # ---------------- report ----------------
    out = {
        "scope": (
            "Species contrasts in the stage-02 library are MODELLED (config §3) on a real "
            "measured leaf base, and are swept in stage 05. This stage validates the "
            "falsification machinery and shows the form of the Phase 0 deliverable. It "
            "establishes nothing about Hong Kong material."),
        "n_sites": len(sites),
        "n_per_class_per_site": N_PER_CLASS_PER_SITE,
        "foliage_season": FOLIAGE_SEASON,
        "bloom_season": BLOOM_SEASON,
        "predictions_foliage": foliage,
        "predictions_bloom": bloom,
        "verdict_counts_foliage": counts,
        "struck_rows": struck,
        "verdict_changes_between_seasons": [
            {"id": i, "foliage": f, "bloom": b} for i, f, b in flipped],
        "sign_reversals_between_seasons": sign_flips,
        "constraint_a2_supported": bool(sign_flips),
        "ranking_vs_measurability_spearman": round(rho, 4),
        "ranking_informative": bool(rho > 0.3),
        "band_selection": {
            "k": K_BANDS,
            "prior_band_nm": wl[np.sort(prior_bands)].round(1).tolist(),
            "benchmark": bench,
            "delta_vs_random_pp": round(delta_pp, 3),
            "se_pp": round(se_pp, 3),
            "claim_supported": helps,
            "weighting_note": (
                "Applying the prior as per-band feature WEIGHTS produces exactly zero "
                "effect: StandardScaler restores unit variance per band, and tree "
                "ensembles are invariant to monotone per-feature rescaling. §3.3(a) is "
                "only implementable as band selection."),
        },
    }
    rep = os.path.join(PATHS.reports, "genomic_validation.json")
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=float)

    _figures(foliage, bloom_by_id, bench, wl, w_ops, prior_bands)

    print(f"\n  Report   -> {os.path.relpath(rep, PATHS.root)}")
    print(f"  Figures  -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig10*.png")
    print("STAGE 10 complete.\n")
    return 0


def _figures(foliage, bloom_by_id, bench, wl, w_ops, prior_bands) -> None:
    # ---- fig10a: predicted direction vs measured effect, both seasons ------
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.0),
                             gridspec_kw={"width_ratios": [1.5, 1]})

    ax = axes[0]
    names = [r["id"].split("_", 1)[1].replace("_", " ") for r in foliage]
    yv = np.arange(len(foliage))[::-1]
    df = [r["test"]["cohens_d_site_blocked"] or 0.0 for r in foliage]
    db = [bloom_by_id[r["id"]]["test"]["cohens_d_site_blocked"] or 0.0 for r in foliage]
    cols = [VERDICT_COLOR[r["test"]["verdict"]] for r in foliage]

    ax.barh(yv, df, height=0.56, color=cols, label="foliage only (the A2 measurement)")
    ax.scatter(db, yv, s=26, marker="D", facecolor="none", edgecolor="#333",
               lw=1.1, zorder=3, label="in bloom")
    for i, r in enumerate(foliage):
        if df[i] * db[i] < 0:
            ax.plot([df[i], db[i]], [yv[i], yv[i]], color="#333", lw=0.7, ls=":", zorder=2)
        d = r["direction"]
        if d != "two_sided":
            ax.annotate("pred " + ("+" if d == "positive" else "−"),
                        (0.06 if df[i] < 0 else -0.06, yv[i]), fontsize=6.3,
                        color="#666", va="center", ha="left" if df[i] < 0 else "right")
    ax.axvline(0, color="#333", lw=0.9)
    for x in (-0.3, 0.3):
        ax.axvline(x, color="#bbb", ls=":", lw=0.9)
    ax.set_yticks(yv)
    ax.set_yticklabels(names, fontsize=8)
    ax.set(xlabel="Cohen's d  (Mikania − native climber), site-blocked",
           title="Each prediction, tested in two seasons\n"
                 "dotted link = the bloom reverses the sign")
    # Bar colour encodes the verdict, so the key has to be on the same axes as
    # the bars — a reader should not have to consult the report to decode it.
    seen = [v for v in (SUPPORTED, NOT_SUPPORTED, REFUTED, UNDERPOWERED)
            if any(r["test"]["verdict"] == v for r in foliage)]
    handles = ([plt.Rectangle((0, 0), 1, 1, color=VERDICT_COLOR[v]) for v in seen]
               + ax.get_legend_handles_labels()[0])
    labels = [v.replace("_", " ").lower() for v in seen] + ax.get_legend_handles_labels()[1]
    ax.legend(handles, labels, fontsize=6.6, frameon=False, loc="lower right", ncol=2)

    ax = axes[1]
    order = ["all_bands", "prior_topk", "evenly_spaced", "random_topk"]
    labels = ["all 121\nbands", f"prior top {bench['prior_topk']['k']}",
              "evenly\nspaced", "random\n(mean of draws)"]
    vals = [bench[k]["mean"] * 100 for k in order]
    errs = [bench[k]["sd"] * 100 for k in order]
    ax.bar(range(4), vals, yerr=errs, capsize=4,
           color=["#7a8894", "#1f8a70", "#5b7fbd", "#c9a227"],
           edgecolor="white", linewidth=0.6)
    for m in bench["random_topk"]["draw_means"]:
        ax.plot([3.32], [m * 100], "o", ms=3, color="#7a5f00", alpha=0.55)
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set(ylabel="Mikania vs native (balanced acc., %)",
           ylim=(min(vals) - 10, max(vals) + 7),
           title="Band SELECTION, not weighting\n(weighting measures exactly zero)")
    for i, v in enumerate(vals):
        ax.annotate(f"{v:.1f}", (i, v + 1.1), ha="center", fontsize=7.5)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig10a_prediction_tests.png"))
    plt.close(fig)

    # ---- fig10b: which bands the prior actually selects --------------------
    fig, ax = plt.subplots(figsize=(10.2, 3.6))
    ax.plot(wl, w_ops, lw=1.8, color="#1f8a70", label="operational prior weight")
    ax.axhline(1.0, color="#666", ls=":", lw=1.0)
    sel = np.zeros_like(wl, dtype=bool)
    sel[prior_bands] = True
    ax.scatter(wl[sel], np.full(sel.sum(), w_ops.max() * 1.06), marker="|", s=90,
               color="#c0392b", label=f"selected ({sel.sum()} bands)")
    ax.annotate("uniform", (405, 1.04), fontsize=7, color="#666")
    ax.set(xlabel="wavelength (nm)", ylabel="prior weight (mean = 1)",
           ylim=(0, w_ops.max() * 1.18),
           title="Which bands the genomics says to keep")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig10b_band_selection.png"))
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
