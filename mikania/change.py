"""
Post-treatment efficacy verification — deliverable 3, and the recurring revenue.

Proposal §3.1:

    "Re-flight of treated sites at fixed intervals, producing a quantified
     re-emergence rate per site and per treatment method. This is the
     recurring-revenue engine and the deliverable AFCD currently cannot produce
     at all."

And §2.1(c) on why it is unserved:

    "Government has acknowledged in LegCo that re-emergence of Mikania after
     weeding occurs, and that departments arrange weeding again as soon as
     practicable. There is no systematic quantification of *where* re-emergence
     occurs, *how fast*, or *which treatment sites are failing.* Money is spent
     on clearance without a measurement loop."

This module closes that loop. Given two epochs over the same ground it
computes, per treatment unit, whether the treatment cleared the infestation and
whether it came back — then aggregates to a per-method re-emergence rate and a
cost-effectiveness ranking.

The statistical trap, and how it is avoided
-------------------------------------------
Naive change detection differences two classified maps and calls the result
change. That compounds both maps' classification error, so with 80% accurate
maps roughly a third of "detected change" is noise. Worse, the errors are
spatially correlated, so the noise clusters and *looks* like real patches.

Two defences here:

1. change is computed on the continuous abundance fraction, not on hard class
   labels, so a pixel drifting from 0.55 to 0.48 registers as small rather than
   flipping category;
2. a minimum detectable change is derived from the classifier's own measured
   error and enforced as a floor — anything smaller is reported as "no
   significant change", not as a number.

Claiming a re-emergence rate below the noise floor would be the fastest possible
way to lose a government client, because it is the one deliverable they can
check against their own field records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage


# ==========================================================================
# Detection floor
# ==========================================================================
def minimum_detectable_change(classifier_accuracy: float,
                              abundance_rmse: float = 0.12,
                              n_pixels: int = 100,
                              z: float = 1.96) -> float:
    """
    Smallest coverage-fraction change we can honestly claim for a patch of
    ``n_pixels``.

    Combines two error sources:

    * abundance estimation error (the unmixing residual, ``abundance_rmse``);
    * classification error, which mislabels a fraction of pixels entirely.

    Averaging over a patch reduces the random part as 1/sqrt(n), which is why
    per-polygon efficacy is defensible where per-pixel efficacy is not. The
    classification term does not average away as fast, because its errors are
    spatially correlated — so it is deliberately included at full strength
    rather than divided by sqrt(n).
    """
    err_cls = (1.0 - float(classifier_accuracy))
    sigma = np.sqrt((abundance_rmse ** 2) / max(n_pixels, 1) + (0.5 * err_cls) ** 2)
    return float(z * sigma)


# ==========================================================================
# Pairwise change
# ==========================================================================
def change_map(before: np.ndarray, after: np.ndarray,
               floor: float = 0.10) -> Dict[str, np.ndarray]:
    """
    Per-pixel change in Mikania coverage fraction between two epochs.

    Returns ``delta`` (signed), ``significant`` (mask above the floor),
    ``cleared`` (was infested, now below reporting threshold) and ``emerged``
    (was clear, now infested — new incursion, the cheapest thing to catch).
    """
    b = np.nan_to_num(np.asarray(before, dtype=np.float64), nan=0.0)
    a = np.nan_to_num(np.asarray(after, dtype=np.float64), nan=0.0)
    delta = a - b
    significant = np.abs(delta) >= floor
    return {
        "delta": delta,
        "significant": significant,
        "cleared": (b > 0.10) & (a <= 0.10) & significant,
        "emerged": (b <= 0.10) & (a > 0.10) & significant,
        "persisted": (b > 0.10) & (a > 0.10),
    }


def unit_efficacy(units: List[Dict[str, Any]],
                  before: np.ndarray, after: np.ndarray,
                  labels: np.ndarray,
                  treatment_assignment: Dict[str, str],
                  classifier_accuracy: float,
                  cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Per-treatment-unit efficacy record.

    ``labels`` is the connected-component labelling that produced ``units``;
    ``treatment_assignment`` maps unit_id -> method key. Each record states
    whether the observed change exceeded that unit's own detection floor, and
    when it did not, says so instead of quoting a number.
    """
    out = []
    for u in units:
        idx = int(u["unit_id"].split("-")[-1])
        m = labels == idx
        n = int(m.sum())
        if n == 0:
            continue

        b = float(np.nanmean(before[m]))
        a = float(np.nanmean(after[m]))
        floor = minimum_detectable_change(classifier_accuracy, n_pixels=n)
        delta = a - b
        significant = abs(delta) >= floor

        method = treatment_assignment.get(u["unit_id"], "no_treatment")
        spec = cfg["efficacy"]["methods"][method]

        # OPERATIONAL DEFINITION OF RE-EMERGENCE.
        # Not "worse than baseline" — that test almost never fires, because a
        # treatment that removes 92% of the biomass still leaves the unit far
        # below baseline even when the vine is visibly back at the margins. AFCD's
        # question is simply "has it come back?", so re-emergence is presence
        # above the reporting threshold inside a unit that was treated. Net
        # reduction is reported alongside, since both matter: one drives the
        # re-treatment schedule, the other measures whether the money worked.
        present_threshold = float(cfg["unmixing"]["min_abundance_report"])
        treated_unit = method != "no_treatment"
        reemerged = bool(treated_unit and a >= present_threshold)

        rec = {
            "unit_id": u["unit_id"],
            "site": u["site"],
            "area_ha": u["area_ha"],
            "n_pixels": n,
            "treatment": method,
            "coverage_before": round(b, 4),
            "coverage_after": round(a, 4),
            "delta": round(delta, 4),
            "detection_floor": round(floor, 4),
            "significant": bool(significant),
            "reemerged": reemerged,
            "presence_threshold": present_threshold,
            "reduction_pct": round(100.0 * (b - a) / max(b, 1e-6), 1) if b > 0 else None,
            "cost_hkd": round(u["area_ha"] * spec["cost_hkd_per_ha"]),
            "verdict": (
                "no significant change (below detection floor)" if not significant
                else "failed — at or above baseline" if delta >= 0
                else "re-emergence (reduced but present)" if reemerged
                else "cleared and holding"
            ),
        }
        if b > 0 and significant:
            # Ecological damage averted per dollar — the number a fixed-budget
            # client optimises, and the reason to measure efficacy at all.
            rec["ha_cleared_per_100k_hkd"] = round(
                (u["area_ha"] * max(b - a, 0.0)) / max(rec["cost_hkd"], 1) * 100_000, 3)
        out.append(rec)
    return out


