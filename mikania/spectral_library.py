"""
The spectral library — proposal §5.1, mitigation (1).

    "Build the ground spectral library first — no flying required. A field
     spectroradiometer measuring leaves and canopy patches at close range, under
     controlled geometry, produces the reference endmember library at a fraction
     of the cost and risk of aerial acquisition. This de-risks the entire project
     before a single survey flight."

That library is also the actual IP (§4.2): "a Hong Kong-specific, ground-truthed
spectral library for Mikania and its native look-alikes across seasons".

Phase 0 has not been flown, so this module builds the best honest stand-in:

* the **base** is real — measured ASD leaf reflectance of tropical broadleaf
  foliage from EcoSIS, resampled through the sensor's spectral response;
* the **biological variance** is real — the principal modes of variation among
  those measured leaves, not Gaussian noise;
* the **species differences** are modelled — narrow-band perturbations drawn
  straight from the mechanism table in proposal §3.2, with every magnitude
  declared in ``config/default.yaml``.

The boundary between measured and modelled is drawn explicitly, in code and in
the saved artefact's metadata, because blurring it is how a feasibility study
turns into a lie. When Phase 0 field spectra exist, :func:`build_library` reads
them from ``data/raw/field_spectra/`` instead and the modelled block is dropped.
"""

from __future__ import annotations

import glob
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import PATHS, load_config, wavelengths


# ==========================================================================
# Reading real measured spectra
# ==========================================================================
def _numeric_columns(cols) -> List[str]:
    """Column labels that parse as a wavelength in nanometres."""
    out = []
    for c in cols:
        s = str(c).strip().lstrip("﻿")
        try:
            v = float(s)
        except ValueError:
            continue
        if 300.0 <= v <= 2600.0:
            out.append(c)
    return out


def _detect_orientation(df: pd.DataFrame) -> str:
    """
    Work out which axis of an EcoSIS table is wavelength.

    A 2151 x 77 table is genuinely ambiguous by shape alone, and guessing wrong
    silently transposes the physics — you get 77 "spectra" of 2151 bands that
    are actually 2151 leaves sampled at 77 wavelengths, and every downstream
    number is nonsense. So decide on evidence, in this order:

    1. If the *column labels* parse as a dense, monotonic wavelength axis of
       plausible extent (> 200 labels spanning > 500 nm), rows are spectra.
    2. Else if the *first column's values* do the same, columns are spectra.
    3. Else fall back to whichever axis is longer, and say so.

    Trusting the config here turned out to be a mistake: EcoSIS's ``/export``
    endpoint normalises some packages to rows-are-spectra regardless of how the
    original resource file was laid out, so a per-package flag goes stale.
    """
    wcols = _numeric_columns(df.columns)
    if len(wcols) > 200:
        wl = np.array([float(str(c).strip().lstrip("﻿")) for c in wcols])
        if np.ptp(wl) > 500.0:
            return "rows_are_spectra"

    first = pd.to_numeric(df.iloc[:, 0], errors="coerce").to_numpy(dtype=np.float64)
    finite = first[np.isfinite(first)]
    if finite.size > 200 and np.ptp(finite) > 500.0 and 250.0 <= finite.min() <= 500.0:
        return "columns_are_spectra"

    return "rows_are_spectra" if df.shape[1] >= df.shape[0] else "columns_are_spectra"


def load_ecosis_csv(path: str, orientation: str = "auto") -> Tuple[np.ndarray, np.ndarray]:
    """
    Read one EcoSIS export into ``(spectra[n, k], wavelengths_nm[k])``.

    ``orientation`` defaults to ``"auto"`` (see :func:`_detect_orientation`);
    pass an explicit value only to override a detection you have verified is
    wrong.
    """
    df = pd.read_csv(path, low_memory=False)
    if orientation in (None, "", "auto"):
        orientation = _detect_orientation(df)

    if orientation == "rows_are_spectra":
        wcols = _numeric_columns(df.columns)
        wl = np.array([float(str(c).strip().lstrip("﻿")) for c in wcols])
        X = df[wcols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float64)
    elif orientation == "columns_are_spectra":
        # First column is the wavelength axis; every other column is one sample.
        wl = pd.to_numeric(df.iloc[:, 0], errors="coerce").to_numpy(dtype=np.float64)
        X = df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float64).T
        good = np.isfinite(wl)
        wl, X = wl[good], X[:, good]
    else:
        raise ValueError(f"unknown orientation {orientation!r}")

    order = np.argsort(wl)
    return X[:, order], wl[order]


