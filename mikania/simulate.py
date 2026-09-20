"""
Tier-2 scene simulation — the Phase 0 demonstration acquisition.

Proposal §7.3 Phase 0 is: fly ~150-250 ha over one catchment, ground-truth 40-60
disjoint validation plots, and report field accuracy with spatially disjoint
hold-out. That flight has not happened. This module builds the scene it would
produce, so that every downstream stage — preprocessing, classification,
unmixing, severity ranking, change detection, the GIS deliverable and the web
platform — is exercised end to end on realistic input.

What is simulated, and why each part earns its cost
---------------------------------------------------
**Spatial structure.** Infestation is not random pixels. Mikania spreads from
edges and disturbance corridors as connected patches, so patches are generated
from thresholded, spatially-correlated Gaussian random fields. Without this the
classifier's spatial context is meaningless and object-based aggregation (which
is how the deliverable is actually produced) cannot be tested.

**Two-layer mixing.** Mikania blankets *over* host canopy, so infested pixels
are genuine mixtures whose Mikania fraction varies continuously from light
infestation to full blanket (proposal §3.2). This is what makes the abundance
product — and therefore the severity score — meaningful.

**Illumination and BRDF.** A slope/aspect brightness field plus an across-track
view-angle gradient. Proposal §5.4 risk 4 names illumination variation as a
medium-severity risk that could swamp inter-species difference; a simulator
without it would silently validate a pipeline that has never faced the problem.

**Pushbroom artefacts.** Wavelength-dependent SNR, spectral smile (across-track
wavelength shift) and keystone (across-track band misregistration). These are
the defects that distinguish a real pushbroom line-scanner from a clean matrix
of numbers, and the preprocessing chain must be shown to survive them.

**Site random effects.** Delegated to :mod:`spectral_library`, which draws a
per-(site, species) offset. This is what makes leave-one-site-out validation
meaningfully harder than random splitting — the entire methodological point of
proposal §5.1(6).

Honest limitation, carried through in the metadata
--------------------------------------------------
Sub-canopy Mikania is invisible from above (proposal §5.2, last row). The
simulator therefore marks a configurable fraction of infested canopy as
*occluded*: present on the ground, absent from the imagery, and excluded from
the ground truth the classifier is scored against. Scoring against truth the
sensor could not physically observe would manufacture a false accuracy penalty
and hide the real limitation. The occluded fraction is reported instead.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage

from .config import class_ids, wavelengths
from .spectral_library import sample_class_spectra


# ==========================================================================
# Spatial fields
# ==========================================================================
def correlated_field(shape: Tuple[int, int], scale_px: float,
                     gen: np.random.Generator) -> np.ndarray:
    """
    A zero-mean, unit-variance Gaussian random field with correlation length
    ``scale_px``, produced by smoothing white noise.

    Cheaper and more controllable than an FFT spectral synthesis, and the
    resulting patch morphology — rounded, connected, size-graded blobs — matches
    how vegetation patches actually look in a canopy far better than either
    white noise or a fractal field.
    """
    f = gen.normal(0.0, 1.0, size=shape)
    f = ndimage.gaussian_filter(f, sigma=max(scale_px, 0.5), mode="reflect")
    return (f - f.mean()) / max(f.std(), 1e-8)


def _threshold_for_fraction(field: np.ndarray, fraction: float) -> float:
    """Threshold that selects exactly ``fraction`` of the field's area."""
    return float(np.quantile(field, 1.0 - np.clip(fraction, 0.0, 1.0)))


