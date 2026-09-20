"""
Interpretable spectral features.

Two families live here, and the contrast between them *is* the commercial
argument in the proposal (§1, §6.1):

**Family A — broadband indices that a multispectral drone can compute.**
EGI, NEGI, BGDI, GRDI, NGRDI and the Plant Pigment Ratio. Published UAV work on
Mikania tested exactly these six and found that *none* of them separated Mikania
from its host plants. They are implemented here not because we expect them to
work but because reproducing that negative result on our own data is the single
most persuasive slide in the deck: it demonstrates the moat rather than
asserting it.

**Family B — narrow-band features that require contiguous sampling.**
Red-edge *position*, green-peak position, chlorophyll well depth, NIR plateau
slope, the 970 nm water feature, PRI and anthocyanin ratios. Every one of these
needs bands a 5-channel sensor does not have. These are what the classifier
actually stands on, and what we show AFCD when they ask what the model is
looking at.

All functions take ``X`` as (n_samples, n_bands) reflectance and ``wl`` as the
matching wavelength grid in nanometres.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from .preprocess import savgol


# ==========================================================================
# Band access
# ==========================================================================
def _at(X: np.ndarray, wl: np.ndarray, nm: float) -> np.ndarray:
    """Reflectance at the band nearest ``nm``."""
    return X[:, int(np.argmin(np.abs(wl - nm)))]


def _window(X: np.ndarray, wl: np.ndarray, lo: float, hi: float) -> Tuple[np.ndarray, np.ndarray]:
    """The sub-spectrum inside [lo, hi] nm, plus its wavelengths."""
    m = (wl >= lo) & (wl <= hi)
    return X[:, m], wl[m]


def _broadband(X: np.ndarray, wl: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Simulate an RGB camera's three channels by integrating the hyperspectral
    cube over realistic Bayer-filter passbands.

    Doing it this way — rather than picking three single bands — is what makes
    the negative-result reproduction *fair*. A consumer camera genuinely
    integrates ~80-100 nm of spectrum per channel, and that integration is
    precisely the information loss we are claiming defeats it.
    """
    b = X[:, (wl >= 430) & (wl <= 500)].mean(axis=1)
    g = X[:, (wl >= 500) & (wl <= 580)].mean(axis=1)
    r = X[:, (wl >= 590) & (wl <= 680)].mean(axis=1)
    return r, g, b


# ==========================================================================
# Family A — the indices published work found insufficient
# ==========================================================================
def broadband_indices(X: np.ndarray, wl: np.ndarray) -> Dict[str, np.ndarray]:
    """
    The six RGB indices tested in the UAV Mikania literature.

    Definitions (fixed here so the reproduction is auditable, since the
    literature is not perfectly consistent about GRDI vs NGRDI):

    ==========  =================================  ================================
    Index       Formula                            What it is supposed to track
    ==========  =================================  ================================
    EGI         2G - R - B                         green vegetation abundance
    NEGI        2g - r - b, on normalised r,g,b    EGI, illumination-normalised
    BGDI        (B - G) / (B + G)                  blue/green pigment balance
    GRDI        G - R                              raw green-red contrast
    NGRDI       (G - R) / (G + R)                  normalised green-red contrast
    PPR         (G - B) / (G + B)                  "plant pigment ratio"
    ==========  =================================  ================================
    """
    r, g, b = _broadband(X, wl)
    s = np.maximum(r + g + b, 1e-8)
    rn, gn, bn = r / s, g / s, b / s
    return {
        "EGI":   2.0 * g - r - b,
        "NEGI":  2.0 * gn - rn - bn,
        "BGDI":  (b - g) / np.maximum(b + g, 1e-8),
        "GRDI":  g - r,
        "NGRDI": (g - r) / np.maximum(g + r, 1e-8),
        "PPR":   (g - b) / np.maximum(g + b, 1e-8),
    }


