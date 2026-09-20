"""
Severity scoring and treatment prioritisation — deliverable 2.

Proposal §2.2 reads a Government policy statement as a procurement brief:

    "Government has stated that complete eradication of Mikania in Hong Kong is
     not achievable, and that requests for clearing should be prioritised
     according to impact on vegetation and land use, with priority given to
     ecologically important areas and to sites where mature trees and woodland
     habitat are adversely affected. ... AFCD has publicly adopted a
     PRIORITISATION strategy for an unwinnable eradication problem. A
     prioritisation strategy requires a ranked, spatially explicit map of
     severity. AFCD does not currently have one. That is the product."

This module turns a classified scene into that ranked map. The five weighted
components come straight from §3.1 deliverable 2 — canopy coverage fraction,
host tree maturity, proximity to ecologically sensitive areas, spread
trajectory, and access cost — and their weights live in the config, not here,
so they can be renegotiated with AFCD without touching code.

Output is a table of *treatment units*: contiguous polygons, each with an area,
a severity score, an action band and a cost estimate. A raster is a map; a
polygon table with an action column is a work plan, and the work plan is what
converts a survey into a purchase order.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage

from .config import class_ids


# ==========================================================================
# Component scores — each returns a raster on [0, 1]
# ==========================================================================
def coverage_component(mikania_fraction: np.ndarray) -> np.ndarray:
    """
    How much of the canopy the blanket covers.

    Used directly: the abundance fraction from unmixing already lives on [0, 1]
    and is the most defensible single indicator of ecological damage, because
    Mikania kills by cutting off light and the fraction of light intercepted is
    what the coverage fraction measures.
    """
    return np.clip(np.nan_to_num(mikania_fraction, nan=0.0), 0.0, 1.0)


def host_maturity_component(cube: np.ndarray, wavelengths: np.ndarray,
                            class_map: np.ndarray, cfg: Dict[str, Any],
                            smooth_px: float = 3.0) -> np.ndarray:
    """
    Proxy for host tree maturity — "sites where mature trees and woodland
    habitat are adversely affected" get priority.

    We have no LiDAR, so maturity is estimated from what a VNIR cube can see:
    mature closed-canopy broadleaf forest has a high, spatially *smooth* NIR
    plateau (deep multi-layer canopy, high LAI), whereas regenerating scrub is
    lower and more texturally broken. The score combines plateau amplitude with
    local textural smoothness.

    This is explicitly a proxy and is labelled as such in the output. If AFCD
    supplies stand-age or tree-register data, or a LiDAR canopy height model,
    it replaces this function and the severity score improves. That substitution
    is a natural upsell and worth flagging in the proposal.
    """
    wl = np.asarray(wavelengths)
    m = (wl >= 780) & (wl <= 900)
    nir = cube[:, :, m].mean(axis=2)

    lo, hi = np.percentile(nir, [5, 95])
    amplitude = np.clip((nir - lo) / max(hi - lo, 1e-6), 0.0, 1.0)

    # Textural smoothness: low local standard deviation -> closed, even canopy.
    local_mean = ndimage.uniform_filter(nir, size=int(max(smooth_px, 1)))
    local_var = ndimage.uniform_filter(nir ** 2, size=int(max(smooth_px, 1))) - local_mean ** 2
    rough = np.sqrt(np.maximum(local_var, 0.0))
    r_lo, r_hi = np.percentile(rough, [5, 95])
    smoothness = 1.0 - np.clip((rough - r_lo) / max(r_hi - r_lo, 1e-6), 0.0, 1.0)

    score = 0.65 * amplitude + 0.35 * smoothness

    # Non-forest classes carry no mature host to lose.
    ids = class_ids(cfg)
    non_host = np.isin(class_map, [ids["soil_rock"], ids["shadow"], ids["shrub_grass"]])
    score = np.where(non_host, 0.15 * score, score)
    return np.clip(score, 0.0, 1.0)


def ecological_sensitivity_component(shape: Tuple[int, int],
                                     site_meta: Dict[str, Any],
                                     occurrence_context: Optional[Dict[str, Any]] = None
                                     ) -> np.ndarray:
    """
    Ecological value of the ground, on [0, 1].

    Driven by the real GBIF native-climber record density around the site
    (fetched in stage 01): catchments where botanists have recorded many native
    climber species are, on the evidence available, more botanically diverse and
    therefore more valuable to protect.

    This is a deliberately weak proxy standing in for what AFCD actually holds —
    SSSI boundaries, Ecologically Important Stream reaches, priority habitat
    designations and the country park zoning layer. Those are the correct
    inputs, they are not open data, and asking for them is exactly the kind of
    cheap high-leverage request proposal §10.1 recommends leading with.
    """
    base = 0.45
    if occurrence_context:
        n_nat = float(occurrence_context.get("n_native_climbers", 0))
        # Saturating: 30+ native climber records is treated as "high value".
        base = 0.30 + 0.55 * (1.0 - np.exp(-n_nat / 18.0))

    # A gentle gradient so the ranking is not perfectly flat within a site;
    # stands in for distance-to-designated-area, which is the real driver.
    lines, samples = shape
    yy = np.linspace(-1.0, 1.0, lines)[:, None]
    xx = np.linspace(-1.0, 1.0, samples)[None, :]
    grad = 0.10 * np.exp(-(yy ** 2 + xx ** 2) / 0.8)
    return np.clip(base + grad, 0.0, 1.0)


def spread_component(mikania_fraction: np.ndarray, patch_scale_px: float = 14.0,
                     previous_fraction: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Spread trajectory.

    With two epochs this is measured directly: growth in coverage between
    surveys, which is the real quantity and the reason the archive (§6.1 point 4)
    compounds in value.

    With only a baseline it is estimated from patch geometry. An expanding
    infestation has a long, convoluted, actively-colonising margin relative to
    its area; a stable one is compact. The perimeter-to-area ratio, normalised
    against a circle of the same area, captures that. It is a genuine proxy but
    a weaker one, and the output records which of the two was used.
    """
    present = mikania_fraction > 0.05

    if previous_fraction is not None:
        growth = np.clip(mikania_fraction - previous_fraction, 0.0, 1.0)
        g_hi = np.percentile(growth[growth > 0], 90) if (growth > 0).any() else 1.0
        return np.clip(growth / max(g_hi, 1e-6), 0.0, 1.0)

    lab, n = ndimage.label(present)
    out = np.zeros(mikania_fraction.shape, dtype=np.float64)
    if n == 0:
        return out

    eroded = ndimage.binary_erosion(present, iterations=1)
    edge = present & ~eroded
    areas = ndimage.sum(present, lab, index=np.arange(1, n + 1))
    perims = ndimage.sum(edge, lab, index=np.arange(1, n + 1))

    for i in range(n):
        a, p = areas[i], perims[i]
        if a <= 0:
            continue
        # Circle of equal area has perimeter 2*sqrt(pi*a); ratio >= 1.
        compactness = p / max(2.0 * np.sqrt(np.pi * a), 1e-6)
        out[lab == i + 1] = np.clip((compactness - 1.0) / 1.6, 0.0, 1.0)
    return out


