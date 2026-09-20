"""
Spectral preprocessing — the chemometric front end.

This is the chain Huang et al. (2021) used to reach 88.71% on *Mikania
micrantha* under laboratory conditions, and the same chain already validated in
the flame-retardant safety-net work in this repository:

    reflectance -> Savitzky-Golay smoothing -> derivative -> SNV -> PCA -> RF/SVM

Why each step earns its place
-----------------------------
**Savitzky-Golay** fits a low-order polynomial in a sliding window, so it
smooths without the peak-flattening a boxcar causes — essential when the
discriminating feature *is* the shape of the red edge.

**Derivatives** remove additive offsets (path radiance, stray light) at first
order and multiplicative-slope terms at second order. Crucially, the red-edge
*position* — the feature that a 5-band multispectral sensor structurally cannot
measure (proposal §3.2) — is the argmax of the first derivative.

**SNV** (standard normal variate) centres and scales each spectrum
individually, which removes the illumination-amplitude term introduced by slope,
aspect and canopy geometry. In steep Hong Kong terrain under a moving sun this
is not a nicety; it is the difference between a classifier that learns species
and one that learns which side of the hill a pixel is on (proposal §5.1, risk 4).

**Continuum removal** normalises each spectrum by its convex hull, isolating
absorption-feature *depth* from the continuum it sits on — the standard way to
compare pigment absorption between samples of different overall brightness.

Everything here operates on either a (n_samples, n_bands) matrix or a
(lines, samples, bands) cube; :func:`as_matrix` / :func:`as_cube` convert.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.signal import savgol_filter


# ==========================================================================
# Shape helpers
# ==========================================================================
def as_matrix(x: np.ndarray) -> Tuple[np.ndarray, Optional[Tuple[int, int]]]:
    """
    Flatten a cube to (n_pixels, n_bands), remembering its spatial shape.
    A matrix is returned unchanged with ``shape=None``.
    """
    a = np.asarray(x)
    if a.ndim == 3:
        h, w, b = a.shape
        return a.reshape(h * w, b), (h, w)
    if a.ndim == 2:
        return a, None
    raise ValueError(f"expected 2-D or 3-D array, got shape {a.shape}")


def as_cube(m: np.ndarray, shape: Optional[Tuple[int, int]]) -> np.ndarray:
    """Inverse of :func:`as_matrix`."""
    if shape is None:
        return m
    return m.reshape(shape[0], shape[1], m.shape[-1])


# ==========================================================================
# Individual transforms
# ==========================================================================
def savgol(X: np.ndarray, window_length: int = 11, polyorder: int = 3,
           deriv: int = 0, delta_nm: float = 5.0) -> np.ndarray:
    """
    Savitzky-Golay smoothing / differentiation along the spectral axis.

    ``delta_nm`` is the band spacing, so first derivatives come out in
    reflectance-per-nanometre rather than reflectance-per-band-index. That makes
    the red-edge position and slope features physically comparable across
    sensors with different band spacing — worth the extra argument.

    The window is clamped to an odd length no larger than the number of bands,
    because scipy raises rather than degrading gracefully and a short spectrum
    (e.g. a resampled 5-band comparison run) should still work.
    """
    X = np.asarray(X, dtype=np.float64)
    nb = X.shape[-1]
    wl = int(window_length)
    if wl % 2 == 0:
        wl += 1
    wl = max(polyorder + 1 + (polyorder % 2 == 0), min(wl, nb if nb % 2 else nb - 1))
    if wl <= polyorder:
        return X if deriv == 0 else np.gradient(X, delta_nm, axis=-1)
    return savgol_filter(X, window_length=wl, polyorder=polyorder,
                         deriv=deriv, delta=delta_nm, axis=-1, mode="interp")


def snv(X: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """
    Standard Normal Variate: per-spectrum z-scoring.

        x' = (x - mean(x)) / std(x)

    Removes the multiplicative illumination factor that slope/aspect/BRDF impose
    on every band equally. After SNV a sunlit and a shaded leaf of the same
    species land on top of each other, which is exactly what we want the
    classifier to see.
    """
    X = np.asarray(X, dtype=np.float64)
    mu = X.mean(axis=-1, keepdims=True)
    sd = X.std(axis=-1, keepdims=True)
    return (X - mu) / np.maximum(sd, eps)


def continuum_removal(X: np.ndarray, wavelengths: np.ndarray) -> np.ndarray:
    """
    Convex-hull continuum removal.

    For each spectrum, build the upper convex hull over (wavelength,
    reflectance), interpolate it back onto the band grid, and divide. Output is
    <= 1 everywhere, equal to 1 on the hull, and dips to the relative depth of
    each absorption feature.

    Implemented with a monotone-chain upper hull rather than scipy's QHull: it is
    O(n log n), exact for this 1-D case, and avoids QHull's degenerate-input
    failures on flat (e.g. deep-shadow) spectra.
    """
    X = np.asarray(X, dtype=np.float64)
    wl = np.asarray(wavelengths, dtype=np.float64)
    flat = X.reshape(-1, X.shape[-1])
    out = np.empty_like(flat)

    for i in range(flat.shape[0]):
        y = flat[i]
        # Monotone chain, keeping only right turns -> upper hull.
        hull: list[int] = []
        for j in range(y.size):
            while len(hull) >= 2:
                a, b = hull[-2], hull[-1]
                cross = (wl[b] - wl[a]) * (y[j] - y[a]) - (wl[j] - wl[a]) * (y[b] - y[a])
                if cross >= 0:          # b is on/below the line a-j: drop it
                    hull.pop()
                else:
                    break
            hull.append(j)
        cont = np.interp(wl, wl[hull], y[hull])
        out[i] = y / np.maximum(cont, 1e-8)

    return out.reshape(X.shape)


def brightness_mask(cube: np.ndarray, wavelengths: np.ndarray,
                    nir_nm: float = 850.0, min_reflectance: float = 0.04) -> np.ndarray:
    """
    Boolean mask of pixels bright enough to classify.

    Deep shadow in a closed subtropical canopy carries almost no signal; forcing
    a class onto those pixels manufactures false positives. We mask them, count
    them, and report the masked fraction as part of the deliverable — an honest
    "we could not see here" is worth more to AFCD than a confident guess.
    """
    i = int(np.argmin(np.abs(np.asarray(wavelengths) - nir_nm)))
    return cube[:, :, i] >= min_reflectance


# ==========================================================================
# The composed pipeline
# ==========================================================================
def build_feature_stack(X: np.ndarray, wavelengths: np.ndarray,
                        cfg_pre: Dict[str, Any]) -> Tuple[np.ndarray, list]:
    """
    Apply the full configured chain and return ``(features, feature_names)``.

    The output concatenates, in order, whichever of these the config enables:

    * order-0 block  — SNV (and optionally continuum-removed) reflectance
    * order-1 block  — SG first derivative, then SNV
    * order-2 block  — SG second derivative, then SNV

    SNV is applied *after* differentiation for the derivative blocks: the
    derivative already removes the additive term, and SNV then puts the three
    blocks on a common scale so no single block dominates the PCA that follows.

    ``feature_names`` are returned so that Random Forest importances can be read
    back as "the 718 nm first derivative", not "feature 147".
    """
    X = np.asarray(X, dtype=np.float64)
    wl = np.asarray(wavelengths, dtype=np.float64)
    delta = float(np.median(np.diff(wl))) if wl.size > 1 else 1.0

    win = int(cfg_pre.get("savgol", {}).get("window_length", 11))
    poly = int(cfg_pre.get("savgol", {}).get("polyorder", 3))
    orders = list(cfg_pre.get("derivative_orders", [0, 1, 2]))
    use_snv = bool(cfg_pre.get("snv", True))
    use_cr = bool(cfg_pre.get("continuum_removal", True))
    lo, hi = cfg_pre.get("clip_reflectance", [0.0, 1.2])

    Xc = np.clip(X, lo, hi)
    blocks, names = [], []

    for d in orders:
        B = savgol(Xc, window_length=win, polyorder=poly, deriv=d, delta_nm=delta)
        if d == 0 and use_cr:
            B = continuum_removal(B, wl)
            tag = "cr"
        else:
            tag = f"d{d}"
        if use_snv:
            B = snv(B)
        blocks.append(B)
        names += [f"{tag}@{w:.0f}nm" for w in wl]

    return np.concatenate(blocks, axis=-1), names
