"""
Hyperspectral I/O.

Three formats matter operationally:

``.npz``    Internal working format. Fast, self-describing, holds the cube plus
            wavelengths plus ground truth plus per-scene metadata in one file.
``ENVI``    What every pushbroom vendor actually writes (``.hdr`` + flat binary).
            Reading it is non-negotiable for ingesting real flight data; writing
            it means our simulated scenes can be opened in ENVI/QGIS/SPy and
            inspected by a sceptical evaluator.
``GeoTIFF`` What AFCD receives. Class maps, severity rasters and abundance
            fractions all leave the pipeline as georeferenced single- or
            multi-band GeoTIFFs that drop straight into their GIS.

Georeferencing note
-------------------
The simulated scenes are placed at real Hong Kong catchment centroids in
EPSG:4326 with a metre-derived pixel size converted to degrees. That is a local
tangent-plane approximation, correct to well under a pixel over a 500 m scene
and completely adequate for a demonstration deliverable. Production data would
carry the flight's own RTK-derived orthorectification grid instead.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np

# Earth radius used for the local metres -> degrees conversion (WGS84 mean).
_EARTH_R_M = 6_371_008.8


# ==========================================================================
# Internal npz format
# ==========================================================================
def save_cube_npz(
    path: str,
    cube: np.ndarray,
    wavelengths: np.ndarray,
    gt: Optional[np.ndarray] = None,
    meta: Optional[Dict[str, Any]] = None,
    **extra: np.ndarray,
) -> str:
    """
    Persist a cube and everything needed to interpret it.

    Parameters
    ----------
    cube : (lines, samples, bands) float32 reflectance, 0..~1.2
    wavelengths : (bands,) float64, nanometres
    gt : (lines, samples) uint8 class ids, 0 = unlabelled
    meta : JSON-serialisable dict — site key, season, GSD, CRS, transform, ...
    **extra : any further same-shaped rasters (e.g. true abundance fractions
              from the simulator, which the classifier must never see)
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload: Dict[str, Any] = {
        "cube": np.asarray(cube, dtype=np.float32),
        "wavelengths": np.asarray(wavelengths, dtype=np.float64),
        "meta_json": np.array(json.dumps(meta or {})),
    }
    if gt is not None:
        payload["gt"] = np.asarray(gt, dtype=np.uint8)
    for k, v in extra.items():
        payload[k] = np.asarray(v)
    np.savez_compressed(path, **payload)
    return path


def load_cube_npz(path: str) -> Dict[str, Any]:
    """Inverse of :func:`save_cube_npz`. Returns a plain dict."""
    z = np.load(path, allow_pickle=False)
    out: Dict[str, Any] = {k: z[k] for k in z.files if k != "meta_json"}
    out["meta"] = json.loads(str(z["meta_json"])) if "meta_json" in z.files else {}
    return out


# ==========================================================================
# ENVI
# ==========================================================================
def write_envi(path_hdr: str, cube: np.ndarray, wavelengths: np.ndarray,
               description: str = "", interleave: str = "bil") -> str:
    """
    Write an ENVI header + raw binary pair.

    BIL interleave is the pushbroom-native layout (one line of all bands at a
    time), so writing BIL keeps the simulated data byte-order-compatible with
    what a real sensor streams to disk.

    Falls back to a hand-written header if the optional ``spectral`` package is
    absent — the format is simple enough that a dependency should not be able to
    block delivery.
    """
    cube = np.asarray(cube, dtype=np.float32)
    lines, samples, bands = cube.shape
    base = path_hdr[:-4] if path_hdr.endswith(".hdr") else path_hdr
    os.makedirs(os.path.dirname(os.path.abspath(base)), exist_ok=True)

    try:
        import spectral.io.envi as envi  # noqa: WPS433 (optional dependency)
        md = {
            "description": description,
            "wavelength units": "nm",
            "wavelength": [f"{w:.3f}" for w in np.asarray(wavelengths)],
            "data type": 4,           # 32-bit float
            "interleave": interleave,
            "byte order": 0,
        }
        img = envi.create_image(base + ".hdr", metadata=md, shape=cube.shape,
                                dtype=np.float32, force=True, interleave=interleave)
        mm = img.open_memmap(writable=True)
        mm[:] = cube
        del mm
        return base + ".hdr"
    except Exception:                                   # pragma: no cover
        pass

    # Minimal, spec-correct fallback.
    order = {"bsq": (2, 0, 1), "bil": (0, 2, 1), "bip": (0, 1, 2)}[interleave]
    cube.transpose(order).astype("<f4").tofile(base + ".img")
    wl = ", ".join(f"{w:.3f}" for w in np.asarray(wavelengths))
    with open(base + ".hdr", "w", encoding="utf-8") as fh:
        fh.write(
            "ENVI\n"
            f"description = {{{description}}}\n"
            f"samples = {samples}\nlines = {lines}\nbands = {bands}\n"
            "header offset = 0\nfile type = ENVI Standard\ndata type = 4\n"
            f"interleave = {interleave}\nbyte order = 0\n"
            "wavelength units = nm\n"
            f"wavelength = {{{wl}}}\n"
        )
    return base + ".hdr"


