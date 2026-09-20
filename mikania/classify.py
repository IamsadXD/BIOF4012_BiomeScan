"""
Classification and — more importantly — honest validation.

Proposal §5.1, mitigation (6) is the single most consequential methodological
statement in the document, and this module exists to enforce it in code rather
than in good intentions:

    "Adjacent pixels in a hyperspectral scene are spatially autocorrelated.
     Random pixel-level train/test splitting leaks catastrophically and produces
     99% accuracies that collapse on new ground. All reported accuracy must be
     from spatially disjoint hold-out sites, with honest confidence intervals.
     This is the single most common failure in the applied hyperspectral
     literature, and reporting honestly is a competitive advantage in a market
     where inflated numbers are the norm."

Accordingly:

* :func:`leave_one_site_out` is the only validation function whose output is
  labelled reportable;
* :func:`random_split_leakage_demo` exists solely to quantify how much a random
  split would have inflated the number, so the gap can be shown to an evaluator;
* every headline metric is returned with a bootstrap confidence interval,
  because a point estimate from five sites is not a result.

Three model families are compared, mirroring the reference literature (Huang et
al. 2021 used SG + PCA + RF and SG + PCA + SVM):

``plsda``  Partial Least Squares Discriminant Analysis — the chemometric
           standard; linear, interpretable, robust in high dimensions.
``rf``     Random Forest — the paper's best performer (88.71%, kappa 0.774).
``svm``    RBF SVM — the paper's fast performer (84.68%, kappa 0.693).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.cross_decomposition import PLSRegression
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             cohen_kappa_score, confusion_matrix)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from .config import class_groups, class_ids, class_keys
from .preprocess import build_feature_stack


# ==========================================================================
# PLS-DA
# ==========================================================================
class PLSDA(BaseEstimator, ClassifierMixin):
    """
    PLS Discriminant Analysis: PLS regression onto a one-hot class matrix,
    classified by argmax of the predicted response.

    scikit-learn has no PLS-DA, and it is the chemometric default for exactly
    this kind of problem — a linear model that finds the directions of X most
    covariant with class membership, which behaves well when bands vastly
    outnumber independent samples and are strongly collinear (as 121 contiguous
    5 nm bands certainly are).
    """

    def __init__(self, n_components: int = 18, scale: bool = False):
        self.n_components = n_components
        self.scale = scale

    def fit(self, X, y):
        X = np.asarray(X, dtype=np.float64)
        self.classes_ = np.unique(y)
        Y = np.zeros((len(y), self.classes_.size))
        for i, c in enumerate(self.classes_):
            Y[y == c, i] = 1.0
        n_comp = int(min(self.n_components, X.shape[1], max(X.shape[0] - 1, 1)))
        self._pls = PLSRegression(n_components=n_comp, scale=self.scale)
        self._pls.fit(X, Y)
        return self

    def decision_function(self, X):
        return self._pls.predict(np.asarray(X, dtype=np.float64))

    def predict(self, X):
        return self.classes_[np.argmax(self.decision_function(X), axis=1)]

    def predict_proba(self, X):
        """Softmax over the PLS response. Not calibrated — used only for ranking."""
        d = self.decision_function(X)
        e = np.exp(d - d.max(axis=1, keepdims=True))
        return e / np.maximum(e.sum(axis=1, keepdims=True), 1e-12)


# ==========================================================================
# Model factory
# ==========================================================================
def make_model(name: str, cfg: Dict[str, Any]) -> Pipeline:
    """
    Build one of the three configured models as a full pipeline.

    Every pipeline starts with ``StandardScaler``. That is not decoration: the
    feature stack concatenates reflectance, first derivative and second
    derivative blocks whose natural magnitudes differ by orders of magnitude, and
    without scaling the PCA and the SVM would both be dominated by whichever
    block happens to have the largest units.

    PCA is applied where the config asks for it, matching the published
    SG + PCA + {RF, SVM} chain.
    """
    m = cfg["models"]
    steps: List[Tuple[str, Any]] = [("scale", StandardScaler())]

    if cfg["features"].get("use_pca", True) and name != "plsda":
        # PLS-DA does its own supervised dimensionality reduction; stacking an
        # unsupervised PCA in front of it would discard class-relevant variance
        # before the supervised step ever sees it.
        steps.append(("pca", PCA(n_components=int(cfg["features"]["pca_components"]),
                                 random_state=cfg["project"]["random_seed"])))

    if name == "plsda":
        steps.append(("clf", PLSDA(n_components=int(m["plsda"]["n_components"]))))
    elif name == "rf":
        p = m["random_forest"]
        steps.append(("clf", RandomForestClassifier(
            n_estimators=int(p["n_estimators"]), max_depth=p.get("max_depth"),
            min_samples_leaf=int(p["min_samples_leaf"]),
            class_weight=p.get("class_weight"), n_jobs=int(p.get("n_jobs", -1)),
            random_state=cfg["project"]["random_seed"])))
    elif name == "svm":
        p = m["svm"]
        steps.append(("clf", SVC(C=float(p["C"]), gamma=p.get("gamma", "scale"),
                                 kernel=p.get("kernel", "rbf"),
                                 class_weight=p.get("class_weight"),
                                 random_state=cfg["project"]["random_seed"])))
    else:
        raise ValueError(f"unknown model {name!r}")

    return Pipeline(steps)


# ==========================================================================
# Dataset assembly
# ==========================================================================
def scene_to_samples(scene: Dict[str, Any], cfg: Dict[str, Any],
                     gen: np.random.Generator,
                     max_per_class: int = 2500) -> Dict[str, np.ndarray]:
    """
    Turn one scene into a labelled sample set.

    Pixels are subsampled per class up to ``max_per_class``. This matters for
    more than speed: without a cap, host canopy at ~46% of the scene would
    dominate the loss and the model would optimise the class nobody is paying
    for. Capping equalises influence without discarding the natural class
    frequencies from the reported metrics, which are computed on the full map.

    Returns feature matrix, labels, site group, and pixel coordinates (kept so
    predictions can be mapped back into raster space).
    """
    cube = scene["cube"]
    gt = scene["gt"]
    wl = scene["wavelengths"]
    h, w, b = cube.shape

    rows, cols, labels = [], [], []
    for cid in np.unique(gt):
        if cid == 0:                       # unlabelled
            continue
        rr, cc = np.where(gt == cid)
        if rr.size > max_per_class:
            sel = gen.choice(rr.size, max_per_class, replace=False)
            rr, cc = rr[sel], cc[sel]
        rows.append(rr); cols.append(cc)
        labels.append(np.full(rr.size, cid, dtype=np.int16))

    r = np.concatenate(rows); c = np.concatenate(cols)
    y = np.concatenate(labels)
    X_raw = cube[r, c, :].astype(np.float64)
    X, names = build_feature_stack(X_raw, wl, cfg["preprocess"])

    site = scene["meta"]["site_key"]
    return {
        "X": X, "y": y,
        "groups": np.full(y.size, site),
        "row": r, "col": c,
        "raw": X_raw,
        "feature_names": np.array(names),
        "site": site,
    }


def stack_samples(parts: Sequence[Dict[str, np.ndarray]]) -> Dict[str, np.ndarray]:
    """Concatenate per-scene sample sets into one dataset."""
    return {
        "X": np.vstack([p["X"] for p in parts]),
        "y": np.concatenate([p["y"] for p in parts]),
        "groups": np.concatenate([p["groups"] for p in parts]),
        "row": np.concatenate([p["row"] for p in parts]),
        "col": np.concatenate([p["col"] for p in parts]),
        "feature_names": parts[0]["feature_names"],
    }


# ==========================================================================
# Metrics
# ==========================================================================
def climber_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                    cfg: Dict[str, Any]) -> Dict[str, float]:
    """
    The metrics the kill criterion is defined on (proposal §7.3).

    Overall accuracy across eight classes is the wrong number to manage against:
    soil, shadow and water are easy and inflate it. What decides whether there is
    a business is the Mikania-versus-native-climber sub-problem, and the false
    positive rate on it — because a false positive means a native climber gets
    cleared, which is the specific harm the Government guidance warns about.
    """
    ids = class_ids(cfg)
    groups = class_groups(cfg)
    tgt = ids[cfg["confusable_pair"]["target"]]
    nat = [ids[k] for k in cfg["confusable_pair"]["natives"]]

    m = np.isin(y_true, [tgt] + nat)
    if not m.any():
        return {"n": 0}

    t = (y_true[m] == tgt).astype(int)
    # A native predicted as some non-climber class is not a Mikania false
    # positive; only an actual Mikania call counts.
    p = (y_pred[m] == tgt).astype(int)

    tp = int(((p == 1) & (t == 1)).sum())
    fp = int(((p == 1) & (t == 0)).sum())
    fn = int(((p == 0) & (t == 1)).sum())
    tn = int(((p == 0) & (t == 0)).sum())

    return {
        "n": int(m.sum()),
        "balanced_accuracy": float(balanced_accuracy_score(t, p)),
        "accuracy": float(accuracy_score(t, p)),
        "recall_mikania": tp / max(tp + fn, 1),
        "precision_mikania": tp / max(tp + fp, 1),
        "false_positive_rate": fp / max(fp + tn, 1),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def full_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                 cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Overall + per-class + climber-subproblem metrics for one fold."""
    keys = class_keys(cfg)
    labels = sorted(set(np.unique(y_true)) | set(np.unique(y_pred)))
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    per_class = {}
    for i, c in enumerate(labels):
        tp = cm[i, i]
        fn = cm[i].sum() - tp
        fp = cm[:, i].sum() - tp
        per_class[keys.get(int(c), str(c))] = {
            "support": int(cm[i].sum()),
            "recall": float(tp / max(tp + fn, 1)),
            "precision": float(tp / max(tp + fp, 1)),
            "f1": float(2 * tp / max(2 * tp + fp + fn, 1)),
        }

    return {
        "overall_accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "kappa": float(cohen_kappa_score(y_true, y_pred)),
        "confusion_matrix": cm.tolist(),
        "confusion_labels": [keys.get(int(c), str(c)) for c in labels],
        "per_class": per_class,
        "climber": climber_metrics(y_true, y_pred, cfg),
    }