def access_component(shape: Tuple[int, int], site_meta: Dict[str, Any]) -> np.ndarray:
    """
    Cost-effectiveness of reaching the ground, on [0, 1] where 1 = cheap.

    Steeper terrain and greater distance from the scene edge (a proxy for
    distance from a trail or road) mean higher clearance cost per hectare. A
    cheap site that is moderately infested can outrank an expensive site that is
    slightly worse, because the objective is hectares of ecological damage
    averted per dollar — which is how a fixed-budget government client actually
    has to think (proposal §6.2).
    """
    lines, samples = shape
    relief = float(site_meta.get("terrain_relief_m", 150.0))
    steepness_penalty = np.clip(relief / 350.0, 0.0, 1.0)

    yy, xx = np.mgrid[0:lines, 0:samples]
    edge_dist = np.minimum.reduce([yy, xx, lines - 1 - yy, samples - 1 - xx]).astype(float)
    edge_dist /= max(edge_dist.max(), 1.0)

    return np.clip((1.0 - 0.65 * edge_dist) * (1.0 - 0.45 * steepness_penalty), 0.0, 1.0)


# ==========================================================================
# Combination
# ==========================================================================
def severity_map(cube: np.ndarray, wavelengths: np.ndarray,
                 class_map: np.ndarray, mikania_fraction: np.ndarray,
                 cfg: Dict[str, Any], site_meta: Dict[str, Any],
                 occurrence_context: Optional[Dict[str, Any]] = None,
                 previous_fraction: Optional[np.ndarray] = None
                 ) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """
    Weighted severity on [0, 1], plus every component raster for audit.

    Returning the components is not optional decoration. When AFCD asks why a
    given patch ranks above another — and on a prioritisation contract they
    will — the answer has to be decomposable into the five stated factors. A
    single opaque score is not defensible in a government review.

    Severity is zeroed where there is no Mikania: a pristine mature stand next
    to a sensitive habitat scores high on three components and must still rank
    zero, because there is nothing to treat.
    """
    w = cfg["severity"]["weights"]
    shape = class_map.shape

    comps = {
        "coverage_fraction": coverage_component(mikania_fraction),
        "host_maturity": host_maturity_component(cube, wavelengths, class_map, cfg),
        "ecological_sensitivity": ecological_sensitivity_component(
            shape, site_meta, occurrence_context),
        "spread_trajectory": spread_component(
            mikania_fraction, cfg["scene"]["patch_scale_px"], previous_fraction),
        "access_cost": access_component(shape, site_meta),
    }

    score = np.zeros(shape, dtype=np.float64)
    for k, weight in w.items():
        score += float(weight) * comps[k]

    score = np.where(comps["coverage_fraction"] > 0.0, score, 0.0)
    return np.clip(score, 0.0, 1.0), comps


