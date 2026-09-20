#!/usr/bin/env python
"""
STAGE 02 — Build the spectral library and test separability *before* flying.
============================================================================

This stage is the whole logic of proposal §5.1, mitigation (1): the ground
spectral library resolves the central scientific risk (Risk 2, "Mikania not
separable from native climbers") at a fraction of the cost of aerial
acquisition, and it does so before any capital commitment.

What it produces
----------------
1. ``data/processed/spectral_library.npz`` — endmembers, the real measured leaf
   bank, and the variance modes stage 03 draws from.
2. A **separability audit**: for every named feature, the normalised distance
   d' between Mikania and each native climber. This is where the proposal's
   central claim gets tested rather than asserted.
3. ``outputs/figures/fig02_*.png`` — the library plot, the derivative plot that
   shows where the discrimination lives, and the broadband-vs-narrowband bar
   chart that reproduces the published negative result.
4. ``outputs/reports/separability.json`` — machine-readable, consumed by the
   platform.

The headline output is the reproduction of the negative result: the six RGB
indices that published UAV work found could not separate Mikania from its host
plants should score d' well below the narrow-band features. If they do not, our
moat argument is weaker than the proposal claims and we need to know now.
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

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import (GroupKFold, StratifiedKFold, cross_val_predict,
                                     cross_val_score)

from mikania.config import PATHS, class_colors, class_ids, load_config, rng, wavelengths
from mikania.features import (SENSOR_TIERS, interpretable_features, sensor_requirement,
                              separability, tier_feature_matrix)
from mikania.preprocess import savgol
from mikania.spectral_library import build_library, sample_class_spectra, save_library

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

# Colours for the three sensor tiers, shared with the web platform.
TIER_COLOR = {"rgb": "#c0392b", "multispectral": "#d98c1f", "hyperspectral": "#1f8a70"}
TIER_LABEL = {
    "rgb": "RGB camera",
    "multispectral": "5-band multispectral",
    "hyperspectral": "hyperspectral only",
}


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=2)
    wl = wavelengths(cfg)

    print("\nSTAGE 02 — spectral library and pre-flight separability audit")
    print("=" * 68)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    lib = build_library(cfg)
    out = save_library(lib, os.path.join(PATHS.processed, "spectral_library.npz"))
    print(f"\nMeasured base: {lib['n_measured_spectra']} real leaf spectra "
          f"resampled to {wl.size} bands @ {cfg['sensor']['fwhm_nm']} nm FWHM")
    for s in lib["measured_sources"]:
        print(f"  - {s}")
    ev = lib["base"]["explained_var_ratio"]
    print(f"  variance modes retained: {len(ev)}  "
          f"(explaining {100*ev.sum():.1f}% of measured leaf variance)")
    print(f"  -> {os.path.relpath(out, PATHS.root)}")

    # ------------------------------------------------------------------
    # Separability audit on library-drawn samples
    # ------------------------------------------------------------------
    ids = class_ids(cfg)
    target = cfg["confusable_pair"]["target"]
    natives = cfg["confusable_pair"]["natives"]
    veg_keys = [k for k in cfg["species_spectra"]]

    N = 500
    # The single-feature audit runs on FOLIAGE ONLY. During the autumn bloom a
    # 22% white flower fraction dominates every index — NDVI included — and the
    # audit would measure the bloom rather than the foliage chemistry. The
    # year-round detection capability is what the moat rests on, so that is what
    # gets audited; the bloom case is covered in the seasonal ablation below.
    season = "wet_summer"
    banks = {k: sample_class_spectra(lib, cfg, k, season, N, gen) for k in veg_keys}
    X = np.vstack([banks[k] for k in veg_keys])
    y = np.concatenate([np.full(N, ids[k]) for k in veg_keys])

    F, names = interpretable_features(X, wl, cfg["features"])

    audit = {"season": season, "n_per_class": N, "features": {}}
    for j, nm in enumerate(names):
        row = {nat: separability(F[:, j], y, ids[target], ids[nat]) for nat in natives}
        # Worst case, not mean: the operational failure is confusing Mikania with
        # ANY native climber, so the binding number is the hardest pair.
        row["worst_case"] = float(np.nanmin([row[n] for n in natives]))
        row["tier"] = sensor_requirement(nm)
        audit["features"][nm] = row

    tiers = {t: {k: v for k, v in audit["features"].items() if v["tier"] == t}
             for t in ("rgb", "multispectral", "hyperspectral")}
    best = {t: (max(d.items(), key=lambda kv: kv[1]["worst_case"]) if d else (None, {"worst_case": 0.0}))
            for t, d in tiers.items()}

    # A multispectral sensor also has every RGB band, so its achievable ceiling
    # is the better of the two tiers. Not accounting for that would overstate the
    # hyperspectral advantage by comparing against an artificially crippled rival.
    ms_ceiling = max(best["rgb"][1]["worst_case"], best["multispectral"][1]["worst_case"])
    hs_ceiling = best["hyperspectral"][1]["worst_case"]

    audit["summary"] = {
        "best_per_tier": {t: {"feature": b[0], "dprime": b[1]["worst_case"]}
                          for t, b in best.items()},
        "multispectral_ceiling_dprime": ms_ceiling,
        "hyperspectral_ceiling_dprime": hs_ceiling,
        "advantage_ratio": hs_ceiling / max(ms_ceiling, 1e-6),
        "interpretation": (
            "d' is the class-mean separation in pooled standard deviations, for "
            "Mikania against the WORST-CASE native climber. d' < 1 means the "
            "distributions overlap so heavily that no threshold separates them; "
            "d' > 2 is comfortably separable. The multispectral ceiling is the "
            "best of the RGB and 5-band tiers, since a multispectral sensor also "
            "carries the visible bands."
        ),
        "caveat": (
            "These are single-feature separabilities on library-drawn spectra at "
            "leaf/patch scale. They bound what any THRESHOLD on one index can do; "
            "a multivariate classifier on many weak features can exceed the best "
            "single d'. Stage 05 measures that properly, on spatially disjoint sites."
        ),
    }

    print("\nSeparability (d', Mikania vs the WORST-CASE native climber)")
    print("-" * 68)
    for t in ("rgb", "multispectral", "hyperspectral"):
        print(f"  {TIER_LABEL[t].upper()}")
        for k, v in sorted(tiers[t].items(), key=lambda kv: -kv[1]["worst_case"])[:8]:
            print(f"    {k.split('_',1)[1]:<16} d' = {v['worst_case']:.2f}")
    print("-" * 68)
    print(f"  best a multispectral drone can do : {ms_ceiling:.2f}  ({best['rgb'][0] if best['rgb'][1]['worst_case']>=ms_ceiling else best['multispectral'][0]})")
    print(f"  best hyperspectral can do         : {hs_ceiling:.2f}  ({best['hyperspectral'][0]})")
    print(f"  advantage ratio                   : {audit['summary']['advantage_ratio']:.1f}x")

    # ------------------------------------------------------------------
    # Sensor ablation — the experiment that actually settles the question
    # ------------------------------------------------------------------
    # Single-feature d' bounds what a THRESHOLD on one index can do. It does not
    # bound what a classifier using many weak features can do, and a competitor
    # arriving with a multispectral drone will not be using one index. So the
    # honest comparison is: give each sensor tier the best feature set it can
    # physically compute, hand all three to the same classifier under the same
    # cross-validation, and see what happens.
    #
    # The handicap is deliberately against us: the low-band tiers get every
    # pairwise normalised difference and ratio of their bands (5 bands -> 25
    # features), which is more than any practitioner actually computes.
    print("\nSensor ablation — same classifier, same data, different sensor")
    print("=" * 68)
    print("Run in BOTH phenological states, because the answer differs completely:")
    print("  autumn_flower : Mikania carries a dense white bloom -> visible to RGB")
    print("  wet_summer    : foliage only -> the year-round detection problem")
    print("-" * 68)

    # Draw the climber classes across several *virtual sites*, each carrying its
    # own (site, species) random effect, and validate leave-one-site-out. The
    # random-split number is computed alongside purely to demonstrate leakage.
    climber_keys = [target] + list(natives)
    ab_sites = [f"vsite_{i}" for i in range(6)]
    per = 220

    def _rf():
        return RandomForestClassifier(
            n_estimators=300, min_samples_leaf=3, class_weight="balanced_subsample",
            random_state=cfg["project"]["random_seed"], n_jobs=-1)

    ablation: dict = {}
    for season_key in ("autumn_flower", "wet_summer"):
        Xs, ys, gs = [], [], []
        for sk in ab_sites:
            for k in climber_keys:
                Xs.append(sample_class_spectra(lib, cfg, k, season_key, per, gen, site_key=sk))
                ys.append(np.full(per, ids[k]))
                gs.append(np.full(per, sk))
        Xc = np.vstack(Xs)
        yc = np.concatenate(ys)
        groups = np.concatenate(gs)
        y_bin = (yc == ids[target]).astype(int)        # Mikania vs any native

        ablation[season_key] = {}
        print(f"\n  {cfg['phenology']['seasons'][season_key]['label']}"
              f"   (flower fraction "
              f"{cfg['phenology']['seasons'][season_key]['flower_fraction']:.2f})")
        for tier in ("rgb", "multispectral", "hyperspectral"):
            Ft, _ = tier_feature_matrix(Xc, wl, tier)
            loso = GroupKFold(n_splits=len(ab_sites))

            acc4 = cross_val_score(_rf(), Ft, yc, groups=groups, cv=loso,
                                   scoring="balanced_accuracy")
            acc2 = cross_val_score(_rf(), Ft, y_bin, groups=groups, cv=loso,
                                   scoring="balanced_accuracy")
            # False positives = a native climber called Mikania. This is the error
            # that gets a native species cleared by mistake — the exact harm the
            # Government greening guidance warns about (proposal §1, §2.1b).
            pred2 = cross_val_predict(_rf(), Ft, y_bin, groups=groups, cv=loso, n_jobs=1)
            fp = float(((pred2 == 1) & (y_bin == 0)).sum() / max((y_bin == 0).sum(), 1))

            leaky = cross_val_score(
                _rf(), Ft, y_bin,
                cv=StratifiedKFold(5, shuffle=True,
                                   random_state=cfg["project"]["random_seed"]),
                scoring="balanced_accuracy").mean()

            ablation[season_key][tier] = {
                "label": SENSOR_TIERS[tier]["label"],
                "example": SENSOR_TIERS[tier]["example"],
                "n_bands": len(SENSOR_TIERS[tier]["bands"] or wl),
                "n_features": int(Ft.shape[1]),
                "balanced_accuracy_4class": float(acc4.mean()),
                "balanced_accuracy_4class_sd": float(acc4.std()),
                "balanced_accuracy_mikania_vs_native": float(acc2.mean()),
                "balanced_accuracy_mikania_vs_native_sd": float(acc2.std()),
                "false_positive_rate": fp,
                "leaky_random_split_accuracy": float(leaky),
                "leakage_inflation_pp": float((leaky - acc2.mean()) * 100.0),
            }
            a = ablation[season_key][tier]
            print(f"    {a['label']:<30} {a['n_bands']:>3}b -> {a['n_features']:>3}f "
                  f"| Mikania-vs-native {acc2.mean()*100:5.1f}% +/-{acc2.std()*100:4.1f} "
                  f"| FP {fp*100:4.1f}%")

    flo, fol = ablation["autumn_flower"], ablation["wet_summer"]
    ablation["_summary"] = {
        "rgb_seasonal_collapse_pp": (
            flo["rgb"]["balanced_accuracy_mikania_vs_native"]
            - fol["rgb"]["balanced_accuracy_mikania_vs_native"]) * 100.0,
        "hyperspectral_seasonal_collapse_pp": (
            flo["hyperspectral"]["balanced_accuracy_mikania_vs_native"]
            - fol["hyperspectral"]["balanced_accuracy_mikania_vs_native"]) * 100.0,
        "foliage_only_hyperspectral_gain_over_multispectral_pp": (
            fol["hyperspectral"]["balanced_accuracy_mikania_vs_native"]
            - fol["multispectral"]["balanced_accuracy_mikania_vs_native"]) * 100.0,
        "foliage_only_hyperspectral_gain_over_rgb_pp": (
            fol["hyperspectral"]["balanced_accuracy_mikania_vs_native"]
            - fol["rgb"]["balanced_accuracy_mikania_vs_native"]) * 100.0,
        "validation": "leave-one-site-out over 6 virtual sites with (site, species) random effects",
        "finding": (
            "During the autumn bloom every sensor tier performs well — which "
            "REPRODUCES the published result that RGB deep learning succeeds on "
            "blooming outbreak points, and is therefore a validation of the "
            "simulator rather than a weakness of it. The commercial argument is "
            "entirely in the foliage-only case, where the bloom is absent and "
            "the broadband tiers lose their cue. That is proposal §6.1(2): "
            "'RGB can do it for two months a year.'"
        ),
        "note": (
            "Library-level (leaf/patch scale). Optimistic bound, not a field "
            "result: no atmosphere, no BRDF, no mixed pixels, no georeferencing "
            "error. Stage 05 repeats this on simulated scenes; only site-disjoint "
            "scene numbers may be quoted externally."
        ),
    }
    s = ablation["_summary"]
    print("\n" + "-" * 68)
    print(f"  RGB accuracy drop, bloom -> foliage only : "
          f"{s['rgb_seasonal_collapse_pp']:+.1f} pp")
    print(f"  Hyperspectral drop, same comparison      : "
          f"{s['hyperspectral_seasonal_collapse_pp']:+.1f} pp")
    print(f"  Foliage-only hyperspectral gain vs RGB   : "
          f"{s['foliage_only_hyperspectral_gain_over_rgb_pp']:+.1f} pp")
    print(f"  Foliage-only gain vs 5-band multispectral: "
          f"{s['foliage_only_hyperspectral_gain_over_multispectral_pp']:+.1f} pp")

    audit["sensor_ablation"] = ablation

    rep_path = os.path.join(PATHS.reports, "separability.json")
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, indent=2)

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------
    colors = class_colors(cfg)
    key_to_id = ids

    # Fig 2a — the library itself
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    for k in veg_keys:
        axes[0].plot(wl, lib["endmembers"][k], lw=1.8,
                     color=colors[key_to_id[k]], label=k.replace("_", " "))
    for k in ("soil_rock", "shadow"):
        axes[0].plot(wl, lib["endmembers"][k], lw=1.2, ls="--",
                     color=colors[key_to_id[k]], label=k.replace("_", " "))
    axes[0].set(xlabel="wavelength (nm)", ylabel="reflectance",
                title="Endmember library (400-1000 nm)")
    axes[0].legend(fontsize=6.5, ncol=2, frameon=False)

    axes[1].plot(wl, lib["measured_bank"].T, lw=0.4, color="#2d9e63", alpha=0.25)
    axes[1].plot(wl, lib["base"]["mean"], lw=2.2, color="#0b3d2e",
                 label=f"mean of {lib['n_measured_spectra']} measured leaves")
    axes[1].set(xlabel="wavelength (nm)", ylabel="reflectance",
                title="Real measured base (EcoSIS tropical broadleaf)")
    axes[1].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig02a_spectral_library.png"))
    plt.close(fig)

    # Fig 2b — where the discrimination lives
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
    d1 = savgol(np.array([lib["endmembers"][k] for k in veg_keys]), deriv=1, delta_nm=5.0)
    for i, k in enumerate(veg_keys):
        axes[0].plot(wl, d1[i], lw=1.6, color=colors[key_to_id[k]], label=k.replace("_", " "))
    axes[0].axvspan(680, 760, color="#ff4d6d", alpha=0.07)
    axes[0].annotate("red edge:\nposition shift", (722, axes[0].get_ylim()[1] * 0.62),
                     fontsize=7, ha="center", color="#8a1030")
    axes[0].set(xlabel="wavelength (nm)", ylabel="dR/d$\\lambda$",
                title="First derivative — the red-edge position feature")
    axes[0].legend(fontsize=6.5, frameon=False)

    mik = lib["endmembers"][target]
    for nat in natives:
        axes[1].plot(wl, 100.0 * (mik - lib["endmembers"][nat]) / np.maximum(lib["endmembers"][nat], 1e-3),
                     lw=1.6, color=colors[key_to_id[nat]], label=f"vs {nat.replace('_',' ')}")
    axes[1].axhline(0, color="#333", lw=0.8)
    for lo, hi, lab in [(430, 500, "B"), (500, 580, "G"), (590, 680, "R")]:
        axes[1].axvspan(lo, hi, color="#888", alpha=0.06)
        axes[1].annotate(lab, ((lo + hi) / 2, axes[1].get_ylim()[0] * 0.85),
                         fontsize=7, ha="center", color="#666")
    axes[1].set(xlabel="wavelength (nm)", ylabel="relative difference (%)",
                title="Mikania minus native climber\n(grey = the three RGB passbands)")
    axes[1].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig02b_discrimination.png"))
    plt.close(fig)

    # Fig 2c — what each sensor class can actually achieve
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    items = sorted(audit["features"].items(), key=lambda kv: kv[1]["worst_case"])
    labels = [k.split("_", 1)[1] for k, _ in items]
    vals = [v["worst_case"] for _, v in items]
    cols = [TIER_COLOR[v["tier"]] for _, v in items]
    ax.barh(labels, vals, color=cols, height=0.74)
    ax.axvline(1.0, color="#444", ls="--", lw=1.0)
    ax.annotate("d' = 1\nheavy overlap", (1.04, 0.4), fontsize=7, color="#444")
    ax.axvline(ms_ceiling, color=TIER_COLOR["multispectral"], ls=":", lw=1.4)
    ax.annotate(f"multispectral ceiling\nd' = {ms_ceiling:.2f}",
                (ms_ceiling + 0.05, len(labels) * 0.72), fontsize=7,
                color=TIER_COLOR["multispectral"])
    handles = [plt.Rectangle((0, 0), 1, 1, color=TIER_COLOR[t]) for t in TIER_COLOR]
    ax.legend(handles, [TIER_LABEL[t] for t in TIER_COLOR], fontsize=7,
              loc="lower right", frameon=False)
    ax.set(xlabel="separability d'  (Mikania vs worst-case native climber)",
           title="Single-feature separability by sensor class")
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig02c_sensor_tier_separability.png"))
    plt.close(fig)

    # Fig 2d — the seasonal ablation: the actual commercial argument
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.2))
    tier_order = ["rgb", "multispectral", "hyperspectral"]
    xs = np.arange(len(tier_order))
    width = 0.38

    for k, (skey, slabel) in enumerate([("autumn_flower", "Sep-Nov, in bloom"),
                                        ("wet_summer", "Jun-Aug, foliage only")]):
        vals = [ablation[skey][t]["balanced_accuracy_mikania_vs_native"] * 100 for t in tier_order]
        errs = [ablation[skey][t]["balanced_accuracy_mikania_vs_native_sd"] * 100 for t in tier_order]
        axes[0].bar(xs + (k - 0.5) * width, vals, width, yerr=errs, capsize=3,
                    label=slabel, color=["#9aa5b1", "#1f8a70"][k],
                    edgecolor="white", linewidth=0.6)

    kill = cfg["kill_criteria"]["mikania_vs_native_min_accuracy"] * 100
    axes[0].axhline(kill, color="#c0392b", ls="--", lw=1.2)
    axes[0].annotate(f"§7.3 kill criterion {kill:.0f}%", (-0.42, kill + 1.4),
                     fontsize=7, color="#c0392b")
    axes[0].axhline(50, color="#666", ls=":", lw=1.0)
    axes[0].annotate("chance", (-0.42, 51.2), fontsize=7, color="#666")
    axes[0].set_xticks(xs)
    axes[0].set_xticklabels(["RGB", "5-band\nmultispectral", "hyperspectral"], fontsize=8)
    axes[0].set(ylabel="Mikania vs native climber (balanced acc., %)",
                ylim=(40, 104), title="Every sensor works in bloom.\nOnly one works the rest of the year.")
    axes[0].legend(fontsize=7, frameon=False, loc="lower left")

    for k, (skey, slabel) in enumerate([("autumn_flower", "in bloom"),
                                        ("wet_summer", "foliage only")]):
        vals = [ablation[skey][t]["false_positive_rate"] * 100 for t in tier_order]
        axes[1].bar(xs + (k - 0.5) * width, vals, width, label=slabel,
                    color=["#9aa5b1", "#c0392b"][k], edgecolor="white", linewidth=0.6)
    maxfp = cfg["kill_criteria"]["max_false_positive_rate"] * 100
    axes[1].axhline(maxfp, color="#c0392b", ls="--", lw=1.2)
    axes[1].annotate(f"max acceptable {maxfp:.0f}%", (-0.42, maxfp + 0.6), fontsize=7, color="#c0392b")
    axes[1].set_xticks(xs)
    axes[1].set_xticklabels(["RGB", "5-band\nmultispectral", "hyperspectral"], fontsize=8)
    axes[1].set(ylabel="false positive rate (%)",
                title="False positives = a native climber\ncleared by mistake")
    axes[1].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig02d_seasonal_sensor_ablation.png"))
    plt.close(fig)

    print(f"\nFigures  -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig02*.png")
    print(f"Report   -> {os.path.relpath(rep_path, PATHS.root)}")
    print("STAGE 02 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
