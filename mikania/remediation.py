"""
Remediation — the fixes for the three problems the pipeline found in the proposal.

``docs/09_findings_vs_proposal.md`` reports three claims that do not survive
measurement. Reporting a problem without a fix is criticism, not engineering, so
this module implements the remedies — and, more importantly, **measures whether
they work**. Proposing an untested fix would repeat exactly the mistake that
sank §3.3(a): claiming a benefit nobody checked.

===============================  ==========================================
Problem (docs/09)                Fix implemented here
===============================  ==========================================
1. Risk 9 sign; the go/no-go     :func:`certification_allocation` —
   test spuriously fails         certify the VALIDATION set, not the
                                 training set. Plus
                                 :func:`disagreement_targeting`, which
                                 finds the mislabelled specimens for a
                                 fraction of the sequencing budget.
2. Public reference coverage     :func:`reference_gap_plan` — how many
   inadequate (B.9 false)        sequences close each gap, and what it costs.
3. §3.3(a) band prior not        :func:`PriorScaler` + :func:`prior_model` —
   implementable as a weight     apply the prior AFTER standardisation, as a
                                 penalty on a regularised model.
===============================  ==========================================

The insight behind fix 1
------------------------
The §7.3 kill criterion is evaluated on the **hold-out**, not on the training
set. So the decision's trustworthiness depends on the *validation* labels being
right, and barely at all on the training labels being right — because, as stage
13 measured, the classifier overrides label noise in training rather than
learning it.

That inverts the §3.4 spending plan. §3.4 says "every voucher entering the
reference library is barcode-verified before it can train anything", which
allocates the sequencing budget across the whole voucher set. If the aim is to
protect the HK$1.4M go/no-go decision, the efficient allocation is the opposite:
certify the validation plots exhaustively and sample the training plots.

The insight behind fix 3
------------------------
The band prior failed because of **operation order**, not because the idea is
wrong. Multiplying features by weights and then handing them to a pipeline whose
first step is ``StandardScaler`` restores unit variance per band and annihilates
the weight exactly.

Applied *after* standardisation, to a model with an L2 penalty, a per-feature
scale is no longer cosmetic: scaling standardised feature *j* by *w_j* is
algebraically identical to giving its coefficient a penalty of λ/w_j². That is a
textbook informative prior, and it is what §3.3(a) was reaching for.

Two conditions have to hold for it to be testable at all, and both were violated
in the first attempt: the model must be **penalised** (an unpenalised or
tree-based model ignores feature scale), and PCA must be **off** (PCA rotates the
band basis away, destroying the identity the prior is expressed in).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .classify import make_model
from .config import class_ids
from .labelerror import corrupt_labels


# ==========================================================================
# FIX 1 — certify the validation set, not the training set
# ==========================================================================
def _certify(y_true: np.ndarray, y_obs: np.ndarray, unit_id: np.ndarray,
             fraction: float, gen: np.random.Generator,
             order: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Restore true labels for a fraction of SPECIMENS (not pixels).

    Certification happens one plant at a time, exactly as misidentification does,
    so the unit here must match the unit in :func:`~mikania.labelerror.corrupt_labels`.
    Certifying a random 30% of *pixels* would silently certify a slice of almost
    every specimen and overstate the benefit enormously.

    ``order`` optionally supplies a priority ranking over specimens (see
    :func:`disagreement_targeting`); without it, specimens are chosen at random,
    which is the honest baseline.
    """
    units = np.unique(unit_id)
    n_cert = int(round(fraction * units.size))
    if order is not None:
        chosen = np.asarray(order)[:n_cert]
    else:
        chosen = gen.choice(units, size=min(n_cert, units.size), replace=False)

    m = np.isin(unit_id, chosen)
    y_out = np.where(m, y_true, y_obs)
    return {"y": y_out, "certified_mask": m, "n_units_certified": int(len(chosen)),
            "n_units_total": int(units.size)}