def build_ground_truth(shape: Tuple[int, int], site: Dict[str, Any],
                       cfg: Dict[str, Any], gen: np.random.Generator
                       ) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    """
    Lay out the scene: which class is where, and how heavily infested.

    Returns ``(gt, mikania_fraction, layers)``.

    The construction order matters and mirrors the real landscape:

    1. a canopy/shrub/soil/shadow substrate from a coarse correlated field —
       shadow and soil are placed first because they are the terrain, not a
       vegetation choice;
    2. native climbers scattered as small patches through the canopy — these
       are the confusables, and they must sit in the same places Mikania could,
       or the classifier could cheat off location alone;
    3. Mikania patches from a finer field, biased toward canopy edges and gaps
       (its actual ecology: it is a light-demanding edge coloniser);
    4. a continuous infestation fraction inside each Mikania patch, high in the
       core and tapering at the margin.
    """
    ids = class_ids(cfg)
    sc = cfg["scene"]
    lines, samples = shape

    # --- 1. substrate ----------------------------------------------------
    base = correlated_field(shape, sc["patch_scale_px"] * 2.2, gen)
    gt = np.full(shape, ids["host_canopy"], dtype=np.uint8)

    # Shrub/grass occupies the LOW tail of the substrate field (open, drier,
    # more exposed ground). Note the direct quantile: an earlier version wrote
    # `base < _threshold_for_fraction(-base, f)`, which double-negates and
    # selects 1-f of the scene instead of f — it made shrub 78% of every scene
    # and demoted host canopy, the dominant matrix, to a minority class.
    shrub_fraction = float(sc.get("shrub_fraction", 0.22))
    gt[base < np.quantile(base, shrub_fraction)] = ids["shrub_grass"]

    soil_f = correlated_field(shape, sc["patch_scale_px"] * 1.1, gen)
    gt[soil_f > _threshold_for_fraction(soil_f, sc["soil_fraction"])] = ids["soil_rock"]

    shadow_f = correlated_field(shape, sc["patch_scale_px"] * 0.8, gen)
    shadow_mask = shadow_f > _threshold_for_fraction(shadow_f, sc["shadow_fraction"])
    gt[shadow_mask] = ids["shadow"]

    # --- 2. native climbers ---------------------------------------------
    natives = cfg["confusable_pair"]["natives"]
    canopy = gt == ids["host_canopy"]
    for i, nat in enumerate(natives):
        f = correlated_field(shape, sc["patch_scale_px"] * 0.75, gen)
        # Each native gets ~4-7% of the canopy, inside canopy only.
        frac = 0.04 + 0.03 * gen.random()
        m = canopy & (f > _threshold_for_fraction(f, frac))
        gt[m] = ids[nat]

    # --- 3. Mikania ------------------------------------------------------
    # Edge affinity: distance from the nearest non-canopy pixel. Mikania is a
    # light-demanding coloniser of gaps, roadsides and stream corridors, so a
    # uniform-random placement would misrepresent both the spatial statistics
    # and the difficulty of the detection problem.
    non_canopy = ~np.isin(gt, [ids["host_canopy"]] + [ids[n] for n in natives])
    dist = ndimage.distance_transform_edt(~non_canopy)
    edge_affinity = np.exp(-dist / max(sc["patch_scale_px"] * 0.9, 1.0))

    mfield = correlated_field(shape, sc["patch_scale_px"], gen) + 1.4 * edge_affinity
    prevalence = float(site["mikania_prevalence"])
    eligible = np.isin(gt, [ids["host_canopy"]] + [ids[n] for n in natives])
    thr = _threshold_for_fraction(mfield[eligible], prevalence / max(eligible.mean(), 1e-6))
    mik_mask = eligible & (mfield > thr)

    # --- 4. infestation fraction ----------------------------------------
    # Distance into the patch -> coverage. Cores are full blanket, margins light.
    inside = ndimage.distance_transform_edt(mik_mask)
    frac = np.clip(inside / max(sc["patch_scale_px"] * 0.55, 1.0), 0.0, 1.0)
    frac = 0.30 + 0.70 * frac                       # never less than 30% where present
    frac = frac * (0.85 + 0.30 * gen.random(shape))
    mikania_fraction = np.where(mik_mask, np.clip(frac, 0.0, 1.0), 0.0)

    layers = {
        "substrate_field": base,
        "shadow_mask": shadow_mask,
        "edge_affinity": edge_affinity,
        "mikania_mask_full": mik_mask,
    }
    return gt, mikania_fraction.astype(np.float32), layers


# ==========================================================================
# Radiometry
# ==========================================================================
def illumination_field(shape: Tuple[int, int], cfg: Dict[str, Any],
                       site: Dict[str, Any], gen: np.random.Generator) -> np.ndarray:
    """
    Multiplicative brightness field from terrain slope/aspect plus across-track
    BRDF.

    Terrain relief is taken from the site config, so a 300 m-relief Sai Kung
    scene is radiometrically harder than a 120 m Lam Tsuen one — which is true,
    and which means leave-one-site-out has to cope with genuinely different
    radiometry per site rather than a cosmetic relabelling.
    """
    sc = cfg["scene"]
    lines, samples = shape

    relief = float(site.get("terrain_relief_m", 150.0)) / 200.0
    terrain = correlated_field(shape, sc["patch_scale_px"] * 3.5, gen)
    illum = 1.0 + sc["illumination_gradient"] * relief * terrain

    # BRDF: across-track brightening toward the forward-scatter edge. Pushbroom
    # scenes show this as a systematic cross-track ramp, and it is a classic
    # cause of "the classifier learned which side of the swath a pixel is on".
    x = np.linspace(-1.0, 1.0, samples)
    illum *= (1.0 + sc["brdf_strength"] * x)[None, :]

    return np.clip(illum, 0.25, 2.0)