def resample_to_sensor(X: np.ndarray, wl_src: np.ndarray,
                       wl_dst: np.ndarray, fwhm_nm: float) -> np.ndarray:
    """
    Convolve 1 nm laboratory spectra with the sensor's spectral response
    function and sample onto the band centres.

    A real pushbroom band is not a point sample: it integrates a roughly
    Gaussian passband of ~6 nm FWHM. Skipping this step makes narrow features
    look sharper than the instrument could ever record them, which would inflate
    every separability number in the study — the exact kind of quiet
    optimism the proposal's Appendix B warns against.
    """
    sigma = float(fwhm_nm) / 2.3548200450309493      # FWHM -> sigma
    src = np.asarray(wl_src, dtype=np.float64)
    dst = np.asarray(wl_dst, dtype=np.float64)

    # (n_dst, n_src) response matrix, row-normalised. Truncated at 3 sigma so
    # the matrix is sparse in practice and far-off bands cannot leak in.
    d = dst[:, None] - src[None, :]
    W = np.exp(-0.5 * (d / sigma) ** 2)
    W[np.abs(d) > 3.0 * fwhm_nm] = 0.0
    rows = W.sum(axis=1, keepdims=True)
    W = np.divide(W, rows, out=np.zeros_like(W), where=rows > 0)

    return np.asarray(X, dtype=np.float64) @ W.T


def quality_filter(X: np.ndarray, wl: np.ndarray) -> np.ndarray:
    """
    Boolean mask of spectra that are physically plausible green foliage.

    Four rejections, in order of how often they fire on real archives:

    1. any non-finite value (instrument dropout);
    2. reflectance outside [0, 1.05] (bad white-reference or a transmittance
       measurement filed as reflectance);
    3. NDVI < 0.55 (not green foliage — could be bark, litter or a panel);
    4. NIR plateau below the red trough (physically impossible for a leaf; a
       reliable sign of a reversed or mis-scaled record).
    """
    X = np.asarray(X, dtype=np.float64)
    ok = np.isfinite(X).all(axis=1)
    ok &= (X >= -0.02).all(axis=1) & (X <= 1.05).all(axis=1)

    def at(nm):
        return X[:, int(np.argmin(np.abs(wl - nm)))]

    r670, r800 = at(670.0), at(800.0)
    ndvi = (r800 - r670) / np.maximum(r800 + r670, 1e-8)
    ok &= ndvi > 0.55
    ok &= r800 > r670
    return ok


# ==========================================================================
# Base model: real mean + real variance modes
# ==========================================================================
def base_leaf_model(X: np.ndarray, n_modes: int = 6) -> Dict[str, np.ndarray]:
    """
    Decompose a bank of measured leaf spectra into a mean plus the leading
    principal modes of its residual.

    Those modes are the *real* biological variability of tropical broadleaf
    foliage — leaf age, water status, thickness, pigment load. Drawing
    within-class variation from them (stage 03) produces synthetic spectra whose
    covariance structure resembles vegetation, rather than the white noise a
    naive simulator would use. This matters: white noise is trivially easy to
    classify through, and a pipeline tuned against it would over-promise.
    """
    X = np.asarray(X, dtype=np.float64)
    mu = X.mean(axis=0)
    R = X - mu
    # SVD rather than an explicit covariance eigendecomposition: numerically
    # better conditioned when n_samples < n_bands, which is the usual case here.
    U, S, Vt = np.linalg.svd(R, full_matrices=False)
    k = int(min(n_modes, Vt.shape[0]))
    modes = Vt[:k]                                     # (k, bands), orthonormal
    scores_sd = (S[:k] / np.sqrt(max(X.shape[0] - 1, 1)))
    return {
        "mean": mu,
        "modes": modes,
        "mode_sd": scores_sd,
        "explained_var_ratio": (S[:k] ** 2) / max(float((S ** 2).sum()), 1e-12),
        "n_source_spectra": np.array(X.shape[0]),
    }