def bootstrap_ci(values: Sequence[float], iters: int = 400, ci: float = 0.95,
                 gen: Optional[np.random.Generator] = None) -> Tuple[float, float, float]:
    """
    Percentile bootstrap over per-site fold scores.

    Resampling SITES, not pixels, is the whole point: pixels within a site are
    not independent, so a pixel bootstrap would produce an absurdly narrow
    interval that misrepresents how much we actually know. With five sites the
    interval is wide — and that width is the honest message, not a defect to be
    engineered away.
    """
    gen = gen or np.random.default_rng(0)
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return (float("nan"),) * 3
    if v.size == 1:
        return float(v[0]), float(v[0]), float(v[0])
    draws = gen.choice(v, size=(iters, v.size), replace=True).mean(axis=1)
    lo = float(np.percentile(draws, 100 * (1 - ci) / 2))
    hi = float(np.percentile(draws, 100 * (1 + ci) / 2))
    return float(v.mean()), lo, hi


# ==========================================================================
# Validation strategies
# ==========================================================================
def leave_one_site_out(data: Dict[str, np.ndarray], cfg: Dict[str, Any],
                       model_name: str = "rf",
                       gen: Optional[np.random.Generator] = None) -> Dict[str, Any]:
    """
    THE reportable validation. Train on all sites but one, test on the held-out
    site, repeat for every site.

    Each fold trains a model that has never seen a single pixel from the test
    catchment — not a neighbouring pixel, not a pixel from the same patch, not a
    pixel that shares an illumination field or a site random effect. That is what
    "spatially disjoint" has to mean for the number to transfer to new ground.
    """
    gen = gen or np.random.default_rng(cfg["project"]["random_seed"])
    sites = sorted(set(data["groups"].tolist()))

    folds, oof_true, oof_pred, oof_site = [], [], [], []
    for s in sites:
        te = data["groups"] == s
        tr = ~te
        if tr.sum() == 0 or te.sum() == 0:
            continue
        model = make_model(model_name, cfg)
        model.fit(data["X"][tr], data["y"][tr])
        pred = model.predict(data["X"][te])

        fm = full_metrics(data["y"][te], pred, cfg)
        fm["held_out_site"] = s
        fm["n_train"] = int(tr.sum())
        fm["n_test"] = int(te.sum())
        folds.append(fm)

        oof_true.append(data["y"][te]); oof_pred.append(pred)
        oof_site.append(np.full(int(te.sum()), s))

    y_true = np.concatenate(oof_true)
    y_pred = np.concatenate(oof_pred)

    oa = [f["overall_accuracy"] for f in folds]
    ka = [f["kappa"] for f in folds]
    cb = [f["climber"].get("balanced_accuracy", np.nan) for f in folds]
    fpr = [f["climber"].get("false_positive_rate", np.nan) for f in folds]

    it = int(cfg["validation"]["bootstrap_iters"])
    lvl = float(cfg["validation"]["ci"])

    return {
        "strategy": "leave_one_site_out",
        "model": model_name,
        "n_sites": len(folds),
        "folds": folds,
        "pooled": full_metrics(y_true, y_pred, cfg),
        "overall_accuracy_ci": bootstrap_ci(oa, it, lvl, gen),
        "kappa_ci": bootstrap_ci(ka, it, lvl, gen),
        "climber_balanced_accuracy_ci": bootstrap_ci(cb, it, lvl, gen),
        "climber_false_positive_ci": bootstrap_ci(fpr, it, lvl, gen),
        "reportable": True,
        "oof": {"y_true": y_true, "y_pred": y_pred, "site": np.concatenate(oof_site)},
    }