def read_envi(path_hdr: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Read an ENVI cube. Returns ``(cube[lines, samples, bands], wavelengths_nm)``.

    This is the entry point real flight data would use. ``spectral`` is required
    here (unlike writing) because parsing every legal ENVI header variant by hand
    is not a good use of anyone's time.
    """
    import spectral.io.envi as envi

    img = envi.open(path_hdr)
    cube = np.asarray(img.load(), dtype=np.float32)
    wl = img.bands.centers
    if wl is None:
        raise ValueError(f"{path_hdr} has no wavelength metadata; cannot interpret bands")
    return cube, np.asarray(wl, dtype=np.float64)


# ==========================================================================
# Georeferencing
# ==========================================================================
def geotransform_for_site(centroid_latlon: Tuple[float, float],
                          shape: Tuple[int, int],
                          gsd_m: float) -> Dict[str, Any]:
    """
    Build an EPSG:4326 affine transform placing a ``shape`` raster of ``gsd_m``
    pixels centred on ``centroid_latlon``.

    Degrees-per-metre in longitude shrinks with latitude by cos(lat); at Hong
    Kong's ~22.4 deg N that factor is ~0.924 and ignoring it would skew the
    scene by 8% in x. Cheap to get right, embarrassing to get wrong.
    """
    lat, lon = centroid_latlon
    lines, samples = shape
    deg_per_m_lat = 360.0 / (2.0 * np.pi * _EARTH_R_M)
    deg_per_m_lon = deg_per_m_lat / max(np.cos(np.radians(lat)), 1e-6)
    px_lon = gsd_m * deg_per_m_lon
    px_lat = gsd_m * deg_per_m_lat
    west = lon - 0.5 * samples * px_lon
    north = lat + 0.5 * lines * px_lat
    return {
        "crs": "EPSG:4326",
        # rasterio/GDAL order: (a, b, c, d, e, f) = (px_w, rot, west, rot, -px_h, north)
        "transform": [px_lon, 0.0, west, 0.0, -px_lat, north],
        "bounds": [west, north - lines * px_lat, west + samples * px_lon, north],
        "gsd_m": gsd_m,
    }


def write_geotiff(path: str, array: np.ndarray, geo: Dict[str, Any],
                  nodata: Optional[float] = None,
                  band_descriptions: Optional[list] = None) -> str:
    """
    Write a single- or multi-band GeoTIFF — the AFCD-facing deliverable format.

    ``array`` may be (H, W) or (H, W, B). Dtype is preserved: class maps stay
    uint8 so QGIS renders them as a categorical raster with our palette, while
    severity and abundance stay float32.
    """
    import rasterio
    from rasterio.transform import Affine

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    arr = np.asarray(array)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    h, w, b = arr.shape
    t = geo["transform"]
    profile = {
        "driver": "GTiff", "height": h, "width": w, "count": b,
        "dtype": arr.dtype.name, "crs": geo["crs"],
        "transform": Affine(t[0], t[1], t[2], t[3], t[4], t[5]),
        "compress": "deflate", "predictor": 2, "tiled": True,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        for i in range(b):
            dst.write(arr[:, :, i], i + 1)
            if band_descriptions and i < len(band_descriptions):
                dst.set_band_description(i + 1, band_descriptions[i])
    return path


# ==========================================================================
# Convenience
# ==========================================================================
def band_index(wavelengths: np.ndarray, target_nm: float) -> int:
    """Index of the band whose centre is nearest ``target_nm``."""
    return int(np.argmin(np.abs(np.asarray(wavelengths) - float(target_nm))))


def rgb_composite(cube: np.ndarray, wavelengths: np.ndarray,
                  rgb_nm: Tuple[float, float, float] = (660.0, 550.0, 470.0),
                  percentile: Tuple[float, float] = (2.0, 98.0)) -> np.ndarray:
    """
    True-colour quicklook from three VNIR bands, percentile-stretched.

    Used for the browser layer stack and for figure panels. Stretch percentiles
    are computed per band over the whole scene, which is the honest choice for a
    quicklook: it shows what the sensor saw, not a per-tile-optimised render that
    would make patchy illumination look uniform.
    """
    idx = [band_index(wavelengths, w) for w in rgb_nm]
    out = np.zeros(cube.shape[:2] + (3,), dtype=np.float32)
    for k, i in enumerate(idx):
        b = cube[:, :, i].astype(np.float32)
        lo, hi = np.percentile(b, percentile)
        out[:, :, k] = np.clip((b - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return out


def save_png(path: str, rgb01: np.ndarray) -> str:
    """Write a float 0..1 RGB (or 2-D grey) array as an 8-bit PNG."""
    from PIL import Image

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    a = np.asarray(rgb01)
    if a.dtype != np.uint8:
        a = (np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(a).save(path, optimize=True)
    return path