# ==========================================================================
# Species differentiation — proposal §3.2 turned into operators
# ==========================================================================
def _gauss(wl: np.ndarray, centre: float, sigma: float) -> np.ndarray:
    """Unit-peak Gaussian on the wavelength axis."""
    return np.exp(-0.5 * ((wl - centre) / sigma) ** 2)


def _warp(spec: np.ndarray, wl: np.ndarray, shift: np.ndarray) -> np.ndarray:
    """
    Resample a spectrum on a locally shifted wavelength axis: R'(l) = R(l - d(l)).

    This is how a red-edge *position* shift is applied. Scaling reflectance
    cannot produce it — a position shift is a translation along the wavelength
    axis, and reproducing it correctly is the whole reason the sensor needs
    contiguous narrow bands (proposal §3.2, 680-750 nm row).
    """
    return np.interp(wl, wl + shift, spec)


def species_operator(base: np.ndarray, wl: np.ndarray, p: Dict[str, float]) -> np.ndarray:
    """
    Apply one species' spectral signature to the base leaf reflectance.

    Each parameter maps to a documented physical mechanism:

    ==================  ==========================================================
    ``chl_scale``       depth of the 675 nm chlorophyll-a well
    ``car_scale``       depth of the 490 nm carotenoid absorption
    ``ant_scale``       anthocyanin absorption on the green shoulder (~555 nm)
    ``green_peak_nm``   translation of the green reflectance maximum
    ``rep_shift_nm``    translation of the red edge (680-760 nm) — the key one
    ``nir_plateau``     amplitude of the 780-1000 nm structural plateau
    ``water_depth``     depth of the 970 nm leaf-water feature
    ==================  ==========================================================

    Absorption changes are applied multiplicatively in log space
    (``R' = R * exp(a * G(l))``) because absorption is exponential in
    concentration (Beer-Lambert), so a multiplicative operator is the physically
    right shape — an additive bump would let strong absorption go negative.
    """
    wl = np.asarray(wl, dtype=np.float64)
    R = np.asarray(base, dtype=np.float64).copy()

    # --- pigment absorption features -------------------------------------
    log_mod = np.zeros_like(wl)
    log_mod += -0.55 * (p["chl_scale"] - 1.0) * _gauss(wl, 675.0, 22.0)
    log_mod += -0.34 * (p["car_scale"] - 1.0) * _gauss(wl, 490.0, 30.0)
    log_mod += -0.22 * (p["ant_scale"] - 1.0) * _gauss(wl, 555.0, 20.0)
    log_mod += -0.30 * (p["water_depth"] - 1.0) * _gauss(wl, 970.0, 26.0)
    R = R * np.exp(log_mod)

    # --- NIR structural plateau ------------------------------------------
    # Smooth ramp so the transition sits inside the red edge rather than
    # producing a step discontinuity the derivative would light up as an artefact.
    ramp = 1.0 / (1.0 + np.exp(-(wl - 745.0) / 12.0))
    R = R * (1.0 + (p["nir_plateau"] - 1.0) * ramp)

    # --- wavelength-axis translations ------------------------------------
    shift = np.zeros_like(wl)
    shift += p["rep_shift_nm"] * _gauss(wl, 720.0, 30.0)               # red edge
    shift += (p["green_peak_nm"] - 550.0) * _gauss(wl, 555.0, 28.0)    # green peak
    if np.any(np.abs(shift) > 1e-6):
        R = _warp(R, wl, shift)

    return np.clip(R, 1e-4, 1.2)


