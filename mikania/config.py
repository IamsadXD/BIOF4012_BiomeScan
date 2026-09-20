"""
Configuration loading and derived constants.

Everything the pipeline needs to know that is not data lives in
``config/default.yaml``. This module reads it once, validates the parts that
other modules depend on, and exposes a handful of derived quantities (the
wavelength grid, class lookup tables, project paths) so that no other module
ever has to recompute them — or, worse, hard-code them.

Usage
-----
>>> from mikania.config import load_config, wavelengths, PATHS
>>> cfg = load_config()
>>> wl = wavelengths(cfg)          # (121,) float64, 400..1000 nm at 5 nm
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List

import numpy as np
import yaml

# --------------------------------------------------------------------------
# Project paths. Resolved relative to this file so that scripts work no matter
# what the caller's working directory is.
# --------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)


@dataclass(frozen=True)
class _Paths:
    root: str = ROOT
    config: str = os.path.join(ROOT, "config")
    data: str = os.path.join(ROOT, "data")
    raw: str = os.path.join(ROOT, "data", "raw")
    interim: str = os.path.join(ROOT, "data", "interim")
    processed: str = os.path.join(ROOT, "data", "processed")
    outputs: str = os.path.join(ROOT, "outputs")
    figures: str = os.path.join(ROOT, "outputs", "figures")
    models: str = os.path.join(ROOT, "outputs", "models")
    reports: str = os.path.join(ROOT, "outputs", "reports")
    platform_data: str = os.path.join(ROOT, "platform", "ui", "data")

    def ensure(self) -> "_Paths":
        """Create every directory in the tree. Idempotent."""
        for name in (
            "data", "raw", "interim", "processed", "outputs",
            "figures", "models", "reports", "platform_data",
        ):
            os.makedirs(getattr(self, name), exist_ok=True)
        return self


PATHS = _Paths()


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> Dict[str, Any]:
    """
    Read and validate the YAML configuration.

    Cached, because it is read from a dozen call sites and the file never
    changes inside a single run. Pass an explicit ``path`` to override (used by
    the tests and by anyone running a sensitivity analysis on a modified copy).
    """
    path = path or os.path.join(PATHS.config, "default.yaml")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    _validate(cfg)
    return cfg


def _validate(cfg: Dict[str, Any]) -> None:
    """
    Fail loudly and early on the handful of invariants that, if broken, would
    produce silently wrong science rather than an exception.
    """
    required = ["project", "sensor", "classes", "species_spectra", "sites",
                "preprocess", "models", "validation", "severity"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"config is missing required sections: {missing}")

    s = cfg["sensor"]
    if s["wavelength_end_nm"] <= s["wavelength_start_nm"]:
        raise ValueError("sensor wavelength range is inverted")

    # Class ids must be dense and start at 0 (unlabelled), because we index
    # colour tables and confusion matrices positionally.
    ids = [c["id"] for c in cfg["classes"]]
    if ids != list(range(len(ids))):
        raise ValueError(f"class ids must be dense 0..N-1, got {ids}")

    # Severity weights must sum to 1 or the score is not on [0, 1] and the
    # action bands become meaningless.
    wsum = sum(cfg["severity"]["weights"].values())
    if abs(wsum - 1.0) > 1e-6:
        raise ValueError(f"severity weights must sum to 1.0, got {wsum:.6f}")

    # Every species named in the class scheme (other than the non-vegetation
    # classes, which are handled analytically) needs a spectral model.
    modelled = set(cfg["species_spectra"])
    needed = {c["key"] for c in cfg["classes"]
              if c["group"] in ("target", "native_climber", "canopy", "other_veg")}
    if not needed.issubset(modelled):
        raise ValueError(f"species_spectra missing entries for {sorted(needed - modelled)}")

    # At least one site must be held out, or the headline accuracy is not an
    # out-of-sample number and §5.1(6) of the proposal is violated.
    if not any(st["role"] == "holdout" for st in cfg["sites"]):
        raise ValueError("at least one site must have role: holdout")


# --------------------------------------------------------------------------
# Derived quantities
# --------------------------------------------------------------------------
def wavelengths(cfg: Dict[str, Any] | None = None) -> np.ndarray:
    """
    The sensor's band-centre wavelength grid, in nanometres.

    400-1000 nm at 5 nm spacing gives 121 bands. The proposal's reference paper
    (Huang et al. 2021) worked over 450-998 nm; this grid is a superset, so the
    published feature set is reproducible on our data.
    """
    cfg = cfg or load_config()
    s = cfg["sensor"]
    n = int(round((s["wavelength_end_nm"] - s["wavelength_start_nm"]) / s["band_spacing_nm"])) + 1
    return np.linspace(s["wavelength_start_nm"], s["wavelength_end_nm"], n)


def n_bands(cfg: Dict[str, Any] | None = None) -> int:
    return int(wavelengths(cfg).size)


def class_table(cfg: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    return (cfg or load_config())["classes"]


def class_ids(cfg=None) -> Dict[str, int]:
    """key -> id, e.g. ``{'mikania': 1, ...}``"""
    return {c["key"]: c["id"] for c in class_table(cfg)}


def class_keys(cfg=None) -> Dict[int, str]:
    """id -> key"""
    return {c["id"]: c["key"] for c in class_table(cfg)}


def class_labels(cfg=None) -> Dict[int, str]:
    """id -> human-readable label, for figures and the UI"""
    return {c["id"]: c["label"] for c in class_table(cfg)}


def class_colors(cfg=None) -> Dict[int, str]:
    """id -> hex colour. One palette shared by matplotlib figures and the web UI."""
    return {c["id"]: c["color"] for c in class_table(cfg)}


def class_groups(cfg=None) -> Dict[int, str]:
    """id -> group ('target', 'native_climber', 'canopy', ...)"""
    return {c["id"]: c["group"] for c in class_table(cfg)}


def color_lut(cfg=None) -> np.ndarray:
    """
    (n_classes, 3) uint8 lookup table for rendering class maps as RGB.
    Built from the same hex strings the UI uses, so a figure in the report and a
    layer in the browser can never disagree about what colour Mikania is.
    """
    tab = class_table(cfg)
    lut = np.zeros((len(tab), 3), dtype=np.uint8)
    for c in tab:
        h = c["color"].lstrip("#")
        lut[c["id"]] = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return lut


def site_table(cfg=None) -> List[Dict[str, Any]]:
    return (cfg or load_config())["sites"]


def sites_by_role(role: str, cfg=None) -> List[Dict[str, Any]]:
    return [s for s in site_table(cfg) if s["role"] == role]


def confusable_ids(cfg=None) -> Dict[str, Any]:
    """
    Resolve the target/native-climber pair into class ids.

    This is the sub-problem the kill criterion is defined on: everything else in
    the scene is easy, and averaging it in would hide the number that matters.
    """
    cfg = cfg or load_config()
    ids = class_ids(cfg)
    cp = cfg["confusable_pair"]
    return {
        "target_id": ids[cp["target"]],
        "native_ids": [ids[k] for k in cp["natives"]],
    }


def rng(cfg=None, offset: int = 0) -> np.random.Generator:
    """
    The project's random number generator.

    Every stochastic step draws from a generator seeded off the single project
    seed plus a per-stage ``offset``, so stages are independently reproducible
    but the whole run is deterministic end to end.
    """
    cfg = cfg or load_config()
    return np.random.default_rng(cfg["project"]["random_seed"] + offset)