def random_split_leakage_demo(data: Dict[str, np.ndarray], cfg: Dict[str, Any],
                              model_name: str = "rf",
                              test_size: float = 0.3) -> Dict[str, Any]:
    """
    Deliberately do the wrong thing, and measure how wrong it looks.

    A random pixel split puts pixels from the same patch — often literally
    adjacent pixels — on both sides of the train/test boundary. The model can
    then memorise local texture and illumination rather than learning species,
    and the resulting accuracy is an artefact.

    The gap between this number and the leave-one-site-out number is the single
    most useful slide in a technical evaluation, because most competing
    proposals will be quoting the inflated figure without knowing it.
    """
    from sklearn.model_selection import train_test_split

    Xtr, Xte, ytr, yte = train_test_split(
        data["X"], data["y"], test_size=test_size,
        random_state=cfg["project"]["random_seed"], stratify=data["y"])
    model = make_model(model_name, cfg)
    model.fit(Xtr, ytr)
    pred = model.predict(Xte)
    out = full_metrics(yte, pred, cfg)
    out.update({
        "strategy": "random_pixel_split",
        "model": model_name,
        "reportable": False,
        "warning": (
            "NOT REPORTABLE. Spatially autocorrelated pixels appear in both "
            "train and test. Included only to quantify the inflation this "
            "produces relative to leave-one-site-out (proposal §5.1 mitigation 6)."
        ),
    })
    return out