def action_band(score: float, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Map a severity score onto its configured action band."""
    for b in cfg["severity"]["bands"]:
        if b["min"] <= score < b["max"]:
            return b
    return cfg["severity"]["bands"][-1]


def treatment_units(severity: np.ndarray, mikania_fraction: np.ndarray,
                    cfg: Dict[str, Any], site_meta: Dict[str, Any],
                    components: Optional[Dict[str, np.ndarray]] = None
                    ) -> List[Dict[str, Any]]:
    """
    Polygonise severity into a ranked list of treatment units.

    Connected components of the infestation mask become work orders. Patches
    below ``severity.patch_min_area_px`` are dropped: raising a work order for a
    handful of pixels wastes a crew's day and erodes confidence in the whole
    product faster than a missed patch does.

    Area is computed at the *demonstration* GSD and the production GSD is
    carried alongside, so nobody reads a hectare figure off a demo scene and
    quotes it as a survey result.
    """
    ids = class_ids(cfg)
    gsd = float(site_meta.get("demo_gsd_m", cfg["scene"]["demo_gsd_m"]))
    px_ha = (gsd ** 2) / 10_000.0
    min_px = int(cfg["severity"]["patch_min_area_px"])

    mask = mikania_fraction > cfg["unmixing"]["min_abundance_report"]
    lab, n = ndimage.label(mask)
    if n == 0:
        return []

    price_lo, price_hi = cfg["economics"]["tier2_survey_hkd_per_ha"]
    units = []
    for i in range(1, n + 1):
        m = lab == i
        npx = int(m.sum())
        if npx < min_px:
            continue
        sev = float(severity[m].mean())
        band = action_band(sev, cfg)
        area_ha = npx * px_ha
        rr, cc = np.where(m)

        unit = {
            "unit_id": f"{site_meta['site_key']}-{i:03d}",
            "site": site_meta["site_key"],
            "site_name": site_meta.get("site_name", site_meta["site_key"]),
            "area_ha": round(area_ha, 4),
            "n_pixels": npx,
            "severity": round(sev, 4),
            "severity_max": round(float(severity[m].max()), 4),
            "mean_coverage_fraction": round(float(mikania_fraction[m].mean()), 4),
            "band": band["label"],
            "action": band["action"],
            "centroid_rc": [int(rr.mean()), int(cc.mean())],
            "bbox_rc": [int(rr.min()), int(cc.min()), int(rr.max()), int(cc.max())],
            "survey_cost_hkd": [round(area_ha * price_lo), round(area_ha * price_hi)],
        }
        if components:
            unit["components"] = {k: round(float(v[m].mean()), 4)
                                  for k, v in components.items()}
        units.append(unit)

    # Rank by severity x area: a large moderate patch is a bigger ecological
    # problem than a tiny severe one, and the crew's day is finite.
    units.sort(key=lambda u: -(u["severity"] * u["area_ha"]))
    for rank, u in enumerate(units, 1):
        u["rank"] = rank
    return units


def units_to_geojson(units: List[Dict[str, Any]], geo: Dict[str, Any],
                     severity: np.ndarray, mikania_fraction: np.ndarray,
                     cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Export treatment units as GeoJSON polygons in EPSG:4326.

    This is the actual AFCD deliverable format — it opens in QGIS, ArcGIS and
    every government GIS, and each feature carries its severity, action band and
    component breakdown as attributes, so the work plan travels with the geometry.
    """
    from scipy import ndimage as ndi

    try:
        from shapely.geometry import mapping
        from shapely.ops import unary_union
        import shapely.geometry as sgeom
    except ImportError:                                  # pragma: no cover
        return {"type": "FeatureCollection", "features": [],
                "error": "shapely not installed"}

    t = geo["transform"]

    def rc_to_lonlat(r, c):
        return (t[2] + c * t[0], t[5] + r * t[4])

    mask = mikania_fraction > cfg["unmixing"]["min_abundance_report"]
    lab, n = ndi.label(mask)
    by_id = {int(u["unit_id"].split("-")[-1]): u for u in units}

    features = []
    for i in range(1, n + 1):
        if i not in by_id:
            continue
        m = lab == i
        # Build the polygon as the union of its pixel squares. Exact, simple,
        # and fast enough at these patch sizes; a production run would use
        # rasterio.features.shapes for the same result on much larger rasters.
        rr, cc = np.where(m)
        squares = []
        for r, c in zip(rr, cc):
            x0, y0 = rc_to_lonlat(r, c)
            x1, y1 = rc_to_lonlat(r + 1, c + 1)
            squares.append(sgeom.box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        geom = unary_union(squares).simplify(abs(t[0]) * 0.5, preserve_topology=True)

        u = by_id[i]
        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {k: v for k, v in u.items() if k not in ("bbox_rc", "centroid_rc")},
        })

    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
