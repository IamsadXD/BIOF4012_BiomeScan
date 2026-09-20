#!/usr/bin/env python
"""
STAGE 01 — Acquire real, open, citable data.
============================================

The proposal is explicit (§5.1) that data collection is the principal risk and
that a Hong Kong ground-truthed spectral library is the actual IP. Phase 0 has
not been flown yet, so this stage pulls every piece of *genuinely open* data
that can stand in for parts of it, and records exactly what each piece is — so
nobody later mistakes a public benchmark for our own field measurements.

Three sources, three different jobs:

1. **GBIF occurrence records (real, Hong Kong).**
   ~550 georeferenced *Mikania micrantha* records inside HK, plus records for
   the native climbers the Government guidance warns are confused with it. This
   is real spatial evidence: it drives Tier-1 candidate-zone screening (§3.3),
   informs which catchments are worth flying (§7.3), and gives the severity
   model a real ecological-context layer instead of an invented one.

   Note the taxonomy trap handled in config: querying GBIF for
   "Bauhinia glauca" returns zero Hong Kong records because the accepted name is
   *Phanera glauca*. A pipeline that silently returned an empty native-climber
   class would have produced a Mikania classifier with nothing to confuse it
   with — and a beautiful, meaningless accuracy figure.

2. **EcoSIS leaf reflectance (real, tropical broadleaf).**
   Field-spectroradiometer measurements of tropical tree leaves, 350-2500 nm at
   1 nm. These are *measured* reflectance curves from real tropical foliage, and
   they become the physical base of the endmember library in stage 02 — so our
   synthetic canopy has the absorption structure, plateau shape and realistic
   biological variance of actual leaves rather than of a hand-drawn curve.

3. **Botswana / EO-1 Hyperion (real hyperspectral imagery).**
   145-band imagery with 14 labelled vegetation classes, several of which are
   species-level riparian and woodland types. This is the honesty control: the
   classifier and the site-disjoint validation machinery get run on real
   hyperspectral data that we did not synthesise, in stage 08. If the pipeline
   only worked on our own simulation, that would be worth knowing.

Every download is written with a provenance record into
``data/raw/PROVENANCE.json``. Re-running skips files already present unless
``--force`` is given.

Usage
-----
    python scripts/01_fetch_open_data.py            # everything
    python scripts/01_fetch_open_data.py --skip-benchmark   # no 79 MB download
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import requests

from mikania.config import PATHS, load_config

UA = {"User-Agent": "MIKANIA-HSI/1.0 (AFCD Phase 0 feasibility pipeline; research use)"}
PROVENANCE: List[Dict[str, Any]] = []


def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def _record(kind: str, name: str, source: str, path: str, note: str, **extra) -> None:
    PROVENANCE.append({
        "kind": kind, "name": name, "source": source,
        "path": os.path.relpath(path, PATHS.root) if path else None,
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "note": note, **extra,
    })


# ==========================================================================
# 1. GBIF
# ==========================================================================
def fetch_gbif(cfg: Dict[str, Any], force: bool = False) -> pd.DataFrame:
    """
    Page the GBIF occurrence API for each configured taxon within Hong Kong.

    We keep only records with coordinates and drop those whose stated positional
    uncertainty exceeds 1 km — a record that could be anywhere inside a square
    kilometre of country park is not evidence about a specific catchment, and
    including it would put fictitious precision into the Tier-1 screening layer.
    """
    out_csv = os.path.join(PATHS.raw, "gbif_hk_occurrences.csv")
    if os.path.exists(out_csv) and not force:
        _log(f"cached  {os.path.basename(out_csv)}")
        return pd.read_csv(out_csv)

    g = cfg["open_data"]["gbif"]
    rows: List[Dict[str, Any]] = []

    for taxon in g["taxa"]:
        got, offset = 0, 0
        while got < g["max_records_per_taxon"]:
            params = {
                "scientificName": taxon["query"],
                "country": g["country"],
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
                "limit": g["page_size"],
                "offset": offset,
            }
            r = requests.get(g["base_url"], params=params, headers=UA, timeout=90)
            r.raise_for_status()
            js = r.json()
            batch = js.get("results", [])
            if not batch:
                break
            for rec in batch:
                unc = rec.get("coordinateUncertaintyInMeters")
                if unc is not None and unc > 1000:
                    continue
                rows.append({
                    "gbif_key": rec.get("key"),
                    "query_name": taxon["query"],
                    "class_key": taxon["class_key"],
                    "scientific_name": rec.get("scientificName"),
                    "lat": rec.get("decimalLatitude"),
                    "lon": rec.get("decimalLongitude"),
                    "uncertainty_m": unc,
                    "year": rec.get("year"),
                    "month": rec.get("month"),
                    "basis": rec.get("basisOfRecord"),
                    "dataset": rec.get("institutionCode") or rec.get("publishingOrgKey"),
                })
            got += len(batch)
            offset += g["page_size"]
            if js.get("endOfRecords"):
                break
            time.sleep(0.25)          # be a good API citizen
        _log(f"GBIF {taxon['query']:<24} -> {got:>4} records  ({taxon['note']})")

    df = pd.DataFrame(rows).dropna(subset=["lat", "lon"]).drop_duplicates("gbif_key")
    df.to_csv(out_csv, index=False)
    _record("occurrences", "GBIF Hong Kong climber occurrences",
            "https://www.gbif.org (GBIF.org occurrence search API)", out_csv,
            "Real georeferenced records; coordinate uncertainty > 1 km discarded. "
            "GBIF data are aggregated from many publishers, mostly iNaturalist for HK. "
            "Licence varies by record (CC0 / CC-BY / CC-BY-NC) — check before redistribution.",
            n_records=int(len(df)),
            taxa={t["query"]: int((df["query_name"] == t["query"]).sum()) for t in g["taxa"]})
    _log(f"GBIF total kept: {len(df)} records -> {os.path.basename(out_csv)}")
    return df


# ==========================================================================
# 2. EcoSIS
# ==========================================================================
def fetch_ecosis(cfg: Dict[str, Any], force: bool = False) -> Dict[str, str]:
    """
    Download EcoSIS packages as CSV.

    EcoSIS stores each package's spectra either as one row per spectrum
    (wavelengths as columns) or transposed, so the config carries an
    ``orientation`` flag per package and stage 02 uses it rather than guessing
    from the shape — a 2151 x 77 table is ambiguous by shape alone.
    """
    paths: Dict[str, str] = {}
    for pkg in cfg["open_data"]["ecosis"]["packages"]:
        name = pkg["name"]
        dest = os.path.join(PATHS.raw, f"ecosis_{name[:48]}.csv")
        if os.path.exists(dest) and not force and os.path.getsize(dest) > 1024:
            _log(f"cached  {os.path.basename(dest)}")
            paths[name] = dest
            continue

        # The package export endpoint serves the whole package as one CSV.
        url = f"https://ecosis.org/api/package/{name}/export"
        r = requests.get(url, params={"metadata": "true"}, headers=UA, timeout=180)
        if r.status_code != 200 or len(r.content) < 1024:
            # Fall back to the package's own attached resources.
            meta = requests.get(f"https://ecosis.org/api/package/{name}",
                                headers=UA, timeout=90).json()
            res = (meta.get("ecosis") or {}).get("resources") or []
            csvs = [x for x in res if str(x.get("url", "")).lower().endswith(".csv")]
            if not csvs:
                _log(f"SKIP    {name}: no downloadable CSV")
                continue
            r = requests.get(csvs[0]["url"], headers=UA, timeout=180)
            r.raise_for_status()

        with open(dest, "wb") as fh:
            fh.write(r.content)
        paths[name] = dest
        _log(f"EcoSIS  {name[:52]:<52} {len(r.content)/1e6:5.2f} MB")
        _record("spectra", name, f"https://ecosis.org/package/{name}", dest,
                f"{pkg['note']}. Real ASD field-spectroradiometer leaf reflectance. "
                "EcoSIS licence: 'Other (Open)'. Cite the dataset authors on reuse.",
                orientation=pkg["orientation"], bytes=len(r.content))
    return paths


# ==========================================================================
# 3. Benchmark hyperspectral imagery
# ==========================================================================
def fetch_benchmark(cfg: Dict[str, Any], force: bool = False) -> Dict[str, str]:
    """
    Download the Botswana EO-1 Hyperion scene and its ground truth.

    Served from a HuggingFace mirror because the canonical Basque-University
    host now rejects non-browser clients. ~79 MB for the cube, streamed to disk
    so we never hold it twice in memory.
    """
    out: Dict[str, str] = {}
    b = cfg["open_data"]["benchmark_hsi"]
    for f in b["files"]:
        dest = os.path.join(PATHS.raw, f["dest"])
        if os.path.exists(dest) and not force and os.path.getsize(dest) > 10_000:
            _log(f"cached  {f['dest']}")
            out[f["key"]] = dest
            continue
        _log(f"downloading {f['dest']} ...")
        with requests.get(f["url"], headers=UA, timeout=900, stream=True) as r:
            r.raise_for_status()
            total = 0
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    total += len(chunk)
        out[f["key"]] = dest
        _log(f"        {f['dest']}  {total/1e6:.1f} MB")
        _record("imagery", f"{b['name']} / {f['key']}", f["url"], dest,
                f"{b['sensor']}. Public research benchmark, widely redistributed; "
                "used here only to validate the classifier and the site-disjoint "
                "cross-validation machinery on real (non-simulated) hyperspectral data.",
                bytes=total)
    return out


# ==========================================================================
# Site join — turn occurrence points into a per-site ecological context layer
# ==========================================================================
def summarise_sites(cfg: Dict[str, Any], gbif: pd.DataFrame) -> Dict[str, Any]:
    """
    For each configured catchment, count nearby real occurrence records.

    This is a genuine Tier-1 product in miniature (§3.3): existing open records
    flag which catchments deserve expensive Tier-2 flying. The radius is 3 km,
    a defensible catchment-scale neighbourhood at Hong Kong's terrain scale.
    """
    R_KM = 3.0
    summary = {}
    for site in cfg["sites"]:
        lat0, lon0 = site["centroid"]
        dlat = (gbif["lat"] - lat0) * 111.32
        dlon = (gbif["lon"] - lon0) * 111.32 * np.cos(np.radians(lat0))
        d = np.sqrt(dlat ** 2 + dlon ** 2)
        near = gbif[d <= R_KM]
        summary[site["key"]] = {
            "name": site["name"],
            "centroid": site["centroid"],
            "radius_km": R_KM,
            "n_records_total": int(len(near)),
            "n_mikania": int((near["class_key"] == "mikania").sum()),
            "n_native_climbers": int((near["class_key"] != "mikania").sum()),
            "nearest_mikania_km": (
                float(d[gbif["class_key"] == "mikania"].min())
                if (gbif["class_key"] == "mikania").any() else None
            ),
        }
    return summary


# ==========================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    ap.add_argument("--skip-benchmark", action="store_true",
                    help="skip the ~79 MB Botswana download")
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()

    print("\nSTAGE 01 — fetching open data")
    print("=" * 68)

    print("\n[1/3] GBIF occurrence records (real, Hong Kong)")
    gbif = fetch_gbif(cfg, args.force)

    print("\n[2/3] EcoSIS leaf reflectance (real, tropical broadleaf)")
    fetch_ecosis(cfg, args.force)

    print("\n[3/3] Benchmark hyperspectral imagery (real, EO-1 Hyperion)")
    if args.skip_benchmark:
        _log("skipped by request")
    else:
        fetch_benchmark(cfg, args.force)

    # Per-site occurrence context -> consumed by severity scoring in stage 06.
    sites = summarise_sites(cfg, gbif)
    ctx = os.path.join(PATHS.interim, "site_occurrence_context.json")
    os.makedirs(PATHS.interim, exist_ok=True)
    with open(ctx, "w", encoding="utf-8") as fh:
        json.dump(sites, fh, indent=2)

    print("\nPer-site real occurrence context (3 km radius):")
    for k, v in sites.items():
        print(f"  {v['name']:<32} Mikania {v['n_mikania']:>3}   native climbers {v['n_native_climbers']:>3}")

    prov = os.path.join(PATHS.raw, "PROVENANCE.json")
    existing = []
    if os.path.exists(prov):
        with open(prov, encoding="utf-8") as fh:
            existing = json.load(fh)
    seen = {(p["kind"], p["name"]) for p in PROVENANCE}
    merged = PROVENANCE + [p for p in existing if (p["kind"], p["name"]) not in seen]
    with open(prov, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)

    print(f"\nProvenance written: {os.path.relpath(prov, PATHS.root)} ({len(merged)} entries)")
    print("STAGE 01 complete.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