# ==========================================================================
# Family B — narrow-band features
# ==========================================================================
def red_edge_position(X: np.ndarray, wl: np.ndarray,
                      window: Tuple[float, float] = (680.0, 760.0),
                      method: str = "derivative") -> np.ndarray:
    """
    Red-edge inflection position (REP), in nanometres.

    This is *the* feature the proposal's §3.2 table calls out as structurally
    invisible to multispectral: a 5-band sensor gives you a red-edge *band*, and
    what discriminates these species is a shift of a few nanometres in the
    red-edge *position*.

    Two estimators:

    ``derivative``
        Sub-band-resolution argmax of the SG first derivative, refined by fitting
        a parabola through the peak and its two neighbours. Resolves shifts far
        smaller than the 5 nm band spacing, which is necessary — the modelled
        inter-species shifts are 1.5 to 4.5 nm.

    ``linear4``
        The classical four-point linear interpolation (Guyot & Baret):
        R_re = (R670 + R780)/2, then REP = 700 + 40 * (R_re - R700)/(R740 - R700).
        Cheaper, more robust in noise, less precise. Kept for cross-checking.
    """
    if method == "linear4":
        r670, r700, r740, r780 = (_at(X, wl, n) for n in (670.0, 700.0, 740.0, 780.0))
        r_re = 0.5 * (r670 + r780)
        return 700.0 + 40.0 * (r_re - r700) / np.maximum(r740 - r700, 1e-8)

    d1 = savgol(X, deriv=1, delta_nm=float(np.median(np.diff(wl))))
    Xw, wlw = _window(d1, wl, *window)
    k = np.argmax(Xw, axis=1)

    # Parabolic refinement around the discrete peak. Interior peaks only; a peak
    # pinned at a window edge is returned as the edge wavelength.
    rep = wlw[k].astype(np.float64)
    interior = (k > 0) & (k < Xw.shape[1] - 1)
    if np.any(interior):
        idx = np.where(interior)[0]
        kk = k[idx]
        y0 = Xw[idx, kk - 1]
        y1 = Xw[idx, kk]
        y2 = Xw[idx, kk + 1]
        denom = (y0 - 2.0 * y1 + y2)
        shift = np.where(np.abs(denom) > 1e-12, 0.5 * (y0 - y2) / np.where(np.abs(denom) > 1e-12, denom, 1.0), 0.0)
        step = float(np.median(np.diff(wlw)))
        rep[idx] = wlw[kk] + np.clip(shift, -1.0, 1.0) * step
    return rep


def green_peak_position(X: np.ndarray, wl: np.ndarray,
                        window: Tuple[float, float] = (520.0, 600.0)) -> np.ndarray:
    """
    Wavelength of the green reflectance maximum, parabola-refined.

    Shifts with the chlorophyll a/b ratio and carotenoid load — proposal §3.2,
    500-600 nm row. A single 40 nm "green" band integrates the whole feature
    away, which is the point.
    """
    Xw, wlw = _window(X, wl, *window)
    k = np.argmax(Xw, axis=1)
    pos = wlw[k].astype(np.float64)
    interior = (k > 0) & (k < Xw.shape[1] - 1)
    if np.any(interior):
        idx = np.where(interior)[0]
        kk = k[idx]
        y0, y1, y2 = Xw[idx, kk - 1], Xw[idx, kk], Xw[idx, kk + 1]
        denom = (y0 - 2.0 * y1 + y2)
        shift = np.where(np.abs(denom) > 1e-12, 0.5 * (y0 - y2) / np.where(np.abs(denom) > 1e-12, denom, 1.0), 0.0)
        step = float(np.median(np.diff(wlw)))
        pos[idx] = wlw[kk] + np.clip(shift, -1.0, 1.0) * step
    return pos


