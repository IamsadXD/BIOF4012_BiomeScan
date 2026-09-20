"""
The genomic desk study — proposal §3.3, and Next Action 0.

    "Run the genomic desk study. Analyse the published *M. micrantha* /
     *M. cordata* genomic and transcriptomic resources to produce a ranked,
     falsifiable list of spectral regions predicted to carry species signal
     (§3.3). Zero capital, a few weeks of analyst time, uses only open data, and
     it determines what the field campaign should measure. **This is now the
     true first action.**"                                       — proposal §10.0

This module is that analysis expressed as code rather than as a memo, which buys
three things a memo does not:

1. **The evidence chain is traversable.** Every spectral prediction resolves to
   named traits, which resolve to named published findings, each with a citation
   and an evidence tier. Confidence is propagated down the chain and floored by
   its weakest link, so no prediction can be reported at higher confidence than
   the inference it actually rests on. Proposal §3.2 is blunt about why this
   matters: the molecular column of its mechanism table "states hypotheses, not
   established leaf-optical measurements".

2. **The predictions are executable.** Each one names a measurement function and
   a direction of effect, so :func:`evaluate_predictions` can run it against the
   ground spectral library and return SUPPORTED / REFUTED / NOT_SUPPORTED /
   UNDERPOWERED. §3.2 requires this: "rows that fail should be struck rather
   than quietly retained." A row can only be struck if something tried to strike
   it.

3. **The ranking feeds the classifier.** :func:`band_prior_weights` turns the
   ranked predictions into a per-band weight vector, which is §3.3(a) —
   "band prioritisation becomes hypothesis-driven ... this reduces overfitting
   risk on a small Phase 0 training set" — made operational instead of asserted.
   Whether the weighting actually helps is then *measured* (stage 00 reports it),
   because a prior that does not improve out-of-sample performance is a story,
   not a method.

The distinction this module is most careful about
-------------------------------------------------
Two different rankings come out of the same evidence, and conflating them would
be a real analytical error:

``biological_score``   how well-supported the prediction is by the published
                       literature. Ignores whether we could measure it from a
                       drone at 90 m over a Hong Kong hillside.
``operational_score``  the same, discounted by ``nuisance_exposure`` — how badly
                       the field confounders in ``config.nuisance`` corrupt that
                       particular feature.

P7 (NIR plateau amplitude) is the worked example of why both are needed. It is
biologically well-supported and operationally close to useless, because leaf area
index, leaf angle and slope move it far more than species does. A desk study
reporting only the biological ranking would send the field campaign to measure
the wrong thing.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import yaml

from .config import PATHS
from .features import green_peak_position, red_edge_position

# Verdict vocabulary, fixed here so the report, the figures and the platform all
# use the same four words.
SUPPORTED = "SUPPORTED"
REFUTED = "REFUTED"                 # measured a real effect in the WRONG direction
NOT_SUPPORTED = "NOT_SUPPORTED"     # measured adequately, found no effect
UNDERPOWERED = "UNDERPOWERED"       # too few samples to say either way

# Effect size below which we call "no difference", and above which a wrong-signed
# difference is a refutation rather than noise. Cohen's d = 0.3 is a conventional
# small-effect boundary; it is stated here rather than buried because the verdict
# assignment is the most consequential judgement this module makes.
D_NEGLIGIBLE = 0.30
MIN_N_PER_GROUP = 12


# ==========================================================================
# Loading
# ==========================================================================
@lru_cache(maxsize=4)
def load_priors(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Read ``config/genomic_priors.yaml``.

    Cached like :func:`mikania.config.load_config`, and validated on the same
    principle: fail loudly on the invariants whose breach would produce quietly
    wrong science rather than an exception.
    """
    path = path or os.path.join(PATHS.config, "genomic_priors.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        pri = yaml.safe_load(fh)
    _validate(pri)
    return pri


def _validate(pri: Dict[str, Any]) -> None:
    for section in ("meta", "findings", "traits", "predictions"):
        if section not in pri:
            raise ValueError(f"genomic_priors.yaml missing section: {section}")

    finding_ids = {f["id"] for f in pri["findings"]}
    trait_ids = {t["id"] for t in pri["traits"]}
    weights = pri["meta"]["evidence_weight"]

    for t in pri["traits"]:
        missing = set(t["from"]) - finding_ids
        if missing:
            raise ValueError(f"trait {t['id']} cites unknown findings: {sorted(missing)}")

    for p in pri["predictions"]:
        missing = set(p["from"]) - trait_ids
        if missing:
            raise ValueError(f"prediction {p['id']} cites unknown traits: {sorted(missing)}")
        if p["feature"] not in MEASURES:
            raise ValueError(f"prediction {p['id']} names unmeasurable feature "
                             f"{p['feature']!r}; known: {sorted(MEASURES)}")
        if p["direction"] not in ("positive", "negative", "two_sided"):
            raise ValueError(f"prediction {p['id']} has no usable direction — "
                             "a prediction without a sign cannot be falsified")
        # A prediction must carry its own falsification test. Without one the
        # entry is an opinion, and §3.3(c) claims falsifiability as a feature.
        if not str(p.get("falsification", "")).strip():
            raise ValueError(f"prediction {p['id']} has no falsification test")

    for coll in (pri["findings"], pri["traits"], pri["predictions"]):
        for item in coll:
            if item["evidence"] not in weights:
                raise ValueError(f"{item['id']} has unknown evidence tier "
                                 f"{item['evidence']!r}")


# ==========================================================================
# Measurement functions — one per `feature` named in the priors
# ==========================================================================
# These are the falsification tests in executable form. They deliberately live
# next to the priors rather than in features.py: features.py serves the
# classifier, and these serve the desk study. A feature used for both would end
# up with two audiences and one compromise.
def _at(X: np.ndarray, wl: np.ndarray, nm: float) -> np.ndarray:
    return X[:, int(np.argmin(np.abs(wl - nm)))]


def _win(X: np.ndarray, wl: np.ndarray, lo: float, hi: float) -> Tuple[np.ndarray, np.ndarray]:
    m = (wl >= lo) & (wl <= hi)
    return X[:, m], wl[m]


def m_red_edge_position(X, wl, **kw) -> np.ndarray:
    """P1 — wavelength of maximum first derivative across the red edge."""
    return red_edge_position(X, wl, window=(680.0, 760.0), method="derivative")


def m_green_peak_position(X, wl, **kw) -> np.ndarray:
    """P3 — wavelength of the green reflectance maximum."""
    return green_peak_position(X, wl, window=(520.0, 600.0))


def m_nir_to_red_shape(X, wl, **kw) -> np.ndarray:
    """
    P2 — NIR plateau height relative to red absorption depth.

    The stem-photosynthesis prediction. Photosynthetic stem tissue carries
    chlorophyll (so it absorbs in the red like a leaf) but has little spongy
    mesophyll (so it scatters far less in the NIR). A canopy patch mixing leaf
    and green stem therefore returns less NIR *per unit of red absorption* than a
    pure-leaf patch of the same greenness.

    Formulated as a ratio of two quantities that scale together under
    illumination change, so the measure is a shape rather than an amplitude —
    which is the entire reason §3.2 puts this row in the table and expects it to
    survive the field confounders that destroy P7.
    """
    nir, _ = _win(X, wl, 780.0, 900.0)
    plateau = nir.mean(axis=1)
    # Red well depth against a 620-760 nm shoulder-to-shoulder continuum.
    r620, r760, r675 = _at(X, wl, 620.0), _at(X, wl, 760.0), _at(X, wl, 675.0)
    cont = r620 + (r760 - r620) * (675.0 - 620.0) / (760.0 - 620.0)
    depth = 1.0 - r675 / np.maximum(cont, 1e-8)
    return plateau / np.maximum(depth, 1e-6)


def m_red_edge_derivative_shape(X, wl, **kw) -> np.ndarray:
    """
    P4 — shape of the red edge beyond its peak position.

    Reduced to a scalar as the *skew* of the first-derivative profile across
    690-750 nm: the derivative-weighted mean wavelength minus the derivative
    peak wavelength. A symmetric red edge gives ~0; asymmetry from a second,
    offset chlorophyll pool (or from mixed leaf/stem tissue) gives a nonzero
    value.

    P4's declared direction is ``two_sided`` because a shape difference has no
    natural sign, and :func:`test_prediction` handles that case by testing
    magnitude only — a two-sided prediction is weaker evidence and is scored as
    such rather than being allowed to win on a technicality.
    """
    sub, wsub = _win(X, wl, 690.0, 750.0)
    d = np.gradient(sub, wsub, axis=1)
    d = np.clip(d, 0.0, None)
    tot = d.sum(axis=1)
    centroid = (d * wsub).sum(axis=1) / np.maximum(tot, 1e-12)
    peak = wsub[np.argmax(d, axis=1)]
    return centroid - peak


def m_carotenoid_depth(X, wl, **kw) -> np.ndarray:
    """P5 — continuum-removed absorption depth over the carotenoid region."""
    r450, r520 = _at(X, wl, 450.0), _at(X, wl, 520.0)
    sub, wsub = _win(X, wl, 470.0, 520.0)
    # (n_samples, 1) endpoints against a (1, n_window) wavelength ramp: the
    # continuum line is per-spectrum, so both axes have to broadcast.
    frac = ((wsub - 450.0) / (520.0 - 450.0))[None, :]
    cont = r450[:, None] + (r520 - r450)[:, None] * frac
    return 1.0 - (sub / np.maximum(cont, 1e-8)).mean(axis=1)


def m_anthocyanin_shoulder(X, wl, **kw) -> np.ndarray:
    """P6 — reflectance shoulder ratio across the anthocyanin-sensitive region."""
    return _at(X, wl, 550.0) / np.maximum(_at(X, wl, 580.0), 1e-8)


def m_nir_plateau(X, wl, **kw) -> np.ndarray:
    """P7 — mean NIR plateau reflectance. The amplitude feature, kept as a control."""
    sub, _ = _win(X, wl, 780.0, 900.0)
    return sub.mean(axis=1)


def m_water_band_depth(X, wl, **kw) -> np.ndarray:
    """P8 — depth of the ~970 nm leaf water feature against a 900/1000 nm continuum."""
    r900, r1000, r970 = _at(X, wl, 900.0), _at(X, wl, 1000.0), _at(X, wl, 970.0)
    cont = r900 + (r1000 - r900) * (970.0 - 900.0) / (1000.0 - 900.0)
    return 1.0 - r970 / np.maximum(cont, 1e-8)


MEASURES = {
    "red_edge_position": m_red_edge_position,
    "green_peak_position": m_green_peak_position,
    "nir_to_red_shape": m_nir_to_red_shape,
    "red_edge_derivative_shape": m_red_edge_derivative_shape,
    "carotenoid_depth": m_carotenoid_depth,
    "anthocyanin_shoulder": m_anthocyanin_shoulder,
    "nir_plateau": m_nir_plateau,
    "water_band_depth": m_water_band_depth,
}

# Which sensor tier could compute each measure, reusing the honesty rule from
# features.SENSOR_REQUIREMENT: a feature is 'hyperspectral' only if it needs a
# band no 5-band sensor carries, or sub-band resolution of a feature POSITION.
MEASURE_SENSOR: Dict[str, str] = {
    "red_edge_position": "hyperspectral",
    "green_peak_position": "hyperspectral",
    "nir_to_red_shape": "multispectral",       # red + NIR bands suffice for the ratio
    "red_edge_derivative_shape": "hyperspectral",
    "carotenoid_depth": "hyperspectral",
    "anthocyanin_shoulder": "hyperspectral",
    "nir_plateau": "multispectral",            # any ag sensor has a NIR band
    "water_band_depth": "hyperspectral",       # 970 nm — no ag sensor carries it
}


def measure(feature: str, X: np.ndarray, wl: np.ndarray) -> np.ndarray:
    """Evaluate one named prediction measure on a (n_samples, n_bands) matrix."""
    if feature not in MEASURES:
        raise KeyError(f"unknown prediction measure {feature!r}")
    return np.asarray(MEASURES[feature](np.asarray(X, dtype=np.float64),
                                        np.asarray(wl, dtype=np.float64)),
                      dtype=np.float64)


# ==========================================================================
# Evidence chains and scoring
# ==========================================================================
def _index(pri: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for coll in ("findings", "traits", "predictions"):
        for item in pri[coll]:
            out[item["id"]] = item
    return out


def evidence_chain(pred_id: str, pri: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Resolve one prediction to the traits and published findings behind it.

    Returns the full chain plus its *weakest link* — the lowest evidence weight
    anywhere along it. Reporting the weakest link rather than the average is the
    conservative choice and the correct one: a chain that passes through one
    unmeasured inferential step is exactly as speculative as that step,
    regardless of how solid the genomics at the far end is.
    """
    pri = pri or load_priors()
    idx = _index(pri)
    w = pri["meta"]["evidence_weight"]

    pred = idx[pred_id]
    traits, findings = [], {}
    for tid in pred["from"]:
        t = idx[tid]
        traits.append({"id": t["id"], "trait": t["trait"], "evidence": t["evidence"],
                       "weight": w[t["evidence"]], "rationale": t["rationale"].strip(),
                       "from": list(t["from"])})
        for fid in t["from"]:
            f = idx[fid]
            findings[fid] = {"id": f["id"], "claim": f["claim"], "evidence": f["evidence"],
                             "weight": w[f["evidence"]], "source": f["source"],
                             "url": f.get("url"), "proposal_ref": f.get("proposal_ref")}

    tiers = ([pred["evidence"]] + [t["evidence"] for t in traits]
             + [f["evidence"] for f in findings.values()])
    weakest = min(tiers, key=lambda tier: w[tier])

    return {
        "prediction_id": pred_id,
        "prediction_evidence": pred["evidence"],
        "traits": traits,
        "findings": sorted(findings.values(), key=lambda f: f["id"]),
        "n_independent_findings": len(findings),
        "weakest_link": weakest,
        "weakest_link_weight": float(w[weakest]),
    }


def score_prediction(pred_id: str, pri: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Score one prediction on the two axes described in the module docstring.

    ``biological_score``
        product of the evidence weights along the chain (prediction tier x mean
        trait tier x mean finding tier), then given a modest bonus for resting on
        more than one *independent* published finding. Independent replication is
        the reason §4.2 can describe the science as "published, replicated in
        adjacent species, and consistent" rather than as a single-paper result,
        and the score should reflect that rather than treating eight citations of
        one paper as eight pieces of evidence.

    ``operational_score``
        the same number discounted by ``nuisance_exposure``, plus a penalty for a
        ``two_sided`` direction. An unsigned prediction is harder to falsify and
        therefore worth less as a field-campaign target, and the scoring says so
        rather than letting it rank on vagueness.
    """
    pri = pri or load_priors()
    idx = _index(pri)
    w = pri["meta"]["evidence_weight"]
    pred = idx[pred_id]
    chain = evidence_chain(pred_id, pri)

    w_pred = w[pred["evidence"]]
    w_trait = float(np.mean([t["weight"] for t in chain["traits"]])) if chain["traits"] else 0.0
    w_find = float(np.mean([f["weight"] for f in chain["findings"]])) if chain["findings"] else 0.0

    # Diminishing-returns bonus: the second independent finding is worth a lot,
    # the fourth very little.
    replication = 1.0 + 0.12 * np.log1p(max(chain["n_independent_findings"] - 1, 0))

    biological = float(np.clip(w_pred * w_trait * w_find * replication, 0.0, 1.0))

    exposure = float(pred.get("nuisance_exposure", 0.5))
    direction_penalty = 0.85 if pred["direction"] == "two_sided" else 1.0
    operational = float(biological * (1.0 - exposure) * direction_penalty)

    return {
        "id": pred_id,
        "window_nm": list(pred["window_nm"]),
        "feature": pred["feature"],
        "measures": pred["measures"],
        "direction": pred["direction"],
        "expected_magnitude": pred.get("expected_magnitude"),
        "nuisance_exposure": exposure,
        "sensor_required": MEASURE_SENSOR.get(pred["feature"], "hyperspectral"),
        "proposal_row": pred.get("proposal_row"),
        "falsification": pred["falsification"].strip(),
        "why_broadband_misses": pred.get("why_broadband_misses"),
        "biological_score": round(biological, 4),
        "operational_score": round(operational, 4),
        "weakest_link": chain["weakest_link"],
        "n_independent_findings": chain["n_independent_findings"],
        "chain": chain,
    }


def rank_predictions(pri: Optional[Dict[str, Any]] = None,
                     by: str = "operational_score") -> List[Dict[str, Any]]:
    """All predictions, scored and sorted. ``by`` selects which of the two rankings."""
    pri = pri or load_priors()
    scored = [score_prediction(p["id"], pri) for p in pri["predictions"]]
    scored.sort(key=lambda s: s[by], reverse=True)
    for i, s in enumerate(scored, 1):
        s[f"rank_{by}"] = i
    return scored


# ==========================================================================
# §3.3(a) — hypothesis-driven band prioritisation
# ==========================================================================
def band_prior_weights(wl: Sequence[float],
                       pri: Optional[Dict[str, Any]] = None,
                       by: str = "operational_score",
                       floor: float = 0.25,
                       edge_softness_nm: float = 12.0) -> np.ndarray:
    """
    Turn the ranked predictions into a per-band prior weight vector.

    This is proposal §3.3(a) in one function:

        "Rather than feeding 200+ bands to a classifier and hoping feature
         selection finds something, we can weight and interrogate the regions the
         biology predicts. This reduces overfitting risk on a small Phase 0
         training set — the regime where blind feature selection fails hardest."

    Three deliberate design choices, each of which is a way of not cheating:

    ``floor``
        no band is ever weighted to zero. The priors are hypotheses; a hard zero
        would let a wrong hypothesis destroy real signal the data contains, and
        would make the whole exercise unfalsifiable — you cannot discover that
        your prior was wrong in a region you refused to look at.

    ``edge_softness_nm``
        window edges are smoothed with a logistic ramp rather than being a boxcar.
        The windows in the priors are stated to the nearest 10 nm from published
        physiology; a hard edge would assert a precision the source does not have.

    ``by``
        defaults to the *operational* ranking, not the biological one. A band that
        carries real biological signal buried under illumination nuisance
        (P7, the NIR plateau) should not be up-weighted just because the genomics
        behind it is solid.

    The returned vector is normalised to mean 1.0, so multiplying features by it
    changes their relative emphasis without changing overall scale — which keeps
    it comparable against the uniform-weight control that stage 00 runs.
    """
    pri = pri or load_priors()
    wl = np.asarray(wl, dtype=np.float64)
    w = np.zeros_like(wl)

    for s in rank_predictions(pri, by=by):
        lo, hi = s["window_nm"]
        k = edge_softness_nm
        ramp = (1.0 / (1.0 + np.exp(-(wl - lo) / k))) * (1.0 / (1.0 + np.exp((wl - hi) / k)))
        w += s[by] * ramp

    if w.max() <= 0:
        return np.ones_like(wl)
    w = floor + (1.0 - floor) * (w / w.max())
    return w / w.mean()


# ==========================================================================
# Falsification — running the predictions against measured spectra
# ==========================================================================
def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if a.size < 2 or b.size < 2:
        return float("nan")
    va, vb = a.var(ddof=1), b.var(ddof=1)
    pooled = ((a.size - 1) * va + (b.size - 1) * vb) / max(a.size + b.size - 2, 1)
    if pooled <= 0:
        return float("nan")
    return float((a.mean() - b.mean()) / np.sqrt(pooled))


def test_prediction(scored: Dict[str, Any],
                    X_target: np.ndarray, X_native: np.ndarray,
                    wl: np.ndarray,
                    site_target: Optional[np.ndarray] = None,
                    site_native: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Execute one prediction's falsification test.

    ``site_target`` / ``site_native``, when given, switch the test from a pooled
    comparison to a **site-blocked** one: the effect size is computed within each
    site and then averaged over sites. This is the same rule §5.1(6) imposes on
    the classifier, applied to the desk study, and for the same reason — the
    site random effects in ``config.site_random_effects`` are comparable in
    magnitude to the between-species differences being tested, so a pooled
    comparison across sites can manufacture or erase an effect at will.

    A pooled result is still reported alongside, because the *gap* between pooled
    and site-blocked is itself diagnostic: a large gap means the feature is
    picking up site rather than species, which is precisely the failure mode a
    field campaign needs to know about before it commits to a band.
    """
    feat = scored["feature"]
    vt = measure(feat, X_target, wl)
    vn = measure(feat, X_native, wl)

    d_pooled = _cohens_d(vt, vn)

    d_blocked, per_site = float("nan"), []
    if site_target is not None and site_native is not None:
        ds = []
        for s in sorted(set(np.asarray(site_target).tolist())
                        & set(np.asarray(site_native).tolist())):
            at = vt[np.asarray(site_target) == s]
            an = vn[np.asarray(site_native) == s]
            if at.size >= MIN_N_PER_GROUP and an.size >= MIN_N_PER_GROUP:
                d = _cohens_d(at, an)
                if np.isfinite(d):
                    ds.append(d)
                    per_site.append({"site": s, "cohens_d": round(float(d), 4),
                                     "n_target": int(at.size), "n_native": int(an.size)})
        if ds:
            d_blocked = float(np.mean(ds))

    d_used = d_blocked if np.isfinite(d_blocked) else d_pooled
    n_ok = (np.isfinite(vt).sum() >= MIN_N_PER_GROUP
            and np.isfinite(vn).sum() >= MIN_N_PER_GROUP)

    # ---- verdict --------------------------------------------------------
    direction = scored["direction"]
    if not n_ok or not np.isfinite(d_used):
        verdict, note = UNDERPOWERED, "too few finite measurements to test"
    elif abs(d_used) < D_NEGLIGIBLE:
        verdict, note = NOT_SUPPORTED, (
            f"effect present but negligible (|d| = {abs(d_used):.2f} < {D_NEGLIGIBLE})")
    elif direction == "two_sided":
        verdict, note = SUPPORTED, "magnitude test only; direction was not predicted"
    elif (direction == "positive" and d_used > 0) or (direction == "negative" and d_used < 0):
        verdict, note = SUPPORTED, "effect present and in the predicted direction"
    else:
        verdict, note = REFUTED, (
            "effect present but OPPOSITE to the predicted direction — "
            "this row should be struck from the §3.2 mechanism table, not retained")

    site_gap = (abs(d_pooled - d_blocked)
                if np.isfinite(d_pooled) and np.isfinite(d_blocked) else float("nan"))

    return {
        "id": scored["id"],
        "feature": feat,
        "window_nm": scored["window_nm"],
        "direction_predicted": direction,
        "cohens_d_pooled": None if not np.isfinite(d_pooled) else round(float(d_pooled), 4),
        "cohens_d_site_blocked": None if not np.isfinite(d_blocked) else round(float(d_blocked), 4),
        "cohens_d_used": None if not np.isfinite(d_used) else round(float(d_used), 4),
        "site_vs_pooled_gap": None if not np.isfinite(site_gap) else round(float(site_gap), 4),
        "per_site": per_site,
        "n_target": int(np.isfinite(vt).sum()),
        "n_native": int(np.isfinite(vn).sum()),
        "verdict": verdict,
        "note": note,
        "target_mean": round(float(np.nanmean(vt)), 6),
        "native_mean": round(float(np.nanmean(vn)), 6),
    }


def evaluate_predictions(X_target: np.ndarray, X_native: np.ndarray, wl: np.ndarray,
                         pri: Optional[Dict[str, Any]] = None,
                         site_target: Optional[np.ndarray] = None,
                         site_native: Optional[np.ndarray] = None,
                         by: str = "operational_score") -> List[Dict[str, Any]]:
    """Run every prediction's falsification test and merge it with its score."""
    pri = pri or load_priors()
    out = []
    for s in rank_predictions(pri, by=by):
        r = test_prediction(s, X_target, X_native, wl, site_target, site_native)
        merged = {**s, "test": r}
        # Posterior = prior confidence, updated by whether the test passed. A
        # refuted prediction keeps a small residual weight rather than going to
        # zero, because one library on one season is not a definitive refutation
        # — but it must not keep ranking as though nothing happened.
        factor = {SUPPORTED: 1.0, NOT_SUPPORTED: 0.35,
                  REFUTED: 0.15, UNDERPOWERED: 0.70}[r["verdict"]]
        merged["posterior_score"] = round(s[by] * factor, 4)
        out.append(merged)
    out.sort(key=lambda m: m["posterior_score"], reverse=True)
    return out


# ==========================================================================
# Report assembly
# ==========================================================================
def desk_study(pri: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    The desk study proper: everything derivable from the literature alone, with
    no field measurement and no capital — proposal §10.0.

    Deliberately separated from :func:`evaluate_predictions`, which needs spectra.
    This function is what an analyst can deliver in week one, and it is what
    determines what the field campaign in §7.3 item 1 should measure.
    """
    pri = pri or load_priors()
    bio = rank_predictions(pri, by="biological_score")
    ops = rank_predictions(pri, by="operational_score")

    bio_order = [p["id"] for p in bio]
    ops_order = [p["id"] for p in ops]
    # Predictions whose two ranks disagree most: the ones where "best supported"
    # and "most useful" come apart. These are the rows an evaluator should be
    # shown, because they are where a naive literature reading goes wrong.
    disagreement = sorted(
        ({"id": pid,
          "biological_rank": bio_order.index(pid) + 1,
          "operational_rank": ops_order.index(pid) + 1,
          "shift": (bio_order.index(pid) + 1) - (ops_order.index(pid) + 1)}
         for pid in bio_order),
        key=lambda d: -abs(d["shift"]))

    tier_counts: Dict[str, int] = {}
    for p in ops:
        tier_counts[p["weakest_link"]] = tier_counts.get(p["weakest_link"], 0) + 1

    return {
        "meta": pri["meta"],
        "n_findings": len(pri["findings"]),
        "n_traits": len(pri["traits"]),
        "n_predictions": len(pri["predictions"]),
        "findings": pri["findings"],
        "traits": pri["traits"],
        "ranked_operational": ops,
        "ranked_biological": bio,
        "rank_disagreement": disagreement,
        "weakest_link_counts": tier_counts,
        "acquisition_constraints": pri.get("acquisition_constraints", []),
        # The honest headline. Every chain ends in an inferential step, so nothing
        # here is established — and saying so up front is the §3.2 / Appendix B.8
        # position, not a hedge added by a nervous author.
        "headline": (
            f"{len(pri['predictions'])} falsifiable spectral predictions derived from "
            f"{len(pri['findings'])} published genomic, transcriptomic and physiological "
            f"findings via {len(pri['traits'])} inferred trait chains. Every chain "
            f"terminates in an `inferred_optical` step: no leaf-optical measurement "
            f"linking these genes to reflectance exists for Hong Kong material. "
            f"These are the measurements the Phase 0 spectroradiometer campaign "
            f"should make, ranked by what is worth measuring rather than by what "
            f"is best cited."
        ),
    }


__all__ = [
    "load_priors", "evidence_chain", "score_prediction", "rank_predictions",
    "band_prior_weights", "measure", "test_prediction", "evaluate_predictions",
    "desk_study", "MEASURES", "MEASURE_SENSOR",
    "SUPPORTED", "REFUTED", "NOT_SUPPORTED", "UNDERPOWERED",
]
