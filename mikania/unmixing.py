"""
Linear spectral unmixing — the two-layer canopy problem.

Proposal §3.2 makes a structural argument that is easy to skim past but is the
mathematical heart of the sensor choice:

    "Mikania forms a *blanket over* the host canopy rather than being part of
     it. This creates a two-layer mixed-pixel structure well suited to spectral
     unmixing, which needs bands >= endmembers — another reason a 5-band
     multispectral sensor is mathematically inadequate here."

That is a hard constraint, not a preference. With 5 endmembers (Mikania, host
canopy, shrub/grass, soil, shadow) a 5-band sensor gives a square system with no
residual degrees of freedom: any spectrum fits perfectly, the fit is
unfalsifiable, and abundances are meaningless. With 121 bands the system is
overdetermined 24-fold, the residual is informative, and the abundance estimate
carries an uncertainty you can quote.

Why abundance and not just a class label
----------------------------------------
The severity product (§3.1 deliverable 2) is scored on *canopy coverage
fraction* — how much of the host canopy the blanket covers. A hard class label
answers "is there Mikania in this pixel"; the abundance answers "how much", which
is what determines ecological damage and therefore treatment priority. Light
infestation and full blanket are different work orders.

Methods
-------
``ucls``  unconstrained least squares — fast, can go negative, diagnostic only
``nnls``  non-negative least squares — physically valid, does not sum to one
``fcls``  fully constrained (non-negative AND sum-to-one) — the operational one
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import nnls


def _stack_endmembers(library: Dict[str, np.ndarray], keys: Sequence[str]) -> np.ndarray:
    """(n_bands, n_endmembers) matrix in the requested key order."""
    missing = [k for k in keys if k not in library]
    if missing:
        raise KeyError(f"endmember library is missing {missing}; have {sorted(library)}")
    return np.column_stack([np.asarray(library[k], dtype=np.float64) for k in keys])


def unmix(X: np.ndarray,
          library: Dict[str, np.ndarray],
          endmember_keys: Sequence[str],
          method: str = "fcls",
          sum_to_one_weight: float = 30.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Estimate per-pixel endmember abundances.

    Parameters
    ----------
    X : (n_pixels, n_bands) reflectance
    library : key -> (n_bands,) endmember reflectance
    endmember_keys : which endmembers, in output column order
    method : 'ucls' | 'nnls' | 'fcls'
    sum_to_one_weight
        FCLS is implemented the standard way: append a row of ``w`` to the
        endmember matrix and a ``w`` to the observation, then solve NNLS. As
        ``w`` grows the sum-to-one constraint is enforced ever more strictly.
        w=30 with reflectance on [0,1] makes the constraint dominate the fit
        without making the system numerically ill-conditioned.

    Returns
    -------
    A : (n_pixels, n_endmembers) abundances
    rmse : (n_pixels,) reconstruction RMSE — the honesty channel

    On ``rmse``
    -----------
    A high residual means the pixel is not well explained by *any* mixture of
    the library, i.e. it contains something we have no endmember for. Those
    pixels must be flagged, not silently assigned. Reporting the residual is how
    you avoid the classic unmixing failure of confidently decomposing a scene
    into endmembers that were never in it.
    """
    X = np.asarray(X, dtype=np.float64)
    E = _stack_endmembers(library, endmember_keys)          # (bands, p)
    n, p = X.shape[0], E.shape[1]

    if method == "ucls":
        A = np.linalg.lstsq(E, X.T, rcond=None)[0].T

    elif method in ("nnls", "fcls"):
        if method == "fcls":
            w = float(sum_to_one_weight)
            E_aug = np.vstack([E, w * np.ones((1, p))])
            X_aug = np.hstack([X, w * np.ones((n, 1))])
        else:
            E_aug, X_aug = E, X
        A = np.empty((n, p), dtype=np.float64)
        for i in range(n):
            A[i], _ = nnls(E_aug, X_aug[i])
    else:
        raise ValueError(f"unknown unmixing method {method!r}")

    resid = X - A @ E.T
    rmse = np.sqrt((resid ** 2).mean(axis=1))
    return A, rmse