def certification_allocation(data: Dict[str, np.ndarray], cfg: Dict[str, Any],
                             gen: np.random.Generator,
                             fractions: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.0),
                             rates: Sequence[float] = (0.18, 0.30),
                             replicates: int = 6,
                             bias: Optional[float] = None,
                             model_name: str = "rf",
                             holdout_site: Optional[str] = None) -> Dict[str, Any]:
    """
    Where should the sequencing budget go — training labels, or validation labels?

    Four arms:

    ``none``        nothing certified — the status quo a competitor operates in.
    ``train_only``  certify training specimens; validation stays uncertified.
    ``val_only``    certify validation specimens; training stays uncertified.
    ``both``        certify everything — the §3.4 plan as written.

    **The reported quantity is P(wrong go/no-go decision), not accuracy.** A
    programme does not act on an accuracy figure; it acts on a verdict. And a
    single draw is not enough to measure a verdict: a first version of this
    experiment ran one replicate at one error rate, landed on a draw where the
    corrupted accuracy happened to sit above the threshold anyway, and therefore
    showed all four arms making the correct decision — demonstrating nothing.
    Decision error is a probability and has to be estimated as one.

    Fits are shared rather than repeated: the trained model depends only on the
    *training* labels, so one fit per (replicate, rate, training fraction) serves
    every validation fraction. That is what makes the replicate count affordable.
    """
    thr = float(cfg["kill_criteria"]["mikania_vs_native_min_accuracy"])
    sites = sorted(set(data["groups"].tolist()))
    holdout = holdout_site or sites[-1]
    te = data["groups"] == holdout
    tr = ~te

    ids = class_ids(cfg)
    tgt = ids[cfg["confusable_pair"]["target"]]
    nat = [ids[k] for k in cfg["confusable_pair"]["natives"]]

    def _bal_acc(y_ref, pred):
        m = np.isin(y_ref, [tgt] + nat)
        if not m.any():
            return float("nan")
        t = (y_ref[m] == tgt).astype(int)
        p = (pred[m] == tgt).astype(int)
        tp = int(((p == 1) & (t == 1)).sum()); fn = int(((p == 0) & (t == 1)).sum())
        fp = int(((p == 1) & (t == 0)).sum()); tn = int(((p == 0) & (t == 0)).sum())
        return 0.5 * (tp / max(tp + fn, 1) + tn / max(tn + fp, 1))

    # Truth: the verdict a programme with fully certified labels would reach.
    base = make_model(model_name, cfg)
    base.fit(data["X"][tr], data["y"][tr])
    true_acc = _bal_acc(data["y"][te], base.predict(data["X"][te]))
    true_verdict = bool(true_acc >= thr)

    arms = ("none", "train_only", "val_only", "both")
    correct = {a: {f: 0 for f in fractions} for a in arms}
    acc_sum = {a: {f: [] for f in fractions} for a in arms}
    n_trials = 0
    n_val_units = 0

    for rate in rates:
        for _ in range(replicates):
            n_trials += 1
            c_tr = corrupt_labels(data["y"][tr], cfg, rate, gen, bias=bias,
                                  row=data["row"][tr], col=data["col"][tr],
                                  site=data["groups"][tr])
            c_te = corrupt_labels(data["y"][te], cfg, rate, gen, bias=bias,
                                  row=data["row"][te], col=data["col"][te],
                                  site=data["groups"][te])
            n_val_units = len(np.unique(c_te["unit_id"]))

            # One fit per training fraction; reused across every validation fraction.
            preds = {}
            for f_tr in sorted(set([0.0] + list(fractions))):
                ytr = _certify(data["y"][tr], c_tr["y_observed"],
                               c_tr["unit_id"], f_tr, gen)["y"]
                m = make_model(model_name, cfg)
                m.fit(data["X"][tr], ytr)
                preds[f_tr] = m.predict(data["X"][te])

            # One certified validation label set per fraction, shared across arms.
            yte = {f: _certify(data["y"][te], c_te["y_observed"], c_te["unit_id"], f, gen)["y"]
                   for f in sorted(set([0.0] + list(fractions)))}

            for f in fractions:
                for arm in arms:
                    f_tr = f if arm in ("train_only", "both") else 0.0
                    f_te = f if arm in ("val_only", "both") else 0.0
                    acc = _bal_acc(yte[f_te], preds[f_tr])
                    acc_sum[arm][f].append(acc)
                    correct[arm][f] += int(bool(acc >= thr) == true_verdict)

    out_arms = {a: [{
        "fraction_certified": float(f),
        "p_correct_decision": round(correct[a][f] / max(n_trials, 1), 4),
        "mean_reported_accuracy": round(float(np.nanmean(acc_sum[a][f])), 4),
        "sd_reported_accuracy": round(float(np.nanstd(acc_sum[a][f])), 4),
    } for f in fractions] for a in arms}

    # Smallest validation-certification fraction that is right in every trial and
    # stays right for every larger fraction. A threshold that flickers is not a
    # threshold anyone can plan a budget against.
    val = out_arms["val_only"]
    min_frac = next((p["fraction_certified"] for i, p in enumerate(val)
                     if all(q["p_correct_decision"] >= 1.0 for q in val[i:])), None)

    return {
        "rates": list(rates), "replicates": replicates, "n_trials": n_trials,
        "holdout_site": holdout, "threshold": thr,
        "true_accuracy": round(float(true_acc), 4),
        "true_verdict": "PASS" if true_verdict else "FAIL",
        "arms": out_arms,
        "min_validation_fraction_for_correct_decision": min_frac,
        "n_validation_specimens": int(n_val_units),
        "interpretation": (
            "The go/no-go verdict is computed on the hold-out, so it depends on the "
            "VALIDATION labels being right and barely at all on the training labels. "
            "Certifying the training set alone cannot repair the decision, because the "
            "number the decision is read from is never touched."),
    }


