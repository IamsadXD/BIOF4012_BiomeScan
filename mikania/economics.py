"""
Coverage economics and pricing — proposal §5.3 and §7.2.

§5.3 is blunt about which number governs the business:

    "This is the binding constraint on the whole business. A 3,000 ha annual
     programme is 25-40 field days. That is achievable with one crew; 44,300 ha
     is not achievable with any crew, which is precisely why the three-tier
     funnel in §3.3 is mandatory rather than optional. Price the contract off
     the effective rate, not the raw rate, and state the assumption openly."

This module computes that rate from first principles rather than quoting the
proposal's table, so that when the two [VERIFY] items — actual sensor swath and
achievable line rate at 90 m AGL — are measured, one config edit propagates
through the coverage model, the field-day count, the contract value and the
break-even analysis together.

Every function returns its assumptions alongside its results. A coverage figure
without its swath assumption is not a number, it is a claim.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np


def coverage_model(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hectares per hour, from platform geometry.

    Chain: swath x ground speed gives the raw swept rate; sidelap and
    operational overhead reduce it to the effective rate that may be quoted.

    The distinction matters commercially. Raw rate is what a sensor datasheet
    implies; effective rate is what a crew delivers after turns, battery swaps,
    return-to-home, re-flights of cloud-affected lines and the solar-angle
    window. Pricing off the raw rate is how survey companies lose money.
    """
    p = cfg["platform"]
    swath = float(p["swath_m"])
    speed = float(p["ground_speed_ms"])
    sidelap = float(p["sidelap_frac"])
    eff = float(p["operational_efficiency"])
    hours = float(p["hours_per_field_day"])

    raw_m2_per_s = swath * speed
    raw_ha_per_hr = raw_m2_per_s * 3600.0 / 10_000.0
    effective_ha_per_hr = raw_ha_per_hr * (1.0 - sidelap) * eff
    ha_per_day = effective_ha_per_hr * hours

    return {
        "swath_m": swath,
        "ground_speed_ms": speed,
        "sidelap_frac": sidelap,
        "operational_efficiency": eff,
        "hours_per_field_day": hours,
        "raw_ha_per_hr": raw_ha_per_hr,
        "effective_ha_per_hr": effective_ha_per_hr,
        "ha_per_field_day": ha_per_day,
        "assumptions": [
            "Swath is MODELLED from an assumed ~22 deg FOV at 90 m AGL and is "
            "marked [VERIFY] in the proposal. It scales the whole model linearly.",
            "Ground speed is SNR-limited, not line-rate-limited, in VNIR at "
            "8 cm GSD under subtropical canopy illumination.",
            "Operational efficiency folds in turns, battery swaps, RTH and "
            "re-flights; it is the least defensible number here and should be "
            "replaced with measured Phase 0 sortie logs.",
        ],
    }