def unmix_cube(cube: np.ndarray,
               library: Dict[str, np.ndarray],
               endmember_keys: Sequence[str],
               method: str = "fcls",
               sum_to_one_weight: float = 30.0,
               mask: Optional[np.ndarray] = None,
               stride: int = 1) -> Tuple[np.ndarray, np.ndarray]:
    """
    Cube-shaped wrapper around :func:`unmix`.

    ``mask`` (lines, samples) restricts the solve to valid pixels — masked
    pixels come back as NaN rather than as a fabricated zero abundance, so a
    downstream mean over the scene cannot quietly include unseen ground.

    ``stride`` subsamples for speed during exploration; the operational run uses
    stride=1. FCLS is a per-pixel constrained solve, so cost is linear in pixel
    count and a full 8 cm production scene would be tiled, not solved whole.
    """
    h, w, b = cube.shape
    flat = cube.reshape(h * w, b)
    valid = np.ones(h * w, dtype=bool) if mask is None else mask.reshape(-1).astype(bool)
    if stride > 1:
        sel = np.zeros(h * w, dtype=bool)
        sel.reshape(h, w)[::stride, ::stride] = True
        valid &= sel

    p = len(endmember_keys)
    A = np.full((h * w, p), np.nan, dtype=np.float32)
    R = np.full(h * w, np.nan, dtype=np.float32)
    if valid.any():
        a, r = unmix(flat[valid], library, endmember_keys, method, sum_to_one_weight)
        A[valid] = a.astype(np.float32)
        R[valid] = r.astype(np.float32)
    return A.reshape(h, w, p), R.reshape(h, w)


def coverage_fraction(abundance: np.ndarray,
                      endmember_keys: Sequence[str],
                      target_key: str = "mikania",
                      shadow_key: str = "shadow",
                      min_report: float = 0.10) -> np.ndarray:
    """
    Convert raw abundances into the *canopy coverage fraction* that severity
    scoring consumes.

    Two adjustments matter:

    1. **Renormalise out shadow.** Shadow is not ground cover; it is missing
       information. A pixel that is 40% shadow, 40% Mikania and 20% canopy has
       67% Mikania coverage *of the surface we can actually see*, and reporting
       40% would systematically understate infestation on shaded slopes.
    2. **Floor small abundances to zero.** Below ~10% the abundance is within
       the noise of the unmixing residual. Reporting it as real infestation
       manufactures work orders, which is the fastest way to lose a government
       client's trust.
    """
    keys = list(endmember_keys)
    a = np.asarray(abundance, dtype=np.float64)
    ti = keys.index(target_key)
    if shadow_key in keys:
        si = keys.index(shadow_key)
        visible = 1.0 - np.clip(a[..., si], 0.0, 0.95)
    else:
        visible = np.ones(a.shape[:-1])
    frac = a[..., ti] / np.maximum(visible, 0.05)
    frac = np.clip(frac, 0.0, 1.0)
    return np.where(frac >= min_report, frac, 0.0)


def endmember_condition_report(library: Dict[str, np.ndarray],
                               endmember_keys: Sequence[str]) -> Dict[str, object]:
    """
    Diagnose whether the endmember set is actually solvable — and quantify the
    band-count argument from §3.2 for the deck.

    Returns the condition number of the endmember matrix at full spectral
    resolution and at a simulated 5-band multispectral resolution. A condition
    number in the thousands means small measurement noise produces large
    abundance error; that is the multispectral case, and it is a number you can
    put on a slide.
    """
    E = _stack_endmembers(library, endmember_keys)
    cond_full = float(np.linalg.cond(E))

    # Five typical multispectral bands (blue, green, red, red-edge, NIR) as
    # index positions into a 121-band 400-1000 nm grid at 5 nm.
    nb = E.shape[0]
    grid = np.linspace(400.0, 1000.0, nb)
    ms_nm = [475.0, 560.0, 668.0, 717.0, 842.0]
    idx = [int(np.argmin(np.abs(grid - m))) for m in ms_nm]
    E_ms = E[idx, :]
    cond_ms = float(np.linalg.cond(E_ms)) if E_ms.shape[0] >= E_ms.shape[1] else float("inf")

    return {
        "n_endmembers": int(E.shape[1]),
        "n_bands_hyperspectral": int(E.shape[0]),
        "n_bands_multispectral": len(ms_nm),
        "condition_hyperspectral": cond_full,
        "condition_multispectral": cond_ms,
        "multispectral_overdetermined": bool(len(ms_nm) > E.shape[1]),
        "note": (
            "With 5 bands and 5 endmembers the system is square: it fits any "
            "spectrum exactly, leaves no residual to test the fit against, and "
            "the abundance estimate is therefore unfalsifiable. 121 bands leave "
            f"{E.shape[0] - E.shape[1]} residual degrees of freedom."
        ),
    }