def apply_season(R: np.ndarray, wl: np.ndarray, season: Dict[str, Any],
                 flower: Dict[str, float], is_target: bool,
                 contrast: float = 1.0) -> np.ndarray:
    """
    Apply phenology — proposal §5.1, mitigation (3): "treat phenology as a
    feature", running the baseline survey in the autumn flowering window where
    the signal is strongest, and an off-season classifier for early detection.

    Two effects:

    * ``leaf_water_scale`` deepens or shallows the 970 nm water feature with the
      wet/dry cycle — this is what makes a March-trained classifier drift by
      September, the risk in §5.4 row 6;
    * ``flower_fraction`` adds a bright white bloom, but **only to Mikania**, and
      only in autumn. That is why the RGB deep-learning literature works on
      *blooming* outbreak points and nowhere else (§1) — and why a spectral
      classifier that does not need the bloom is worth more.
    """
    wl = np.asarray(wl, dtype=np.float64)
    R = np.asarray(R, dtype=np.float64).copy()

    R = R * np.exp(-0.30 * (season.get("leaf_water_scale", 1.0) - 1.0) * _gauss(wl, 970.0, 26.0))

    # The bloom is scaled by contrast as well. It is genuine species information
    # — the whole reason RGB deep learning works on blooming outbreak points —
    # so "no species-distinguishing signal at all" (contrast 0) has to switch it
    # off too, or the control measures flower detection rather than chance.
    f = float(season.get("flower_fraction", 0.0)) * float(contrast) if is_target else 0.0
    if f > 0.0:
        anchors_nm = np.array([450.0, 550.0, 680.0, 800.0])
        anchors_r = np.array([flower["r450"], flower["r550"], flower["r680"], flower["r800"]])
        bloom = np.interp(wl, anchors_nm, anchors_r)
        R = (1.0 - f) * R + f * bloom          # areal mixture, not a tint

    return np.clip(R, 1e-4, 1.2)


# ==========================================================================
# Drawing realistic class samples
# ==========================================================================
def scaled_species_params(cfg: Dict[str, Any], key: str,
                          contrast: Optional[float] = None) -> Dict[str, float]:
    """
    Return one species' parameters with every deviation from spectral neutrality
    multiplied by the contrast scale.

    ``contrast = 0`` collapses the species onto the neutral leaf — the classes
    become spectrally identical and any classifier must fall to chance. That is
    a genuine control: if the pipeline still reports high accuracy at contrast 0,
    something is leaking, and the whole study is void. Stage 05 runs it for
    exactly that reason.

    ``contrast = 1`` is the nominal, literature-consistent configuration.
    """
    sc = cfg.get("species_contrast", {})
    if contrast is None:
        contrast = float(sc.get("scale", 1.0))
    contrast = float(contrast)
    neutral = sc.get("neutral", {})
    params = dict(cfg["species_spectra"][key])
    for pname, nval in neutral.items():
        if pname in params:
            params[pname] = nval + (params[pname] - nval) * contrast

    # Within-class variability must be neutralised too. Species differ in how
    # VARIABLE they are, and a classifier can exploit that difference in spread
    # even when the means coincide — so leaving it unscaled made the contrast-0
    # control report 75% instead of chance. Neutral is the cross-species mean.
    cvs = [float(v["within_class_cv"]) for v in cfg["species_spectra"].values()]
    cv_neutral = float(np.mean(cvs))
    params["within_class_cv"] = cv_neutral + (params["within_class_cv"] - cv_neutral) * contrast

    return params


