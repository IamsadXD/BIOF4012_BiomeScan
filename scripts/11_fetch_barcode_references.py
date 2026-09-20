#!/usr/bin/env python
"""
STAGE 11 — Acquire real barcode reference sequences (NCBI, BOLD).
=================================================================

Proposal §3.4 identifies the specimen and §4.2 identifies the problem:

    "Reference coverage in BOLD and GenBank is uneven by taxon and geography,
     which is a live project risk rather than a solved problem — see Risk 9."

and Appendix B.9 states the assumption this stage exists to test:

    "**Barcode reference coverage is assumed adequate** for *M. micrantha*,
     *Bauhinia glauca*, *Byttneria aspera* and the dominant host canopy species
     in BOLD/GenBank. Unverified, and known to be uneven across taxa and
     regions."

That assumption is checkable today, for free, and this stage checks it. Every
sequence downloaded here is real, public and citable; the coverage gaps it finds
are real gaps, not modelled ones. Where a taxon/locus cell is empty, the
consequence propagates all the way to whether a voucher can be certified at all
(§13.5 requires two loci to agree), so the coverage matrix is not a curiosity —
it is a direct constraint on the product.

Sources
-------
**NCBI Entrez** (primary). Free, no API key needed at this volume, documented
rate limit of 3 requests/second which §13.8 respects.

**BOLD Systems** (secondary, optional). The barcoding-specific database; its
public combined endpoint is queried where reachable. The pipeline must not fail
if BOLD is down or has changed its API — it is additive evidence, not a
dependency, and a build that breaks because a third party redesigned a URL is a
build nobody can reproduce in two years.

Outputs
-------
* ``data/raw/barcode_refs/<locus>.fasta`` — the sequences
* ``data/raw/barcode_refs/coverage.json`` — the taxon x locus matrix
* ``outputs/reports/barcode_reference_coverage.json`` — the Risk-10 assessment
* ``outputs/figures/fig11_reference_coverage.png``

Usage
-----
    python scripts/11_fetch_barcode_references.py            # cached if present
    python scripts/11_fetch_barcode_references.py --force    # re-download
    python scripts/11_fetch_barcode_references.py --offline  # audit the cache only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests

from mikania.barcode import SeqRecord, clean_sequence, read_fasta, write_fasta
from mikania.config import PATHS, load_config

UA = {"User-Agent": "MIKANIA-HSI/2.0 (AFCD Phase 0 feasibility pipeline; research use)"}
REF_DIR = os.path.join(PATHS.raw, "barcode_refs")

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": False, "figure.facecolor": "white",
})

# Sanity bounds on a downloaded record. A 40 kb hit for "matK" is a whole plastid
# genome, which is a legitimate GenBank record and a useless barcode reference:
# aligning a 700 bp query against it would waste a second per comparison and
# invite spurious partial matches elsewhere in the genome.
MIN_LEN_BP = 150
MAX_LEN_BP = 4000


def _log(msg: str) -> None:
    print(f"  {msg}", flush=True)


# ==========================================================================
# NCBI
# ==========================================================================
def _esearch_ids(term: str, cfg_n: Dict[str, Any], retmax: int,
                 attempts: int = 3) -> List[str]:
    """
    esearch, tolerating the ways a public API misbehaves.

    NCBI intermittently returns JSON containing raw control characters, which
    ``json.loads`` rejects outright. Observed in practice on this exact query
    set. Three defences, in order: parse non-strictly, retry with backoff, and
    fall back to scraping ``<Id>`` elements from the XML response. A reference
    build that dies because a third party emitted a stray byte is a build nobody
    can reproduce in two years.
    """
    params = {"db": "nuccore", "term": term, "retmax": retmax,
              "email": cfg_n.get("email"), "tool": "mikania-hsi"}
    last: Exception | None = None

    for attempt in range(attempts):
        try:
            r = requests.get(cfg_n["esearch_url"], headers=UA, timeout=60,
                             params={**params, "retmode": "json"})
            r.raise_for_status()
            js = json.loads(r.text, strict=False)      # strict=False allows raw control chars
            return list(js.get("esearchresult", {}).get("idlist", []))
        except Exception as e:                          # noqa: BLE001
            last = e
            time.sleep(float(cfg_n["request_interval_s"]) * (2 ** attempt))

    try:
        r = requests.get(cfg_n["esearch_url"], headers=UA, timeout=60, params=params)
        r.raise_for_status()
        return re.findall(r"<Id>(\d+)</Id>", r.text)
    except Exception:                                   # noqa: BLE001
        _log(f"esearch failed for {term!r} ({type(last).__name__}) — treating as zero hits")
        return []


def ncbi_fetch(taxon: str, locus_key: str, locus_query: str, cfg_n: Dict[str, Any],
               retmax: int) -> List[SeqRecord]:
    """esearch then efetch, one taxon/locus pair. Returns cleaned records."""
    term = f'"{taxon}"[Organism] AND {locus_query}'
    ids = _esearch_ids(term, cfg_n, retmax)
    time.sleep(float(cfg_n["request_interval_s"]))
    if not ids:
        return []

    r = requests.get(cfg_n["efetch_url"], headers=UA, timeout=120, params={
        "db": "nuccore", "id": ",".join(ids), "rettype": "fasta", "retmode": "text",
        "email": cfg_n.get("email"), "tool": "mikania-hsi"})
    r.raise_for_status()
    time.sleep(float(cfg_n["request_interval_s"]))

    out, hdr, buf = [], None, []

    def _flush():
        if hdr is None:
            return
        seq = clean_sequence("".join(buf))
        if MIN_LEN_BP <= len(seq) <= MAX_LEN_BP:
            out.append(SeqRecord(id=hdr.split()[0], seq=seq, locus=locus_key,
                                 accession=hdr.split()[0], source="ncbi",
                                 description=hdr.strip()))

    for line in r.text.splitlines():
        if line.startswith(">"):
            _flush()
            hdr, buf = line[1:], []
        elif hdr is not None:
            buf.append(line)
    _flush()
    return out


# ==========================================================================
# BOLD  (optional, must never break the run)
# ==========================================================================
def bold_fetch(taxon: str, locus_key: str, cfg_b: Dict[str, Any]) -> List[SeqRecord]:
    try:
        r = requests.get(cfg_b["combined_url"], headers=UA,
                         timeout=float(cfg_b["timeout_s"]),
                         params={"taxon": taxon, "format": "tsv"})
        if r.status_code != 200 or not r.text.strip():
            return []
        lines = r.text.splitlines()
        if len(lines) < 2:
            return []
        head = lines[0].split("\t")
        col = {c: i for i, c in enumerate(head)}
        need = ("processid", "markercode", "nucleotides")
        if not all(k in col for k in need):
            return []
        out = []
        for line in lines[1:]:
            f = line.split("\t")
            if len(f) < len(head):
                continue
            marker = f[col["markercode"]].strip()
            if locus_key.lower().replace("-", "") not in marker.lower().replace("-", ""):
                continue
            seq = clean_sequence(f[col["nucleotides"]])
            if MIN_LEN_BP <= len(seq) <= MAX_LEN_BP:
                out.append(SeqRecord(id=f"BOLD:{f[col['processid']]}", seq=seq,
                                     locus=locus_key, source="bold",
                                     accession=f[col["processid"]],
                                     description=f"BOLD {marker}"))
        return out
    except Exception as e:                                     # noqa: BLE001
        _log(f"BOLD unavailable for {taxon}/{locus_key} ({type(e).__name__}) — "
             f"continuing on NCBI alone")
        return []


# ==========================================================================
# Main
# ==========================================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    ap.add_argument("--offline", action="store_true", help="audit the cache, fetch nothing")
    ap.add_argument("--no-bold", action="store_true", help="skip the BOLD secondary source")
    args = ap.parse_args()

    cfg = load_config()
    PATHS.ensure()
    os.makedirs(REF_DIR, exist_ok=True)

    mol = cfg["molecular"]
    loci = mol["loci"]
    refs_cfg = mol["references"]
    taxa = refs_cfg["taxa"]

    print("\nSTAGE 11 — barcode reference acquisition (real open data)")
    print("=" * 78)

    # Synonym grouping. Doing this before anything else because it is the trap
    # that would otherwise be discovered as a nonsensical barcode-gap result five
    # stages later (see config §13.8 `accepted_name`).
    accepted = {t["name"]: t.get("accepted_name", t["name"]) for t in taxa}
    synonyms = {n: a for n, a in accepted.items() if n != a}
    if synonyms:
        for n, a in synonyms.items():
            _log(f"synonym  {n!r} -> accepted name {a!r}; records merged, not "
                 f"treated as a separate species")

    all_records: Dict[str, List[SeqRecord]] = {L["key"]: [] for L in loci}
    fetched_any = False

    for L in loci:
        lk, lq = L["key"], L["ncbi_query"]
        cache = os.path.join(REF_DIR, f"{lk}.fasta")

        if os.path.exists(cache) and not args.force:
            recs = read_fasta(cache)
            for r in recs:
                r.locus = lk            # trust the file we are reading, not the defline
            all_records[lk] = recs
            _log(f"cached   {lk:<10} {len(recs):>4} sequences")
            continue

        if args.offline:
            _log(f"offline  {lk:<10} no cache present; skipping")
            continue

        fetched_any = True
        seen_md5, recs = set(), []
        for t in taxa:
            got = ncbi_fetch(t["name"], lk, lq, refs_cfg["ncbi"],
                             int(refs_cfg["ncbi"]["max_per_taxon_locus"]))
            if not args.no_bold and refs_cfg.get("bold", {}).get("optional", True):
                got += bold_fetch(t["name"], lk, refs_cfg["bold"])

            kept = 0
            for r in got:
                # Dedupe on sequence content, not accession: the same sequence is
                # frequently submitted under both a synonym and the accepted name,
                # and counting it twice would inflate apparent reference depth
                # exactly where the §13.3 `min_reference_seqs_per_species` check
                # is supposed to protect us.
                m = r.md5()
                if m in seen_md5:
                    continue
                seen_md5.add(m)
                r.taxon = accepted[t["name"]]
                r.class_key = t["class_key"]
                recs.append(r)
                kept += 1
            _log(f"ncbi     {lk:<10} {t['name']:<22} {kept:>3} kept")

        all_records[lk] = recs
        write_fasta(recs, cache)
        _log(f"wrote    {os.path.relpath(cache, PATHS.root)}  ({len(recs)} sequences)")

    # ---------------- coverage matrix ----------------
    accepted_names = sorted(set(accepted.values()))
    matrix: Dict[str, Dict[str, int]] = {}
    for a in accepted_names:
        matrix[a] = {L["key"]: sum(1 for r in all_records[L["key"]] if r.taxon == a)
                     for L in loci}

    min_refs = int(mol["identification"]["min_reference_seqs_per_species"])
    total = sum(len(v) for v in all_records.values())

    print(f"\n  Reference coverage — {total} sequences, "
          f"{len(accepted_names)} accepted taxa x {len(loci)} loci")
    print("  " + "-" * 74)
    hdr = f"  {'accepted name':<24}" + "".join(f"{L['key']:>12}" for L in loci) + f"{'usable':>9}"
    print(hdr)
    for a in accepted_names:
        row = f"  {a:<24}"
        usable = 0
        for L in loci:
            n = matrix[a][L["key"]]
            row += f"{(str(n) if n else '—'):>12}"
            usable += 1 if n >= min_refs else 0
        row += f"{usable:>9}"
        print(row)

    # ---------------- Risk 9 / Risk 10 assessment ----------------
    empty = [(a, L["key"]) for a in accepted_names for L in loci if matrix[a][L["key"]] == 0]
    thin = [(a, L["key"], matrix[a][L["key"]]) for a in accepted_names for L in loci
            if 0 < matrix[a][L["key"]] < min_refs]
    uncertifiable = [a for a in accepted_names
                     if sum(1 for L in loci if matrix[a][L["key"]] >= min_refs)
                     < int(mol["release"]["min_loci_agreeing"])]
    no_core = [a for a in accepted_names
               if not any(matrix[a][L["key"]] >= min_refs
                          for L in loci if L["role"] == "core")]

    print(f"\n  Risk assessment against Appendix B.9 ('coverage assumed adequate')")
    print(f"    empty  taxon x locus cells : {len(empty)} of {len(accepted_names) * len(loci)}")
    print(f"    thin   (1..{min_refs - 1} sequences)     : {len(thin)}")
    if empty:
        print(f"    empty cells: " + ", ".join(f"{a}/{l}" for a, l in empty[:6])
              + (" ..." if len(empty) > 6 else ""))

    predicted = {(e["taxon"], e["locus"]) for e in refs_cfg.get("expected_sparse", [])}
    hit = [(a, l) for a, l in empty if (a, l) in predicted]
    if predicted:
        print(f"    of the {len(predicted)} sparse cells predicted in config §13.8, "
              f"{len(hit)} came back empty as expected")

    if uncertifiable:
        print(f"\n    !! {len(uncertifiable)} taxon/taxa cannot reach the §13.5 "
              f"two-locus agreement requirement\n       from public references alone: "
              f"{', '.join(uncertifiable)}")
        print("       Consequence: vouchers of these taxa will QUARANTINE rather than")
        print("       certify. That is Risk 10 measured, not assumed — and it is the")
        print("       direct argument for §5.4 mitigation 9, 'sequence and curate our")
        print("       own vouchers; the resulting reference set becomes an asset'.")
    if no_core:
        print(f"    !! no usable CORE locus (rbcL/matK) for: {', '.join(no_core)}")

    # ---------------- reports ----------------
    cov = {
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sources": ["NCBI Entrez nuccore"] + ([] if args.no_bold else ["BOLD Systems public API"]),
        "loci": [{k: L[k] for k in ("key", "role", "genome", "discrimination_rank")} for L in loci],
        "accepted_taxa": accepted_names,
        "synonyms_merged": synonyms,
        "matrix": matrix,
        "totals_by_locus": {L["key"]: len(all_records[L["key"]]) for L in loci},
        "total_sequences": total,
        "min_reference_seqs_per_species": min_refs,
        "empty_cells": [{"taxon": a, "locus": l} for a, l in empty],
        "thin_cells": [{"taxon": a, "locus": l, "n": n} for a, l, n in thin],
        "taxa_below_two_locus_requirement": uncertifiable,
        "taxa_without_usable_core_locus": no_core,
        "predicted_sparse_confirmed": [{"taxon": a, "locus": l} for a, l in hit],
        "appendix_b9_verdict": (
            "SUPPORTED — public reference coverage is adequate for every taxon"
            if not uncertifiable else
            f"NOT SUPPORTED — {len(uncertifiable)} taxon/taxa lack the reference depth "
            f"to certify a voucher from public data alone"),
    }
    with open(os.path.join(REF_DIR, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(cov, fh, indent=1)
    rep = os.path.join(PATHS.reports, "barcode_reference_coverage.json")
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(cov, fh, indent=1)

    _figure(matrix, accepted_names, loci, min_refs)

    if fetched_any:
        _log(f"\n  {total} real sequences cached under "
             f"{os.path.relpath(REF_DIR, PATHS.root)}/")
    print(f"  Report   -> {os.path.relpath(rep, PATHS.root)}")
    print(f"  Figure   -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig11_reference_coverage.png")
    print("STAGE 11 complete.\n")
    return 0


def _figure(matrix, taxa, loci, min_refs) -> None:
    keys = [L["key"] for L in loci]
    M = np.array([[matrix[a][k] for k in keys] for a in taxa], dtype=float)

    fig, ax = plt.subplots(figsize=(7.6, 0.52 * len(taxa) + 2.4))
    shown = np.log10(M + 1)
    ax.imshow(shown, cmap="YlGnBu", aspect="auto", vmin=0, vmax=max(shown.max(), 1.0))

    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            n = int(M[i, j])
            if n == 0:
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, facecolor="#f4d4d4",
                                           edgecolor="#c0392b", lw=1.2))
                txt, col = "none", "#8a1030"
            elif n < min_refs:
                txt, col = str(n), "#8a5a00"
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, facecolor="none",
                                           edgecolor="#d98c1f", lw=1.6, ls="--"))
            else:
                txt, col = str(n), ("white" if shown[i, j] > shown.max() * 0.6 else "#12303f")
            ax.text(j, i, txt, ha="center", va="center", fontsize=8, color=col,
                    fontweight="bold" if n == 0 else "normal")

    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([f"{L['key']}\n({L['role']})" for L in loci], fontsize=8)
    ax.set_yticks(range(len(taxa)))
    ax.set_yticklabels([t.replace(" ", " ") for t in taxa], fontsize=8, style="italic")
    ax.set_title("Public barcode reference coverage (NCBI + BOLD)\n"
                 f"red = none, dashed = below the {min_refs}-sequence floor for a species call",
                 fontsize=9.5)
    ax.set_xticks(np.arange(-.5, len(keys), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(taxa), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.4)
    ax.tick_params(which="minor", length=0)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig11_reference_coverage.png"))
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