def disagreement_targeting(data: Dict[str, np.ndarray], cfg: Dict[str, Any],
                           gen: np.random.Generator,
                           rate: Optional[float] = None,
                           bias: Optional[float] = None,
                           model_name: str = "rf",
                           budgets: Sequence[float] = (0.1, 0.2, 0.3, 0.5)) -> Dict[str, Any]:
    """
    Spend the sequencing budget where the errors actually are.

    A classifier trained on mostly-correct labels overrides the minority that are
    wrong — stage 13 measured exactly that. The corollary is useful: the
    specimens the model *disagrees with* are enriched for genuine label errors, so
    they are the ones worth sequencing.

    Specimens are ranked by the fraction of their pixels the model assigns to a
    class other than their label, using out-of-fold predictions so a specimen is
    never scored by a model that trained on it. Enrichment is reported against the
    random-sampling baseline, which is what §3.4's "certify everything" plan
    degenerates to when the budget is short.

    This is standard active label cleaning. It is included because it changes the
    economics: it means partial certification is far better than proportionally
    cheaper, which is what makes fix 1 affordable.
    """
    rate = float(cfg["molecular"]["field_error"]["misid_rate_sterile"] if rate is None else rate)
    sites = sorted(set(data["groups"].tolist()))

    c = corrupt_labels(data["y"], cfg, rate, gen, bias=bias,
                       row=data["row"], col=data["col"], site=data["groups"])
    y_obs, unit = c["y_observed"], c["unit_id"]

    # Out-of-fold predictions by site, so no specimen is scored by a model that saw it.
    pred = np.empty_like(y_obs)
    for s in sites:
        te = data["groups"] == s
        m = make_model(model_name, cfg)
        m.fit(data["X"][~te], y_obs[~te])
        pred[te] = m.predict(data["X"][te])

    units = np.unique(unit)
    rows = []
    for u in units:
        m = unit == u
        rows.append({
            "unit": int(u),
            "disagreement": float((pred[m] != y_obs[m]).mean()),
            "corrupted": bool(c["corrupted_mask"][m].any()),
            "n_px": int(m.sum()),
        })
    order = sorted(rows, key=lambda r: -r["disagreement"])
    n_corrupt = sum(1 for r in rows if r["corrupted"])
    base_rate = n_corrupt / max(len(rows), 1)

    curve = []
    for b in budgets:
        k = max(int(round(b * len(order))), 1)
        top = order[:k]
        found = sum(1 for r in top if r["corrupted"])
        precision = found / max(k, 1)
        curve.append({
            "budget_fraction": float(b),
            "n_sequenced": k,
            "errors_found": found,
            "errors_total": n_corrupt,
            "recall": round(found / max(n_corrupt, 1), 4),
            "precision": round(precision, 4),
            "enrichment_vs_random": round(precision / max(base_rate, 1e-9), 2),
        })

    return {
        "rate": rate,
        "n_specimens": len(rows),
        "n_corrupted": n_corrupt,
        "base_rate": round(base_rate, 4),
        "curve": curve,
        "interpretation": (
            "Ranking specimens by model-label disagreement concentrates the genuine "
            "label errors into the top of the list, so a partial sequencing budget "
            "recovers far more than its share of them. Random sampling recovers "
            "exactly its share, by construction."),
    }