def site_effect_params(cfg: Dict[str, Any], key: str, site_key: str) -> Dict[str, float]:
    """
    Draw the per-(site, species) random effect.

    Seeded off a stable hash of ``(seed, site_key, key)`` rather than off a
    running generator, so that the offsets are:

    * **consistent** — every pixel of that species at that site gets the same
      offset, which is what makes the residual spatially correlated;
    * **reproducible** — the same site always draws the same effect regardless
      of the order stages run in;
    * **independent across sites** — no accidental correlation that would make
      leave-one-site-out easier than it should be.

    Returns a multiplier/offset dict to be merged into the species parameters.
    """
    import hashlib

    sre = cfg.get("site_random_effects", {})
    if not sre:
        return {}
    tag = f"{cfg['project']['random_seed']}|{site_key}|{key}".encode()
    seed = int.from_bytes(hashlib.blake2b(tag, digest_size=8).digest(), "big")
    g = np.random.default_rng(seed)
    return {
        "rep_shift_nm": float(g.normal(0.0, sre.get("rep_shift_sd_nm", 0.0))),
        "green_peak_nm": float(g.normal(0.0, sre.get("green_peak_sd_nm", 0.0))),
        "chl_scale": float(np.exp(g.normal(0.0, sre.get("chl_scale_sd", 0.0)))),
        "car_scale": float(np.exp(g.normal(0.0, sre.get("car_scale_sd", 0.0)))),
        "nir_plateau": float(np.exp(g.normal(0.0, sre.get("nir_plateau_sd", 0.0)))),
        "water_depth": float(np.exp(g.normal(0.0, sre.get("water_depth_sd", 0.0)))),
        "background": float(g.normal(0.0, sre.get("background_shift_sd", 0.0))),
    }