def apply_sensor_model(cube: np.ndarray, wl: np.ndarray, cfg: Dict[str, Any],
                       gen: np.random.Generator) -> np.ndarray:
    """
    Degrade a clean reflectance cube into what the pushbroom would record.

    Three real artefacts, in acquisition order:

    **Smile** — an across-track shift of the wavelength calibration. Column 0 and
    column N sample slightly different wavelengths for the same band index.
    Applied first because it happens in the optics.

    **Keystone** — an across-track spatial misregistration that differs by band,
    so the blue and NIR images of the same target are fractionally offset. This
    is what turns a sharp patch edge into a spectrally mixed fringe.

    **Noise** — wavelength-dependent, from the configured SNR anchor points.
    Interpolated in log space because SNR spans an order of magnitude and linear
    interpolation would badly misestimate the blue end, which is exactly where
    the carotenoid features we depend on live.
    """
    sens = cfg["sensor"]
    lines, samples, bands = cube.shape
    out = cube.astype(np.float32).copy()

    # --- smile ------------------------------------------------------------
    smile = float(sens.get("smile_nm", 0.0))
    if smile > 0:
        x = np.linspace(-1.0, 1.0, samples)
        shift = smile * (x ** 2 - x.mean())          # parabolic, as in real optics
        for j in range(samples):
            if abs(shift[j]) < 1e-3:
                continue
            # Resample every pixel in this column onto the shifted wavelength grid.
            col = cube[:, j, :]
            out[:, j, :] = np.array([np.interp(wl, wl + shift[j], s) for s in col],
                                    dtype=np.float32)

    # --- keystone ---------------------------------------------------------
    ks = float(sens.get("keystone_px", 0.0))
    if ks > 0:
        for b in range(bands):
            d = ks * (b / max(bands - 1, 1) - 0.5) * 2.0
            if abs(d) > 1e-3:
                out[:, :, b] = ndimage.shift(out[:, :, b], (0.0, d), order=1,
                                             mode="nearest")

    # --- noise ------------------------------------------------------------
    anchors_nm = np.array([450.0, 700.0, 900.0])
    anchors_snr = np.array([sens["snr_at_450nm"], sens["snr_at_700nm"], sens["snr_at_900nm"]])
    snr = np.exp(np.interp(wl, anchors_nm, np.log(anchors_snr)))
    # Reference radiance level: noise is proportional to a mid-scene signal, not
    # to each pixel's own value, because detector noise does not vanish in shade.
    ref = np.median(out.reshape(-1, bands), axis=0)
    sigma = np.maximum(ref, 0.02) / snr
    out += gen.normal(0.0, 1.0, size=out.shape).astype(np.float32) * sigma.astype(np.float32)

    out += float(sens.get("dark_current_offset", 0.0))
    return np.clip(out, 1e-4, 1.5).astype(np.float32)


