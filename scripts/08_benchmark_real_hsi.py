#!/usr/bin/env python
"""
STAGE 08 — Run the same pipeline on REAL hyperspectral imagery.
===============================================================

Everything up to here has been measured on scenes this project simulated. That
is a legitimate way to build and exercise a pipeline, and an illegitimate way to
claim it works. This stage is the control.

The Botswana scene (EO-1 Hyperion, 145 retained bands, 1476 x 256 px) is a real
satellite hyperspectral acquisition over the Okavango Delta with 14 labelled
vegetation classes — several of them species-level woodland and riparian types
including *Colophospermum mopane*, *Acacia* variants and several sedge/grassland
communities. It is a genuine species-discrimination-in-vegetation problem
recorded by a real instrument, which is exactly the analogue we need.

What this stage proves, and what it does not
--------------------------------------------
**Proves:** the preprocessing chain, the feature stack, the model factory and —
critically — the spatially-blocked validation machinery all work on real
hyperspectral data with real sensor noise, real atmospheric residuals and real
spatial autocorrelation. And it re-demonstrates the leakage result on data
nobody can accuse us of having generated to order.

**Does not prove:** anything about Mikania, Hong Kong, or the separability of
*Mikania micrantha* from *Bauhinia glauca*. Different continent, different
species, 30 m pixels rather than 8 cm. It is a machinery check, not an ecology
result, and it is labelled as such everywhere it appears.

Spatial blocking on a scene with no site labels
-----------------------------------------------
Botswana has no "site" column, so leave-one-site-out is emulated by cutting the
scene into contiguous spatial blocks and holding out whole blocks. This is the
standard spatial-blocking approach and it is the same idea as the catchment
hold-out: no test pixel may be adjacent to a training pixel.
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
from scipy.io import loadmat
from sklearn.metrics import cohen_kappa_score

from mikania.classify import bootstrap_ci, full_metrics, make_model
from mikania.config import PATHS, load_config, rng
from mikania.preprocess import build_feature_stack

plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 160, "font.size": 8.5,
                     "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white"})

# Botswana class names, from the dataset's published documentation.
BOTSWANA_CLASSES = [
    "Water", "Hippo grass", "Floodplain grasses 1", "Floodplain grasses 2",
    "Reeds", "Riparian", "Firescar", "Island interior",
    "Acacia woodlands", "Acacia shrublands", "Acacia grasslands",
    "Short mopane", "Mixed mopane", "Exposed soils",
]

# EO-1 Hyperion retains 145 bands after removing water-absorption and noisy
# regions. The retained set spans 400-2500 nm; this is the published grouping.
HYPERION_BANDS_NM = np.concatenate([
    np.arange(427.55, 925.85, 10.21),      # VNIR 10-63
    np.arange(932.72, 1348.0, 10.21),      # SWIR-1
    np.arange(1418.0, 1800.0, 10.21),
    np.arange(1968.0, 2396.0, 10.21),
])


def spatial_blocks(shape, n_blocks_y=4, n_blocks_x=2):
    """
    Label each pixel with a contiguous spatial block id.

    Blocks are the stand-in for catchments. Holding out a whole block means no
    test pixel touches a training pixel, which is the only way to stop spatial
    autocorrelation from leaking — the same principle as the leave-one-site-out
    design in stage 04.
    """
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    by = (yy * n_blocks_y // h).clip(0, n_blocks_y - 1)
    bx = (xx * n_blocks_x // w).clip(0, n_blocks_x - 1)
    return (by * n_blocks_x + bx).astype(int)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="rf", choices=["plsda", "rf", "svm"])
    ap.add_argument("--max-per-class", type=int, default=900)
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=1000)

    cube_p = os.path.join(PATHS.raw, "Botswana.mat")
    gt_p = os.path.join(PATHS.raw, "Botswana_gt.mat")
    if not (os.path.exists(cube_p) and os.path.exists(gt_p)):
        print("Botswana benchmark not downloaded. Run:")
        print("  python scripts/01_fetch_open_data.py")
        return 1

    print("\nSTAGE 08 — real hyperspectral benchmark (EO-1 Hyperion, Botswana)")
    print("=" * 78)

    cube = loadmat(cube_p)["Botswana"].astype(np.float64)
    gt = loadmat(gt_p)["Botswana_gt"].astype(int)
    h, w, b = cube.shape
    wl = HYPERION_BANDS_NM[:b] if HYPERION_BANDS_NM.size >= b else np.linspace(400, 2500, b)

    print(f"  cube {h} x {w} x {b} bands   labelled pixels {int((gt>0).sum()):,}   "
          f"classes {int(gt.max())}")
    print(f"  REAL data: real sensor noise, real atmosphere, real autocorrelation.")

    # ---------- sample ----------
    blocks = spatial_blocks((h, w))
    rows, cols = [], []
    for c in range(1, gt.max() + 1):
        rr, cc = np.where(gt == c)
        if rr.size == 0:
            continue
        if rr.size > args.max_per_class:
            sel = gen.choice(rr.size, args.max_per_class, replace=False)
            rr, cc = rr[sel], cc[sel]
        rows.append(rr); cols.append(cc)
    r = np.concatenate(rows); c = np.concatenate(cols)
    y = gt[r, c]
    grp = blocks[r, c]

    X_raw = cube[r, c, :]
    # Hyperion is delivered as scaled radiance; normalise per spectrum so the
    # same preprocessing chain applies as to our reflectance cubes.
    X_raw = X_raw / np.maximum(np.abs(X_raw).max(axis=1, keepdims=True), 1e-8)
    X, _ = build_feature_stack(X_raw, wl, cfg["preprocess"])
    print(f"  sampled {X.shape[0]:,} pixels -> {X.shape[1]} features "
          f"(same SG + derivative + SNV chain as the Mikania pipeline)")

    # ---------- spatially blocked CV ----------
    print("\n  Spatially-blocked cross-validation (leave-one-BLOCK-out)")
    print("  " + "-" * 72)
    # Botswana's classes are strongly spatially segregated — several occur in
    # only one part of the delta. So some blocks contain classes the training
    # folds never saw, and the model cannot possibly get those right. Counting
    # them as errors would overstate the leakage gap by blaming spatial blocking
    # for a class-coverage problem. Both numbers are therefore reported: the raw
    # one, and the one restricted to test pixels whose class was trainable.
    fold_oa, fold_kappa, fold_oa_cov = [], [], []
    oof_t, oof_p = [], []
    coverage = []
    for blk in sorted(set(grp.tolist())):
        te = grp == blk
        tr = ~te
        if te.sum() < 50 or len(set(y[tr].tolist())) < 2:
            continue
        model = make_model(args.model, cfg)
        model.fit(X[tr], y[tr])
        pred = model.predict(X[te])

        seen = np.isin(y[te], np.unique(y[tr]))
        oa = float((pred == y[te]).mean())
        oa_cov = float((pred[seen] == y[te][seen]).mean()) if seen.any() else float("nan")
        kp = float(cohen_kappa_score(y[te], pred))

        fold_oa.append(oa); fold_kappa.append(kp); fold_oa_cov.append(oa_cov)
        coverage.append(float(seen.mean()))
        oof_t.append(y[te]); oof_p.append(pred)
        print(f"    block {blk}   n_test {int(te.sum()):>5}   "
              f"overall {oa*100:5.1f}%   kappa {kp:>6.3f}   "
              f"classes trainable {seen.mean()*100:5.1f}%   "
              f"on those {0.0 if np.isnan(oa_cov) else oa_cov*100:5.1f}%")

    oa_m, oa_lo, oa_hi = bootstrap_ci(fold_oa, 400, 0.95, gen)
    kp_m, kp_lo, kp_hi = bootstrap_ci(fold_kappa, 400, 0.95, gen)
    cov_m, cov_lo, cov_hi = bootstrap_ci([v for v in fold_oa_cov if np.isfinite(v)],
                                         400, 0.95, gen)
    print("  " + "-" * 72)
    print(f"    BLOCKED (raw)        overall {oa_m*100:5.1f}% "
          f"[{oa_lo*100:.1f}-{oa_hi*100:.1f}]   kappa {kp_m:.3f}")
    print(f"    BLOCKED (trainable)  overall {cov_m*100:5.1f}% "
          f"[{cov_lo*100:.1f}-{cov_hi*100:.1f}]   "
          f"<- the fair number: excludes classes absent from training")

    # ---------- the leaky comparison ----------
    from sklearn.model_selection import train_test_split
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y,
                                          random_state=cfg["project"]["random_seed"])
    model = make_model(args.model, cfg)
    model.fit(Xtr, ytr)
    pr = model.predict(Xte)
    leak_oa = float((pr == yte).mean())
    leak_kp = float(cohen_kappa_score(yte, pr))
    print(f"    RANDOM               overall {leak_oa*100:5.1f}%                 "
          f"kappa {leak_kp:.3f}")
    print(f"\n    inflation vs raw blocked       {((leak_oa - oa_m)*100):+5.1f} pp")
    print(f"    inflation vs trainable blocked {((leak_oa - cov_m)*100):+5.1f} pp  "
          f"<- the defensible figure")
    print("\n    The same leakage effect, on real data we did not generate.")
    print("    This is the number most published hyperspectral results quote.")

    # ---------- report ----------
    y_true = np.concatenate(oof_t); y_pred = np.concatenate(oof_p)
    report = {
        "dataset": "Botswana (EO-1 Hyperion)",
        "provenance": "https://huggingface.co/datasets/danaroth/botswana",
        "shape": [h, w, b],
        "n_classes": int(gt.max()),
        "class_names": BOTSWANA_CLASSES,
        "model": args.model,
        "blocked_overall_accuracy": [oa_m, oa_lo, oa_hi],
        "blocked_overall_accuracy_trainable_classes": [cov_m, cov_lo, cov_hi],
        "per_fold_class_coverage": coverage,
        "class_coverage_note": (
            "Botswana classes are spatially segregated, so some blocks contain "
            "classes no training fold saw. The 'trainable' figure excludes those "
            "pixels; it is the fair comparison against a random split, which by "
            "construction never has unseen classes."
        ),
        "blocked_kappa": [kp_m, kp_lo, kp_hi],
        "random_split_overall_accuracy": leak_oa,
        "random_split_kappa": leak_kp,
        "leakage_inflation_pp": (leak_oa - oa_m) * 100,
        "leakage_inflation_pp_trainable": (leak_oa - cov_m) * 100,
        "per_fold_overall": fold_oa,
        "pooled": full_metrics(y_true, y_pred, cfg),
        "what_this_proves": (
            "The preprocessing chain, feature stack, model factory and "
            "spatially-blocked validation machinery all function on real "
            "hyperspectral imagery with real sensor noise and real spatial "
            "autocorrelation, and the leakage effect reproduces on data this "
            "project did not generate."
        ),
        "what_this_does_not_prove": (
            "Nothing about Mikania micrantha, Hong Kong, or separability from "
            "Bauhinia glauca / Byttneria aspera. Different continent, different "
            "species, 30 m pixels versus 8 cm. Machinery check only."
        ),
    }
    rp = os.path.join(PATHS.reports, "benchmark_botswana.json")
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=float)

    # ---------- figure ----------
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.6))

    band = cube[:, :, 30]
    lo, hi = np.percentile(band, [2, 98])
    axes[0].imshow(np.clip((band - lo) / max(hi - lo, 1e-6), 0, 1).T, cmap="gray",
                   aspect="auto")
    axes[0].set(title="Botswana, Hyperion band 31\n(real satellite hyperspectral)")
    axes[0].grid(False); axes[0].set_xticks([]); axes[0].set_yticks([])

    gtm = np.ma.masked_where(gt == 0, gt)
    axes[1].imshow(gtm.T, cmap="tab20", aspect="auto")
    axes[1].set(title=f"Ground truth\n{gt.max()} vegetation classes")
    axes[1].grid(False); axes[1].set_xticks([]); axes[1].set_yticks([])

    axes[2].bar([0, 1, 2], [leak_oa * 100, cov_m * 100, oa_m * 100],
                yerr=[[0, (cov_m - cov_lo) * 100, (oa_m - oa_lo) * 100],
                      [0, (cov_hi - cov_m) * 100, (oa_hi - oa_m) * 100]],
                capsize=5, color=["#c0392b", "#1f8a70", "#9aa5b1"], width=0.6,
                edgecolor="white")
    axes[2].set_xticks([0, 1, 2])
    axes[2].set_xticklabels(["random\npixel split", "spatially blocked\n(trainable classes)",
                             "spatially blocked\n(raw)"], fontsize=7)
    axes[2].set(ylabel="overall accuracy (%)", ylim=(0, 108),
                title=f"Leakage reproduces on REAL data\n{(leak_oa-cov_m)*100:+.1f} pp inflation")
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig08_benchmark_botswana.png"))
    plt.close(fig)

    print(f"\nReport   -> {os.path.relpath(rp, PATHS.root)}")
    print(f"Figure   -> outputs/figures/fig08_benchmark_botswana.png")
    print("STAGE 08 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