# ==========================================================================
# FIX 2 — close the public reference gaps
# ==========================================================================
def reference_gap_plan(coverage: Dict[str, Any], cfg: Dict[str, Any],
                       occurrence_counts: Optional[Dict[str, int]] = None
                       ) -> Dict[str, Any]:
    """
    Turn the measured coverage matrix into a costed, prioritised sequencing plan.

    Two prioritisation inputs, and the second is the one that stops this becoming
    a completionist exercise:

    **Operational need** — how many sequences short of the §13.3 floor a
    taxon/locus is.

    **Hong Kong relevance** — ``occurrence_counts`` from GBIF. A taxon with one
    HK record in 1991 is not an operational discrimination problem however thin
    its reference coverage is, and spending the Phase 0 molecular budget on it
    would be closing a gap nobody falls into.
    """
    mol = cfg["molecular"]
    m = mol["costs_hkd"]
    floor = int(mol["identification"]["min_reference_seqs_per_species"])
    n_loci_needed = int(mol["release"]["min_loci_agreeing"])
    matrix = coverage.get("matrix", {})
    loci = [l["key"] for l in mol["loci"]]
    core = {l["key"] for l in mol["loci"] if l.get("role") == "core"}

    # Per-sequence cost: one extraction shared across loci, one PCR and a
    # bidirectional Sanger pair per locus.
    per_seq = m["pcr_per_reaction"] + 2 * m["sanger_per_reaction"]

    items = []
    for taxon, row in matrix.items():
        deficits = {L: max(floor - int(row.get(L, 0)), 0) for L in loci}
        usable = [L for L in loci if int(row.get(L, 0)) >= floor]
        has_core = any(L in core for L in usable)
        certifiable = len(usable) >= n_loci_needed and has_core
        if certifiable:
            continue

        # Cheapest route to certifiability: fill the loci that are closest to the
        # floor, ensuring at least one core locus among them.
        need = sorted((L for L in loci if deficits[L] > 0),
                      key=lambda L: (L not in core if not has_core else False, deficits[L]))
        plan, gained = [], list(usable)
        for L in need:
            if len(gained) >= n_loci_needed and (has_core or any(x in core for x in gained)):
                break
            plan.append({"locus": L, "sequences_needed": deficits[L]})
            gained.append(L)

        n_seq = sum(p["sequences_needed"] for p in plan)
        n_vouchers = max((max((p["sequences_needed"] for p in plan), default=0)), 0)
        cost = n_vouchers * m["extraction_per_sample"] + n_seq * per_seq

        occ = None if occurrence_counts is None else occurrence_counts.get(taxon)
        items.append({
            "taxon": taxon,
            "current": {L: int(row.get(L, 0)) for L in loci},
            "usable_loci": usable,
            "has_usable_core_locus": has_core,
            "plan": plan,
            "sequences_needed": n_seq,
            "vouchers_needed": n_vouchers,
            "cost_hkd": round(cost),
            "hk_occurrence_records": occ,
            "priority": ("low — not an operational HK discrimination problem"
                         if occ is not None and occ <= 2 else
                         ("high" if occ is None or occ > 50 else "medium")),
        })

    items.sort(key=lambda x: (0 if x["priority"].startswith("high") else
                              (1 if x["priority"].startswith("medium") else 2),
                              -x["sequences_needed"]))
    high = [i for i in items if i["priority"].startswith("high")]

    return {
        "n_taxa_uncertifiable": len(items),
        "items": items,
        "total_cost_hkd": round(sum(i["cost_hkd"] for i in items)),
        "high_priority_cost_hkd": round(sum(i["cost_hkd"] for i in high)),
        "cost_per_sequence_hkd": round(per_seq),
        "note": ("Costs are consumables only, from the MODELLED figures in §13.9, and "
                 "assume the vouchers are collected on field visits already being made. "
                 "They exclude collection time and lab access, both of which are already "
                 "in the §7.3 envelope."),
    }


# ==========================================================================
# FIX 3 — the band prior, applied where it survives
# ==========================================================================
class PriorScaler(BaseEstimator, TransformerMixin):
    """
    Multiply features by a fixed weight vector — placed **after** ``StandardScaler``.

    That placement is the whole fix. Before the scaler, the weights are undone
    exactly. After it, for a model with an L2 penalty, scaling standardised
    feature *j* by *w_j* is algebraically equivalent to penalising its coefficient
    by λ/w_j² — an informative prior, which is what §3.3(a) wanted and did not
    get.
    """

    def __init__(self, weights: Optional[np.ndarray] = None):
        self.weights = weights

    def fit(self, X, y=None):
        w = np.ones(np.asarray(X).shape[1]) if self.weights is None else np.asarray(self.weights)
        if w.size != np.asarray(X).shape[1]:
            raise ValueError(f"prior has {w.size} weights for {np.asarray(X).shape[1]} features")
        self.w_ = w
        return self

    def transform(self, X):
        return np.asarray(X, dtype=float) * self.w_[None, :]