# ==========================================================================
# Scene assembly
# ==========================================================================
def simulate_site(site: Dict[str, Any], lib: Dict[str, Any], cfg: Dict[str, Any],
                  gen: np.random.Generator,
                  contrast: Optional[float] = None,
                  treated: Optional[np.ndarray] = None,
                  epoch: str = "baseline",
                  noise_gen: Optional[np.random.Generator] = None,
                  fraction_override: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Simulate one catchment acquisition.

    Parameters
    ----------
    gen
        Drives the SCENE LAYOUT — terrain, class placement, patch geometry.
    noise_gen
        Drives the ACQUISITION — per-pixel spectral draws, illumination and
        sensor noise. Defaults to ``gen``.

        The split exists for re-flights. A second survey of the same catchment
        must see the *same ground* (identical terrain, identical species
        placement) under a *different acquisition* (different day, sun angle and
        noise realisation). Passing one generator for both — as the first version
        of the efficacy stage did — regenerates the entire landscape from
        scratch, so patches appear to have been cleared and identical-sized
        patches appear to have emerged elsewhere. Change detection then measures
        nothing but the random seed.
    treated
        Boolean mask of polygons cleared between epochs.
    fraction_override
        Explicit Mikania coverage fraction to impose, replacing the generated
        one. This is how the efficacy stage carries a treatment outcome —
        partial clearance plus margin re-emergence — into the re-flight.
    epoch
        Label carried into metadata ('baseline' / 're-flight +6mo' etc.).

    Returns a dict with the cube, the observable ground truth, the true Mikania
    fraction, and full metadata including the occluded fraction.
    """
    wl = wavelengths(cfg)
    sc = cfg["scene"]
    shape = (sc["lines"], sc["samples"])
    ids = class_ids(cfg)
    season_key = site["season"]

    ngen = noise_gen if noise_gen is not None else gen

    gt, mik_frac, layers = build_ground_truth(shape, site, cfg, gen)

    if fraction_override is not None:
        mik_frac = np.asarray(fraction_override, dtype=np.float32).copy()

    # --- treatment between epochs ----------------------------------------
    if treated is not None and treated.any():
        gt = gt.copy()
        mik_frac = mik_frac.copy()
        gt[treated & (gt == ids["mikania"])] = ids["host_canopy"]
        mik_frac[treated] *= 0.0

    # --- sub-canopy occlusion (proposal §5.2, honest limitation) ----------
    # A fraction of infested canopy is under closed canopy and simply cannot be
    # seen from above. It is removed from BOTH the imagery and the ground truth,
    # and reported separately, rather than being scored as a miss.
    occl_field = correlated_field(shape, sc["patch_scale_px"] * 1.3, gen)  # layout: same ground each epoch
    occl_frac_target = float(cfg.get("scene", {}).get("subcanopy_occluded_fraction", 0.18))
    infested = mik_frac > 0
    occluded = np.zeros(shape, dtype=bool)
    if infested.any():
        # occl_field[infested] is ALREADY restricted to infested pixels, so the
        # target fraction applies to it directly. (Dividing by infested.mean()
        # here — as the eligible-area threshold above legitimately does — drove
        # the quantile past 1.0 and occluded the entire infestation.)
        thr = _threshold_for_fraction(occl_field[infested], occl_frac_target)
        occluded = infested & (occl_field > thr)
        mik_frac = np.where(occluded, 0.0, mik_frac)

    # Class map the sensor can actually observe.
    gt_obs = gt.copy()
    gt_obs[(mik_frac > 0.30)] = ids["mikania"]
    gt_obs[occluded & (gt_obs == ids["mikania"])] = ids["host_canopy"]

    # --- spectra ----------------------------------------------------------
    lines, samples = shape
    bands = wl.size
    cube = np.zeros((lines, samples, bands), dtype=np.float32)

    veg_keys = set(cfg["species_spectra"])
    for key, cid in ids.items():
        if key == "unlabelled":
            continue
        m = gt == cid
        n = int(m.sum())
        if n == 0:
            continue
        if key in veg_keys:
            spec = sample_class_spectra(lib, cfg, key, season_key, n, ngen,
                                        site_key=site["key"], contrast=contrast)
        else:
            # soil_rock / shadow: endmember plus modest multiplicative variation.
            em = lib["endmembers"][key]
            spec = em[None, :] * np.exp(ngen.normal(0.0, 0.16, size=(n, 1)))
        cube[m] = spec.astype(np.float32)

    # --- two-layer mixing: Mikania blanket OVER host canopy ---------------
    # This is the structure proposal §3.2 describes, and the reason abundance
    # (not just a class label) is the meaningful product.
    mix = mik_frac[:, :, None]
    if infested.any():
        n_inf = int((mik_frac > 0).sum())
        mik_spec = sample_class_spectra(lib, cfg, "mikania", season_key, n_inf, ngen,
                                        site_key=site["key"], contrast=contrast)
        blanket = np.zeros_like(cube)
        blanket[mik_frac > 0] = mik_spec.astype(np.float32)
        cube = (1.0 - mix) * cube + mix * blanket

    # --- radiometry --------------------------------------------------------
    cube *= illumination_field(shape, cfg, site, ngen)[:, :, None].astype(np.float32)
    cube = apply_sensor_model(cube, wl, cfg, ngen)

    meta = {
        "site_key": site["key"],
        "site_name": site["name"],
        "role": site["role"],
        "season": season_key,
        "season_label": cfg["phenology"]["seasons"][season_key]["label"],
        "epoch": epoch,
        "centroid": site["centroid"],
        "area_ha": site["area_ha"],
        "demo_gsd_m": sc["demo_gsd_m"],
        "production_gsd_m": cfg["platform"]["gsd_m"],
        "contrast_scale": float(contrast if contrast is not None
                                else cfg["species_contrast"]["scale"]),
        "mikania_prevalence_target": site["mikania_prevalence"],
        "mikania_prevalence_observed": float((gt_obs == ids["mikania"]).mean()),
        "subcanopy_occluded_fraction": float(
            occluded.sum() / max(infested.sum(), 1)) if infested.any() else 0.0,
        "shadow_fraction": float((gt == ids["shadow"]).mean()),
        "n_bands": int(bands),
        "wavelength_range_nm": [float(wl[0]), float(wl[-1])],
        "limitation_note": (
            "Sub-canopy infestation is excluded from both imagery and ground "
            "truth: it is physically unobservable from above (proposal §5.2). "
            "Reported accuracy is canopy-level accuracy, and the occluded "
            "fraction is stated so the scope of the claim is unambiguous."
        ),
    }

    return {
        "cube": cube,
        "gt": gt_obs.astype(np.uint8),
        "gt_full": gt.astype(np.uint8),
        "mikania_fraction": mik_frac.astype(np.float32),
        "occluded": occluded,
        "wavelengths": wl,
        "meta": meta,
        "layers": layers,
    }