def sample_class_spectra(lib: Dict[str, Any], cfg: Dict[str, Any], key: str,
                         season_key: str, n: int,
                         gen: np.random.Generator,
                         site_key: Optional[str] = None,
                         contrast: Optional[float] = None) -> np.ndarray:
    """
    Draw ``n`` plausible spectra for one vegetation class.

    Four stacked sources of variation, in decreasing order of magnitude. The
    ordering is the point: the nuisance terms are *larger* than the
    between-species contrasts, which is what makes this the hard field problem
    rather than the easy laboratory one.

    1. **Structural nuisance** — per-sample jitter on NIR plateau amplitude
       (leaf area index, leaf angle), chlorophyll content (leaf age, light
       environment) and red-edge position. Drawn from ``config.nuisance``.
    2. **Real biological modes** — projections onto the principal modes of the
       measured EcoSIS leaf bank, so the synthetic covariance structure is that
       of real foliage rather than white noise.
    3. **Brightness** — log-normal multiplicative factor for local illumination.
    4. **Species signature** — the §3.2 operator, applied last so the nuisance
       terms modulate it rather than being erased by it.

    Sensor noise is *not* added here; it belongs with the SNR model in the scene
    simulator (stage 03), because its magnitude depends on the acquisition.
    """
    wl = lib["wavelengths"]
    nz = cfg.get("nuisance", {})
    _c = float(contrast if contrast is not None
               else cfg.get("species_contrast", {}).get("scale", 1.0))
    params = scaled_species_params(cfg, key, _c)
    season = cfg["phenology"]["seasons"][season_key]
    is_target = (key == cfg["confusable_pair"]["target"])
    cv = float(params["within_class_cv"])

    # --- site-level random effect (applied to the class mean) -------------
    bg_shift = 0.0
    if site_key is not None:
        se = site_effect_params(cfg, key, site_key)
        if se:
            params["rep_shift_nm"] = params["rep_shift_nm"] + se["rep_shift_nm"]
            params["green_peak_nm"] = params["green_peak_nm"] + se["green_peak_nm"]
            params["chl_scale"] = params["chl_scale"] * se["chl_scale"]
            params["car_scale"] = params["car_scale"] * se["car_scale"]
            params["nir_plateau"] = params["nir_plateau"] * se["nir_plateau"]
            params["water_depth"] = params["water_depth"] * se["water_depth"]
            bg_shift = se["background"]

    # --- per-sample nuisance-perturbed species means ---------------------
    # Every parameter that carries species information is jittered here. If one
    # were left un-jittered, its between-species difference would sit in a
    # direction of zero within-class variance and become trivially separable —
    # a purely numerical artefact that would inflate every accuracy downstream.
    jit = {
        "nir_plateau": ("lai_plateau_cv", "mul"),
        "chl_scale": ("chl_content_cv", "mul"),
        "car_scale": ("car_content_cv", "mul"),
        "ant_scale": ("ant_content_cv", "mul"),
        "water_depth": ("water_content_cv", "mul"),
        "rep_shift_nm": ("rep_jitter_nm", "add"),
        "green_peak_nm": ("green_peak_jitter_nm", "add"),
    }

    X = np.empty((n, wl.size), dtype=np.float64)
    for i in range(n):
        p = dict(params)
        for pname, (cfg_key, mode) in jit.items():
            s = float(nz.get(cfg_key, 0.0))
            if s <= 0.0:
                continue
            if mode == "mul":
                p[pname] = params[pname] * float(np.exp(gen.normal(0.0, s)))
            else:
                p[pname] = params[pname] + float(gen.normal(0.0, s))
        m = species_operator(lib["base"]["mean"], wl, p)
        X[i] = apply_season(m, wl, season, cfg["phenology"]["flower_reflectance"],
                            is_target, contrast=_c)

    # --- real biological variance modes -----------------------------------
    modes = lib["base"]["modes"]
    sd = lib["base"]["mode_sd"]
    scores = gen.normal(0.0, 1.0, size=(n, modes.shape[0])) * sd[None, :] * (cv / 0.08)
    X = X + scores @ modes

    # --- illumination amplitude -------------------------------------------
    X *= np.exp(gen.normal(0.0, float(nz.get("brightness_cv", cv * 0.55)), size=(n, 1)))

    # --- canopy-patch composition ------------------------------------------
    # Mix in shaded leaf area, non-photosynthetic material and visible substrate.
    # Fractions are truncated half-normals: never negative, and capped so that
    # green foliage still dominates (otherwise the sample is not that class).
    em = lib.get("endmembers", {})
    if em:
        def _frac(mean_key, sd_key, cap):
            # bg_shift moves the whole site's background composition together:
            # a wetter, more closed catchment carries more shadow and litter
            # everywhere, not independently per pixel.
            m = float(nz.get(mean_key, 0.0)) * float(np.exp(bg_shift))
            s = float(nz.get(sd_key, 0.0))
            if m <= 0.0 and s <= 0.0:
                return np.zeros((n, 1))
            return np.clip(gen.normal(m, s, size=(n, 1)), 0.0, cap)

        f_sh = _frac("background_shadow_mean", "background_shadow_sd", 0.35)
        f_np = _frac("background_npv_mean", "background_npv_sd", 0.30)
        f_so = _frac("background_soil_mean", "background_soil_sd", 0.20)
        total = f_sh + f_np + f_so
        over = total > 0.55
        if np.any(over):
            scale = np.where(over, 0.55 / np.maximum(total, 1e-6), 1.0)
            f_sh, f_np, f_so = f_sh * scale, f_np * scale, f_so * scale
            total = f_sh + f_np + f_so

        X = ((1.0 - total) * X
             + f_sh * em["shadow"][None, :]
             + f_np * em.get("npv", em["soil_rock"])[None, :]
             + f_so * em["soil_rock"][None, :])

    return np.clip(X, 1e-4, 1.2)


# ==========================================================================
# Non-vegetation endmembers
# ==========================================================================
def soil_rock_endmember(wl: np.ndarray) -> np.ndarray:
    """
    Weathered granitic / lateritic soil — the dominant exposed substrate in
    Hong Kong's country parks.

    Modelled, not measured: a monotonic rise from blue to NIR with the
    ferric-iron shoulder near 900 nm and the Fe(3+) crystal-field feature near
    500 nm that give lateritic soils their red colour. Flagged as modelled in
    the library metadata.
    """
    wl = np.asarray(wl, dtype=np.float64)
    R = 0.085 + 0.00040 * (wl - 400.0)
    R *= (1.0 - 0.16 * _gauss(wl, 500.0, 60.0))
    R *= (1.0 - 0.07 * _gauss(wl, 900.0, 90.0))
    return np.clip(R, 1e-4, 1.2)