def method_summary(records: List[Dict[str, Any]],
                   cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate per-unit records into a per-method verdict.

    This is the table that answers AFCD's real question — "which clearance
    methods and which sites are failing?" (§6.1 point 3) — and the one that
    turns a one-off survey into an annual contract.
    """
    by_method: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        by_method.setdefault(r["treatment"], []).append(r)

    out = {}
    for method, recs in by_method.items():
        sig = [r for r in recs if r["significant"]]
        reemerged = [r for r in recs if r.get("reemerged")]
        area = sum(r["area_ha"] for r in recs)
        cost = sum(r["cost_hkd"] for r in recs)
        deltas = [r["delta"] for r in sig]

        out[method] = {
            "n_units": len(recs),
            "n_significant": len(sig),
            "n_reemerged": len(reemerged),
            "observed_reemergence_rate": (len(reemerged) / len(recs)) if recs else None,
            "mean_reduction_pct": (round(float(np.mean(
                [r["reduction_pct"] for r in recs if r["reduction_pct"] is not None])), 1)
                if any(r["reduction_pct"] is not None for r in recs) else None),
            "configured_reemergence_rate": cfg["efficacy"]["methods"][method]["reemergence_rate"],
            "total_area_ha": round(area, 3),
            "total_cost_hkd": cost,
            "mean_coverage_change": round(float(np.mean(deltas)), 4) if deltas else None,
            "cost_per_ha_hkd": cfg["efficacy"]["methods"][method]["cost_hkd_per_ha"],
            "note": (
                "Observed rate is measured from the two simulated epochs; the "
                "configured rate is the simulator's input. They differ because "
                "detection is imperfect — which is the point: this is what the "
                "measurement loop would actually recover from real re-flights."
            ),
        }

    ranked = sorted(
        [(k, v) for k, v in out.items()
         if k != "no_treatment" and v["observed_reemergence_rate"] is not None],
        key=lambda kv: (kv[1]["observed_reemergence_rate"],
                        kv[1]["cost_per_ha_hkd"]))
    return {"by_method": out, "recommended_order": [k for k, _ in ranked]}


def assign_treatments(units: List[Dict[str, Any]], cfg: Dict[str, Any],
                      gen: np.random.Generator) -> Dict[str, str]:
    """
    Allocate a treatment method to each unit for the demonstration.

    Deliberately *not* random: AFCD would send the cheapest adequate method to
    easy sites and the expensive one to the worst. Reproducing that assignment
    logic matters, because it creates exactly the confounding that makes naive
    efficacy comparison misleading — the expensive method looks worse simply
    because it was sent to the harder sites. The report flags the confound
    rather than pretending it away.
    """
    # Keyed off the CONFIG action bands rather than hardcoded severity numbers,
    # so retuning severity.bands during a negotiation with AFCD cannot silently
    # desynchronise the treatment plan from the action the map recommends.
    by_band = {
        "Urgent": "cut_stump_herbicide",
        "Priority": "cut_and_tarp",
        "Schedule": "manual_pull",
        # Low-severity units are left as untreated controls — without a control
        # there is no way to separate treatment effect from natural fluctuation.
        "Monitor": "no_treatment",
    }
    fallback = "manual_pull"
    return {u["unit_id"]: by_band.get(u["band"], fallback) for u in units}


def apply_treatment_outcome(mikania_fraction: np.ndarray, labels: np.ndarray,
                            units: List[Dict[str, Any]],
                            assignment: Dict[str, str],
                            cfg: Dict[str, Any],
                            gen: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """
    Simulate the ground truth of what treatment actually did, for the re-flight.

    Returns ``(new_fraction, treated_mask)``. Re-emergence is seeded from patch
    margins rather than uniformly, because that is how Mikania actually returns —
    from surviving root fragments and the surrounding seed bank at the edges.
    """
    frac = np.asarray(mikania_fraction, dtype=np.float64).copy()
    treated = np.zeros(frac.shape, dtype=bool)

    for u in units:
        idx = int(u["unit_id"].split("-")[-1])
        m = labels == idx
        if not m.any():
            continue
        method = assignment.get(u["unit_id"], "no_treatment")
        spec = cfg["efficacy"]["methods"][method]
        if method == "no_treatment":
            # Untreated control: continues to spread.
            frac[m] = np.clip(frac[m] * (1.0 + 0.18 * gen.random(int(m.sum()))), 0.0, 1.0)
            continue

        treated |= m
        frac[m] *= (1.0 - float(spec["clearance"]))

        # Re-emergence, from the margin inward.
        if gen.random() < float(spec["reemergence_rate"]):
            edge = m & ~ndimage.binary_erosion(m, iterations=2)
            n_edge = int(edge.sum())
            if n_edge:
                strength = 0.25 + 0.45 * gen.random()
                frac[edge] = np.clip(frac[edge] + strength * gen.random(n_edge), 0.0, 1.0)

    return np.clip(frac, 0.0, 1.0), treated