def proposal_table_consistency_check(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check the computed model against the numbers written in proposal §5.3 — and
    flag that the table as published does not reconcile with itself.

    Two arithmetic discrepancies, both worth fixing before the document goes to
    an evaluator who will check them:

    **(1) Raw area rate.** The table gives "~46 ha/hr" and shows its working as
    "36 m x 6 m/s". But 36 m x 6 m/s = 216 m^2/s = 77.8 ha/hr, not 46. The stated
    swath and speed do not produce the stated raw rate.

    **(2) Per field day.** The table gives an effective rate of 25-30 ha/hr and,
    separately, 80-120 ha per field day over "6 hours operations". 25-30 ha/hr
    for 6 hours is 150-180 ha/day, not 80-120. The two rows are inconsistent by
    roughly a factor of two.

    Neither error is fatal — the conclusion that 44,300 ha is unreachable and
    that the three-tier funnel is mandatory survives either reading — but a
    government technical evaluator who multiplies 36 by 6 will find it, and
    finding it costs more credibility than the correction does.

    The implied per-day figure that reconciles the table is roughly 13-20 ha/hr,
    which corresponds to an operational efficiency near 0.25-0.37 rather than
    the 0.62 assumed here. That is the number the Phase 0 sortie logs settle.
    """
    cov = coverage_model(cfg)
    stated = {
        "raw_ha_per_hr": 46.0,
        "effective_ha_per_hr": [25.0, 30.0],
        "ha_per_field_day": [80.0, 120.0],
    }
    implied_hr_from_day = [d / cov["hours_per_field_day"] for d in stated["ha_per_field_day"]]

    return {
        "computed": {
            "raw_ha_per_hr": cov["raw_ha_per_hr"],
            "effective_ha_per_hr": cov["effective_ha_per_hr"],
            "ha_per_field_day": cov["ha_per_field_day"],
        },
        "stated_in_proposal": stated,
        "discrepancies": [
            {
                "item": "raw area rate",
                "stated": 46.0,
                "computed_from_stated_inputs": cov["raw_ha_per_hr"],
                "detail": "36 m swath x 6 m/s = 77.8 ha/hr; the table says 46 ha/hr.",
            },
            {
                "item": "per field day vs effective rate",
                "stated_effective_ha_per_hr": stated["effective_ha_per_hr"],
                "implied_by_stated_field_day": implied_hr_from_day,
                "detail": ("80-120 ha over 6 h implies 13-20 ha/hr, but the table "
                           "separately states 25-30 ha/hr. The two rows disagree "
                           "by roughly 2x."),
            },
        ],
        "implied_operational_efficiency_to_match_field_day": [
            d / (cov["raw_ha_per_hr"] * (1 - cfg["platform"]["sidelap_frac"])
                 * cov["hours_per_field_day"]) for d in stated["ha_per_field_day"]
        ],
        "recommendation": (
            "Rebuild the §5.3 table from the platform geometry rather than "
            "quoting it, and replace operational_efficiency with measured Phase 0 "
            "sortie logs. The strategic conclusion (three-tier funnel mandatory) "
            "holds under every reading, so correcting the arithmetic costs nothing "
            "and removes an easy line of attack."
        ),
    }


def programme_cost(area_ha: float, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Field days, crew days and contract value for a given annual Tier-2 area."""
    cov = coverage_model(cfg)
    econ = cfg["economics"]
    days = area_ha / max(cov["ha_per_field_day"], 1e-6)
    lo, hi = econ["tier2_survey_hkd_per_ha"]

    return {
        "area_ha": area_ha,
        "field_days": days,
        "field_days_with_weather_margin": days / 0.62,   # ~38% weather loss, autumn-winter
        "contract_value_hkd": [area_ha * lo, area_ha * hi],
        "ha_per_field_day": cov["ha_per_field_day"],
    }


def three_tier_funnel(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quantify the §3.3 funnel: why territory-wide hyperspectral is impossible and
    what the funnel converts it into.

    The result is the single most important slide for a technical evaluator,
    because it shows the constraint was engineered around rather than ignored.
    """
    econ = cfg["economics"]
    cov = coverage_model(cfg)
    total = float(econ["afcd_total_area_ha"])
    flag_lo, flag_hi = econ["tier1_flag_fraction"]

    naive_days = total / max(cov["ha_per_field_day"], 1e-6)
    out = {
        "total_afcd_area_ha": total,
        "naive_full_coverage_field_days": naive_days,
        "naive_full_coverage_years_one_crew": naive_days / 200.0,   # ~200 flyable days/yr
        "tiers": [],
    }
    for frac in (flag_lo, flag_hi):
        a = total * frac
        pc = programme_cost(a, cfg)
        out["tiers"].append({
            "tier1_flag_fraction": frac,
            "tier2_area_ha": a,
            "field_days": pc["field_days"],
            "field_days_with_weather_margin": pc["field_days_with_weather_margin"],
            "contract_value_hkd": pc["contract_value_hkd"],
            "feasible_with_one_crew": pc["field_days_with_weather_margin"] <= 200,
        })
    return out


def revenue_model(cfg: Dict[str, Any], tier2_ha: float = 3000.0,
                  reflight_ha: float = 1200.0,
                  n_rapid_response: int = 6) -> Dict[str, Any]:
    """
    Indicative annual revenue from the §7.2 price list.

    Returns low/high bounds rather than a point estimate, because every input is
    a range and collapsing ranges to a midpoint is how business plans acquire
    false precision.
    """
    e = cfg["economics"]

    def rng_mul(pair, qty):
        return [pair[0] * qty, pair[1] * qty]

    lines = {
        "tier2_survey": rng_mul(e["tier2_survey_hkd_per_ha"], tier2_ha),
        "reflight_efficacy": rng_mul(e["reflight_hkd_per_ha"], reflight_ha),
        "platform_licence": list(e["platform_licence_hkd_per_year"]),
        "rapid_response": rng_mul(e["rapid_response_hkd"], n_rapid_response),
    }
    total_lo = sum(v[0] for v in lines.values())
    total_hi = sum(v[1] for v in lines.values())

    return {
        "assumptions": {
            "tier2_ha": tier2_ha, "reflight_ha": reflight_ha,
            "rapid_response_mobilisations": n_rapid_response,
        },
        "lines": lines,
        "total_hkd": [total_lo, total_hi],
        "proposal_indicative_range_hkd": [1_500_000, 4_000_000],
        "note": (
            "Prices are inferred from general survey-services benchmarks, not "
            "from any observed HK government contract (proposal Appendix B.6). "
            "Treat as an order-of-magnitude sanity check, not a quotation."
        ),
    }


def phase0_budget_check(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Does the §7.3 Phase 0 scope fit inside the HK$1.4M / 10-month ask?

    Phase 0 flies 150-250 ha over one catchment plus a ground spectral library
    and 40-60 validation plots. This is a coarse bottom-up check, and its value
    is that it is bottom-up: an ask that cannot be reconstructed from its own
    workplan does not survive a funder's first question.
    """
    econ = cfg["economics"]
    cov = coverage_model(cfg)
    budget = float(econ["phase0_budget_hkd"])

    survey_ha = 200.0
    field_days = survey_ha / max(cov["ha_per_field_day"], 1e-6)
    field_days_wx = field_days / 0.62

    # Indicative bottom-up costs (HK$). Stated so they can be argued with.
    items = {
        "field spectroradiometer (rental/purchase amortised)": 180_000,
        "VNIR hyperspectral payload (amortised over 3 yr, 1 yr share)": 420_000,
        "UAV platform + CAD compliance + insurance": 120_000,
        "2 staff x 10 months (loaded, part-allocated)": 480_000,
        "botanist / ground-truth field days": 90_000,
        "processing, storage, GIS delivery": 60_000,
    }
    total = sum(items.values())

    return {
        "budget_hkd": budget,
        "bottom_up_total_hkd": total,
        "headroom_hkd": budget - total,
        "fits": total <= budget,
        "line_items": items,
        "phase0_survey_ha": survey_ha,
        "phase0_field_days": field_days,
        "phase0_field_days_with_weather": field_days_wx,
        "note": (
            "Line items are indicative and unquoted. The point of the check is "
            "that the ask is reconstructible from the workplan, not that these "
            "are the prices a supplier would give."
        ),
    }