def npv_endmember(wl: np.ndarray) -> np.ndarray:
    """
    Non-photosynthetic vegetation: dry stems, litter, senescent leaves.

    The defining property is the *absence* of the chlorophyll well and the red
    edge — reflectance rises smoothly and monotonically from blue to NIR with
    only weak lignin/cellulose structure in the VNIR. NPV is always present in a
    real canopy patch and always absent from a contact-probe leaf measurement,
    which is precisely why laboratory separability overstates field separability
    (proposal §4.1: "88.71% is a laboratory result ... field performance will be
    lower and any proposal claiming otherwise is not credible").
    """
    wl = np.asarray(wl, dtype=np.float64)
    R = 0.10 + 0.00055 * (wl - 400.0)
    R *= (1.0 - 0.10 * _gauss(wl, 670.0, 90.0))     # residual pigment, very shallow
    return np.clip(R, 1e-4, 1.2)


def shadow_endmember(wl: np.ndarray) -> np.ndarray:
    """
    Deep shadow under closed canopy: illuminated only by diffuse skylight
    (Rayleigh, strongly blue-weighted) plus a little green light transmitted
    through the leaves above.

    Getting this endmember right matters more than it looks. Shadow is 10%+ of a
    steep subtropical scene; if it is treated as "dark vegetation" the unmixer
    pushes the deficit into whichever green endmember is nearest, and shaded host
    canopy starts being reported as Mikania. Proposal §5.2, canopy-occlusion row.
    """
    wl = np.asarray(wl, dtype=np.float64)
    rayleigh = (450.0 / wl) ** 4.0
    transmitted = 0.35 * _gauss(wl, 550.0, 40.0) + 0.55 * (wl > 750.0)
    R = 0.022 * rayleigh + 0.016 * transmitted
    return np.clip(R, 1e-4, 1.2)