def prior_model(weights: Optional[np.ndarray], cfg: Dict[str, Any],
                C: float = 0.05) -> Pipeline:
    """
    Penalised linear model with an optional band prior.

    Deliberately **not** the project's default random forest, and deliberately
    without PCA. Both exclusions are requirements rather than preferences:

    * a tree ensemble is invariant to monotone per-feature rescaling, so it cannot
      express a band prior at all;
    * PCA rotates the band basis away, destroying the identity in which the prior
      is written.

    ``C`` is small (strong regularisation) because the prior only does work when
    the penalty binds. At large ``C`` the model is effectively unpenalised and
    every weighting scheme converges to the same solution — which, if you do not
    notice it, looks exactly like "the prior does not help".
    """
    return Pipeline([
        ("scale", StandardScaler()),
        ("prior", PriorScaler(weights)),
        ("clf", LogisticRegression(C=C, max_iter=4000, class_weight="balanced",
                                   random_state=cfg["project"]["random_seed"])),
    ])


def evaluate_prior(X: np.ndarray, y: np.ndarray, site: np.ndarray,
                   cfg: Dict[str, Any], w_prior: np.ndarray,
                   gen: np.random.Generator, n_random: int = 12,
                   C: float = 0.05) -> Dict[str, Any]:
    """
    Leave-one-site-out comparison of uniform, prior and random weightings.

    The random arm is the control that makes the result mean something: a prior
    that beats uniform weighting but not a *random* weighting of the same
    magnitude distribution has demonstrated only that regularisation is uneven,
    not that the biology was informative. Random vectors are built by permuting
    the prior itself, so the comparison holds the weight distribution fixed and
    varies only which band gets which weight.
    """
    ids = class_ids(cfg)
    tgt = ids[cfg["confusable_pair"]["target"]]
    nat = [ids[k] for k in cfg["confusable_pair"]["natives"]]
    sites = sorted(set(np.asarray(site).tolist()))

    def _loso(w):
        out = []
        for s in sites:
            te = np.asarray(site) == s
            m = prior_model(w, cfg, C=C)
            m.fit(X[~te], y[~te])
            pred = m.predict(X[te])
            mask = np.isin(y[te], [tgt] + nat)
            if not mask.any():
                continue
            t = (y[te][mask] == tgt).astype(int)
            p = (pred[mask] == tgt).astype(int)
            tp = int(((p == 1) & (t == 1)).sum()); fn = int(((p == 0) & (t == 1)).sum())
            fp = int(((p == 1) & (t == 0)).sum()); tn = int(((p == 0) & (t == 0)).sum())
            out.append(0.5 * (tp / max(tp + fn, 1) + tn / max(tn + fp, 1)))
        return np.asarray(out)

    uni = _loso(None)
    pri = _loso(w_prior)
    rnd = [_loso(gen.permutation(w_prior)) for _ in range(n_random)]
    rnd_mean = np.mean(rnd, axis=0)

    paired_uni = pri - uni
    paired_rnd = pri - rnd_mean

    def _summ(a):
        return {"mean": round(float(a.mean()), 4), "sd": round(float(a.std()), 4),
                "per_site": np.round(a, 4).tolist()}

    beat = sum(1 for r in rnd if pri.mean() > r.mean())
    se = float(np.std(paired_rnd, ddof=1) / np.sqrt(paired_rnd.size)) if paired_rnd.size > 1 else float("nan")

    return {
        "C": C,
        "uniform": _summ(uni),
        "prior": _summ(pri),
        "random_permuted_mean": _summ(rnd_mean),
        "n_random_permutations": n_random,
        "delta_vs_uniform_pp": round(100.0 * float(paired_uni.mean()), 3),
        "delta_vs_random_pp": round(100.0 * float(paired_rnd.mean()), 3),
        "se_vs_random_pp": round(100.0 * se, 3) if np.isfinite(se) else None,
        "beat_n_of_random": f"{beat}/{n_random}",
        "supported": bool(np.isfinite(se) and 100.0 * float(paired_rnd.mean()) > 2 * 100.0 * se),
    }


__all__ = ["certification_allocation", "disagreement_targeting", "reference_gap_plan",
           "PriorScaler", "prior_model", "evaluate_prior"]