def narrowband_indices(X: np.ndarray, wl: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Physiologically-motivated narrow-band indices, each requiring bands a
    multispectral sensor does not have.

    ========  ==========================================  ==========================
    Index     Formula                                     Tracks
    ========  ==========================================  ==========================
    NDVI      (R800 - R670)/(R800 + R670)                 greenness / LAI (baseline)
    RENDVI    (R750 - R705)/(R750 + R705)                 red-edge chlorophyll
    mND705    (R750 - R705)/(R750 + R705 - 2*R445)        as above, haze-corrected
    PRI       (R531 - R570)/(R531 + R570)                 xanthophyll / light use
    ARI       1/R550 - 1/R700                             anthocyanin
    CRI       1/R510 - 1/R550                             carotenoid
    PSRI      (R680 - R500)/R750                          senescence
    WBI       R900 / R970                                 leaf water content
    NIR_slope d/dwl of the 780-900 nm plateau             mesophyll structure / LAI
    RED_DEPTH continuum depth of the 660-690 nm well      chlorophyll absorption
    ========  ==========================================  ==========================
    """
    def R(n):  # noqa: N802 — matches the notation used in the index literature
        return _at(X, wl, n)

    r445, r500, r510, r531, r550, r570 = (R(n) for n in (445, 500, 510, 531, 550, 570))
    r670, r680, r700, r705, r750, r800, r900, r970 = (R(n) for n in (670, 680, 700, 705, 750, 800, 900, 970))

    # Plateau slope: least-squares gradient over 780-900 nm, per spectrum.
    Xp, wlp = _window(X, wl, 780.0, 900.0)
    wc = wlp - wlp.mean()
    nir_slope = (Xp * wc).sum(axis=1) / max((wc ** 2).sum(), 1e-8)

    # Chlorophyll well depth relative to a 620-760 nm shoulder-to-shoulder line.
    r620, r760 = R(620), R(760)
    cont_675 = r620 + (r760 - r620) * (675.0 - 620.0) / (760.0 - 620.0)
    red_depth = 1.0 - R(675) / np.maximum(cont_675, 1e-8)

    def _sd(a, b):
        return (a - b) / np.maximum(a + b, 1e-8)

    return {
        "NDVI":      _sd(r800, r670),
        "RENDVI":    _sd(r750, r705),
        "mND705":    (r750 - r705) / np.maximum(r750 + r705 - 2.0 * r445, 1e-8),
        "PRI":       _sd(r531, r570),
        "ARI":       1.0 / np.maximum(r550, 1e-3) - 1.0 / np.maximum(r700, 1e-3),
        "CRI":       1.0 / np.maximum(r510, 1e-3) - 1.0 / np.maximum(r550, 1e-3),
        "PSRI":      (r680 - r500) / np.maximum(r750, 1e-8),
        "WBI":       r900 / np.maximum(r970, 1e-8),
        "NIR_slope": nir_slope * 1e3,     # per 1000 nm, so magnitudes read nicely
        "RED_DEPTH": red_depth,
    }


# ==========================================================================
# Which sensor can actually compute each feature
# ==========================================================================
# This table is the honest version of the moat argument, and it costs us the
# easiest headline. NDVI is NOT a hyperspectral feature: any agricultural
# multispectral drone (MicaSense RedEdge, DJI P4M, Sentinel-2) has red and NIR
# bands and computes it directly. Filing it under "narrowband" would have
# inflated the hyperspectral advantage with a feature the competition already
# has. Three tiers:
#
#   rgb            a consumer camera can compute it (3 broad visible channels)
#   multispectral  a 5-band ag sensor can (blue, green, red, red-edge, NIR)
#   hyperspectral  requires contiguous narrow bands — the actual moat
#
# A feature is 'hyperspectral' only if it needs either (a) a band position no
# 5-band sensor carries, or (b) sub-band-width resolution of a feature POSITION.
SENSOR_REQUIREMENT: Dict[str, str] = {
    # --- Family A: the six indices published UAV work found insufficient ----
    "bb_EGI": "rgb", "bb_NEGI": "rgb", "bb_BGDI": "rgb",
    "bb_GRDI": "rgb", "bb_NGRDI": "rgb", "bb_PPR": "rgb",
    # --- computable by a 5-band multispectral sensor ------------------------
    "nb_NDVI": "multispectral",       # red + NIR — every ag drone has these
    "nb_RENDVI": "multispectral",     # 705/750 approximated by a red-edge band
    # --- genuinely require contiguous narrow bands ---------------------------
    "nb_PRI": "hyperspectral",        # 531 vs 570 nm, 10 nm apart
    "nb_ARI": "hyperspectral",        # 550 and 700 nm narrow inverses
    "nb_CRI": "hyperspectral",        # 510 and 550 nm narrow inverses
    "nb_PSRI": "hyperspectral",       # 500/680/750 nm narrow
    "nb_mND705": "hyperspectral",     # needs 445 nm haze band alongside 705/750
    "nb_WBI": "hyperspectral",        # 900 vs 970 nm — no ag sensor carries 970
    "nb_NIR_slope": "hyperspectral",  # a slope needs many contiguous bands
    "nb_RED_DEPTH": "hyperspectral",  # continuum depth needs the whole well
    "nb_REP_deriv": "hyperspectral",  # red-edge POSITION, sub-band resolution
    "nb_REP_linear4": "hyperspectral",
    "nb_GREEN_PEAK": "hyperspectral",  # green-peak POSITION
}


def sensor_requirement(feature_name: str) -> str:
    """Which sensor class can compute ``feature_name``. Unknown -> hyperspectral."""
    return SENSOR_REQUIREMENT.get(feature_name, "hyperspectral")


# --------------------------------------------------------------------------
# Sensor ablation — the fair head-to-head
# --------------------------------------------------------------------------
# Real band definitions, so the comparison is against actual products rather
# than a straw man. Each entry is (centre_nm, full_width_nm).
SENSOR_TIERS: Dict[str, Dict[str, Any]] = {
    "rgb": {
        "label": "RGB camera (consumer Bayer)",
        "example": "DJI Zenmuse P1 / any consumer payload",
        # Bayer filters are broad and overlapping; these are nominal passbands.
        "bands": [(465.0, 70.0), (540.0, 80.0), (635.0, 90.0)],
    },
    "multispectral": {
        "label": "5-band multispectral",
        "example": "MicaSense RedEdge-MX / DJI P4 Multispectral",
        "bands": [(475.0, 32.0), (560.0, 27.0), (668.0, 16.0),
                  (717.0, 12.0), (842.0, 57.0)],
    },
    "hyperspectral": {
        "label": "VNIR hyperspectral pushbroom",
        "example": "400-1000 nm, 121 contiguous bands",
        "bands": None,          # all of them
    },
}


def resample_to_tier(X: np.ndarray, wl: np.ndarray, tier: str
                     ) -> Tuple[np.ndarray, List[str]]:
    """
    Degrade a hyperspectral matrix to what a cheaper sensor would have recorded.

    Each output band is the reflectance averaged over its passband — which is
    physically what a broad filter does, and is the information loss the whole
    business case turns on.

    Returns ``(bands, names)``. Use :func:`tier_feature_matrix` to get the
    classifier-ready feature set.
    """
    spec = SENSOR_TIERS[tier]
    if spec["bands"] is None:
        return np.asarray(X, dtype=np.float64), [f"{w:.0f}nm" for w in wl]

    cols, names = [], []
    for c, fw in spec["bands"]:
        m = (wl >= c - fw / 2.0) & (wl <= c + fw / 2.0)
        if not m.any():                     # passband outside our range
            m = np.zeros_like(wl, dtype=bool)
            m[int(np.argmin(np.abs(wl - c)))] = True
        cols.append(X[:, m].mean(axis=1))
        names.append(f"{c:.0f}nm")
    return np.column_stack(cols), names


def tier_feature_matrix(X: np.ndarray, wl: np.ndarray, tier: str
                        ) -> Tuple[np.ndarray, List[str]]:
    """
    Build the *best possible* feature set for a given sensor tier.

    This is where the comparison is made fair rather than rigged. A 5-band
    sensor is not limited to five raw numbers: practitioners compute every
    normalised difference and simple ratio between its bands. So each low-band
    tier gets its raw bands PLUS every pairwise normalised difference
    (a-b)/(a+b) PLUS every pairwise ratio — 5 bands become 25 features. If
    hyperspectral still wins after that handicap, the advantage is real.

    The hyperspectral tier gets its raw bands plus the SG first derivative,
    which is the standard chemometric treatment and is *unavailable* below ~20
    contiguous bands (you cannot fit a smoothing polynomial through 5 scattered
    points and call the result a derivative).
    """
    from .preprocess import savgol

    B, names = resample_to_tier(X, wl, tier)
    n_b = B.shape[1]

    if tier == "hyperspectral":
        d1 = savgol(B, deriv=1, delta_nm=float(np.median(np.diff(wl))))
        return (np.column_stack([B, d1]),
                [f"R{n}" for n in names] + [f"d1_{n}" for n in names])

    feats = [B]
    fnames = [f"R{n}" for n in names]
    for i in range(n_b):
        for j in range(i + 1, n_b):
            a, b = B[:, i], B[:, j]
            feats.append(((a - b) / np.maximum(a + b, 1e-8))[:, None])
            fnames.append(f"ND({names[i]},{names[j]})")
            feats.append((a / np.maximum(b, 1e-8))[:, None])
            fnames.append(f"R({names[i]}/{names[j]})")
    return np.column_stack(feats), fnames


# ==========================================================================
# Combined descriptor
# ==========================================================================
def interpretable_features(X: np.ndarray, wl: np.ndarray,
                           cfg_feat: Dict[str, Any] | None = None
                           ) -> Tuple[np.ndarray, List[str]]:
    """
    Assemble every named feature into ``(matrix, names)``.

    Used for three things: the "what is the model looking at" section of the
    AFCD report, the spectral explorer in the web platform, and the
    broadband-vs-narrowband separability comparison that reproduces the
    published negative result.
    """
    cfg_feat = cfg_feat or {}
    rew = tuple(cfg_feat.get("red_edge_window_nm", [680.0, 760.0]))
    gpw = tuple(cfg_feat.get("green_peak_window_nm", [520.0, 600.0]))

    feats: Dict[str, np.ndarray] = {}
    feats.update({f"bb_{k}": v for k, v in broadband_indices(X, wl).items()})
    feats.update({f"nb_{k}": v for k, v in narrowband_indices(X, wl).items()})
    feats["nb_REP_deriv"] = red_edge_position(X, wl, rew, method="derivative")
    feats["nb_REP_linear4"] = red_edge_position(X, wl, rew, method="linear4")
    feats["nb_GREEN_PEAK"] = green_peak_position(X, wl, gpw)

    names = sorted(feats)
    return np.column_stack([feats[n] for n in names]).astype(np.float64), names


def separability(X: np.ndarray, y: np.ndarray, a: int, b: int) -> float:
    """
    Two-class separability of a single feature, as a normalised distance.

        d' = |mu_a - mu_b| / sqrt(0.5 * (var_a + var_b))

    Also called the Fisher ratio (square-rooted) or, in detection theory, d'.
    A value below ~1 means the two classes overlap so heavily that no threshold
    on this feature can usefully split them.

    This is the statistic that makes the "broadband indices cannot do this"
    claim quantitative instead of rhetorical.
    """
    xa, xb = X[y == a], X[y == b]
    if xa.size == 0 or xb.size == 0:
        return float("nan")
    pooled = 0.5 * (xa.var(ddof=1) + xb.var(ddof=1))
    return float(abs(xa.mean() - xb.mean()) / np.sqrt(max(pooled, 1e-12)))