# ==========================================================================
# Library assembly
# ==========================================================================
def build_library(cfg: Optional[Dict[str, Any]] = None,
                  n_modes: int = 6) -> Dict[str, Any]:
    """
    Build the complete endmember library.

    Returns a dict with:

    ``wavelengths``  (bands,) sensor grid
    ``endmembers``   key -> (bands,) mean reflectance for each class
    ``base``         the real-leaf mean + variance modes (for stage 03)
    ``provenance``   per-endmember 'measured' / 'measured+modelled' / 'modelled'

    If ``data/raw/field_spectra/*.csv`` exists — the Phase 0 deliverable — those
    real Hong Kong measurements replace the modelled species block entirely and
    the provenance flips to 'measured'. The code path is here now so that
    swapping in field data later is a drop-in, not a rewrite.
    """
    cfg = cfg or load_config()
    wl = wavelengths(cfg)
    sens = cfg["sensor"]

    # ---- 1. real measured base -----------------------------------------
    banks: List[np.ndarray] = []
    sources: List[str] = []
    for pkg in cfg["open_data"]["ecosis"]["packages"]:
        matches = glob.glob(os.path.join(PATHS.raw, f"ecosis_{pkg['name'][:48]}*.csv"))
        if not matches:
            continue
        X, wl_src = load_ecosis_csv(matches[0], pkg.get("orientation", "auto"))
        keep = (wl_src >= 380.0) & (wl_src <= 1050.0)
        if keep.sum() < 50:
            continue
        Xr = resample_to_sensor(X[:, keep], wl_src[keep], wl, sens["fwhm_nm"])
        # Some archives store reflectance as percent (0-100) rather than 0-1.
        if np.nanmedian(Xr) > 1.5:
            Xr = Xr / 100.0
        ok = quality_filter(Xr, wl)
        if ok.sum() >= 5:
            banks.append(Xr[ok])
            sources.append(f"{pkg['name']} (n={int(ok.sum())}/{X.shape[0]} passed QC)")

    if not banks:
        raise RuntimeError(
            "No measured leaf spectra available. Run scripts/01_fetch_open_data.py first — "
            "this pipeline deliberately refuses to invent a base leaf reflectance curve."
        )

    measured = np.vstack(banks)
    base = base_leaf_model(measured, n_modes=n_modes)

    # ---- 2. optional real Hong Kong field spectra ----------------------
    field_dir = os.path.join(PATHS.raw, "field_spectra")
    field_means: Dict[str, np.ndarray] = {}
    if os.path.isdir(field_dir):
        for f in sorted(glob.glob(os.path.join(field_dir, "*.csv"))):
            key = os.path.splitext(os.path.basename(f))[0]
            df = pd.read_csv(f)
            wcols = _numeric_columns(df.columns)
            if not wcols:
                continue
            wl_src = np.array([float(str(c).strip()) for c in wcols])
            Xf = resample_to_sensor(df[wcols].to_numpy(float), wl_src, wl, sens["fwhm_nm"])
            field_means[key] = Xf[quality_filter(Xf, wl)].mean(axis=0)

    # ---- 3. species endmembers ------------------------------------------
    endmembers: Dict[str, np.ndarray] = {}
    provenance: Dict[str, str] = {}
    for key, params in cfg["species_spectra"].items():
        if key in field_means:
            endmembers[key] = field_means[key]
            provenance[key] = "measured (Hong Kong field spectroradiometer)"
        else:
            endmembers[key] = species_operator(base["mean"], wl, params)
            provenance[key] = (
                "measured base (EcoSIS tropical broadleaf) + modelled species "
                "perturbation from config.species_spectra"
            )

    endmembers["soil_rock"] = soil_rock_endmember(wl)
    provenance["soil_rock"] = "modelled (lateritic/granitic soil optics)"
    endmembers["shadow"] = shadow_endmember(wl)
    provenance["shadow"] = "modelled (Rayleigh skylight + canopy transmittance)"
    endmembers["npv"] = npv_endmember(wl)
    provenance["npv"] = "modelled (dry stem / litter, no chlorophyll well)"

    return {
        "wavelengths": wl,
        "endmembers": endmembers,
        "base": base,
        "provenance": provenance,
        "measured_sources": sources,
        "n_measured_spectra": int(measured.shape[0]),
        "measured_bank": measured,
    }


def save_library(lib: Dict[str, Any], path: str) -> str:
    """Persist the library as npz. Endmembers are stored one array per key."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload: Dict[str, Any] = {
        "wavelengths": lib["wavelengths"],
        "base_mean": lib["base"]["mean"],
        "base_modes": lib["base"]["modes"],
        "base_mode_sd": lib["base"]["mode_sd"],
        "base_explained": lib["base"]["explained_var_ratio"],
        "measured_bank": lib["measured_bank"],
        "endmember_keys": np.array(sorted(lib["endmembers"])),
        "provenance_json": np.array(__import__("json").dumps({
            "per_endmember": lib["provenance"],
            "measured_sources": lib["measured_sources"],
            "n_measured_spectra": lib["n_measured_spectra"],
        })),
    }
    for k, v in lib["endmembers"].items():
        payload[f"em_{k}"] = v
    np.savez_compressed(path, **payload)
    return path


def load_library(path: str) -> Dict[str, Any]:
    """Inverse of :func:`save_library`."""
    import json as _json

    z = np.load(path, allow_pickle=False)
    keys = [str(k) for k in z["endmember_keys"]]
    return {
        "wavelengths": z["wavelengths"],
        "endmembers": {k: z[f"em_{k}"] for k in keys},
        "base": {
            "mean": z["base_mean"], "modes": z["base_modes"],
            "mode_sd": z["base_mode_sd"], "explained_var_ratio": z["base_explained"],
        },
        "measured_bank": z["measured_bank"],
        **_json.loads(str(z["provenance_json"])),
    }
