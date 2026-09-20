#!/usr/bin/env python
"""
STAGE 12 — Run the §3.4 verification pipeline against a known answer key.
=========================================================================

Proposal §3.4 specifies a seven-stage pipeline and claims it converts the
weakest part of v1.0 into something auditable:

    "This is a bioinformatics pipeline, it is standard, and it is cheap relative
     to a flying day. It also converts the least defensible part of the v1.0
     proposal — 'our botanist identified them' — into an auditable, reproducible,
     versioned procedure."

A pipeline that is never tested against a known truth is an assertion with more
steps. So this stage builds a test set with a real answer key:

**Held-out real sequences as vouchers.** A stratified subset of the sequences
stage 11 downloaded is *removed from the reference set* and degraded into
simulated Sanger reads. Their true identities are real GenBank identities, so
"the pipeline recovered the right species" is a measurable claim rather than a
modelled one.

What is real and what is modelled, precisely
--------------------------------------------
**Real:** the sequences, their identities, the reference set they are searched
against, the reference coverage, the barcode gaps, and therefore every
identification success and failure.

**Modelled:** (a) read degradation — the primer-proximal dropout, 3' decay and
substitution rates of a Sanger trace; (b) voucher assembly — a voucher is built
from one held-out sequence per locus *of the same species*, whereas a real
voucher's four loci come from one plant; (c) the visual field call attached to
each voucher, drawn at the §13.7 error rates.

(b) matters and is stated rather than buried: it means the pipeline is never
tested against a specimen whose loci genuinely disagree — a hybrid, an
introgressed individual, or a contaminated reaction. Those are exactly the cases
§13.5's ``quarantine_rather_than_discard`` exists for, and this design cannot
exercise them. Real vouchers will.

Outputs
-------
* ``outputs/reports/barcode_verification.json`` — certificates, metrics, gaps
* ``data/processed/certificates.json`` — consumed by stages 13 and 14
* ``outputs/figures/fig12a_verification.png``, ``fig12b_barcode_gap.png``
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mikania.barcode import (SeqRecord, Voucher, adjudicate, barcode_gap, chimera_score,
                             curate_references, identify_locus, pairwise_distances,
                             place_query, qc_check, quality_trim, read_fasta,
                             simulate_field_call, simulate_sanger_read)
from mikania.config import PATHS, load_config, rng, site_table
from mikania.labelerror import concordance

REF_DIR = os.path.join(PATHS.raw, "barcode_refs")

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

HOLDOUT_FRAC = 0.28          # of each taxon's sequences at each locus
MIN_KEEP_AS_REFERENCE = 1    # never strip a taxon/locus to zero references


def _load_refs(cfg) -> Dict[str, List[SeqRecord]]:
    out: Dict[str, List[SeqRecord]] = {}
    for L in cfg["molecular"]["loci"]:
        p = os.path.join(REF_DIR, f"{L['key']}.fasta")
        if not os.path.exists(p):
            continue
        recs = read_fasta(p)
        for r in recs:
            r.locus = L["key"]          # trust the file we are reading, not the defline
        out[L["key"]] = [r for r in recs if r.taxon]
    return out


def _split(refs: Dict[str, List[SeqRecord]], gen):
    """
    Stratified hold-out per taxon per locus.

    A taxon/locus cell is never stripped below ``MIN_KEEP_AS_REFERENCE``. Emptying
    a cell to build a test voucher would manufacture a failure that the public
    databases do not actually have, and stage 11 already reports the real empty
    cells — inventing more would corrupt the Risk-10 measurement.
    """
    held: Dict[str, List[SeqRecord]] = defaultdict(list)
    kept: Dict[str, List[SeqRecord]] = defaultdict(list)

    for locus, recs in refs.items():
        by_taxon: Dict[str, List[SeqRecord]] = defaultdict(list)
        for r in recs:
            by_taxon[r.taxon].append(r)
        for taxon, group in by_taxon.items():
            n_hold = int(np.floor(len(group) * HOLDOUT_FRAC))
            n_hold = min(n_hold, max(len(group) - MIN_KEEP_AS_REFERENCE, 0))
            idx = gen.permutation(len(group))
            for i, j in enumerate(idx):
                (held if i < n_hold else kept)[locus].append(group[j])
    return kept, held


def _build_vouchers(held, cfg, gen) -> List[Voucher]:
    """
    Assemble vouchers from held-out sequences, one per locus per specimen.

    MODELLED STEP — see the module docstring. Real vouchers yield four loci from
    one plant; these pair independent GenBank accessions of the same species.
    """
    loci = [L["key"] for L in cfg["molecular"]["loci"]]
    sites = [s["key"] for s in site_table(cfg)]
    seasons = cfg["molecular"]["voucher_plan"]["seasons"]
    sterile_frac = float(cfg["molecular"]["voucher_plan"]["sterile_fraction"])
    classes = sorted({r.class_key for L in loci for r in held.get(L, []) if r.class_key})

    pools: Dict[str, Dict[str, List[SeqRecord]]] = defaultdict(lambda: defaultdict(list))
    for L in loci:
        for r in held.get(L, []):
            pools[r.taxon][L].append(r)

    vouchers: List[Voucher] = []
    n = 0
    for taxon, per_locus in pools.items():
        depth = max(len(v) for v in per_locus.values())
        cls = next(r.class_key for v in per_locus.values() for r in v)
        for i in range(depth):
            n += 1
            sterile = bool(gen.random() < sterile_frac)
            site = sites[n % len(sites)]
            season = seasons[n % len(seasons)]
            v = Voucher(
                voucher_id=f"HK-{season[:3].upper()}-{n:04d}",
                site_key=site, season=season,
                lat=float(next(s["centroid"][0] for s in site_table(cfg) if s["key"] == site)
                          + gen.normal(0, 0.004)),
                lon=float(next(s["centroid"][1] for s in site_table(cfg) if s["key"] == site)
                          + gen.normal(0, 0.004)),
                true_class=cls, true_taxon=taxon, sterile=sterile,
                field_call=simulate_field_call(cls, sterile, classes,
                                               cfg["molecular"]["field_error"], gen))
            for L in loci:
                if i < len(per_locus.get(L, [])):
                    v.reads[L] = simulate_sanger_read(per_locus[L][i], gen)
            if v.reads:
                vouchers.append(v)
    return vouchers


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=12)
    mol = cfg["molecular"]

    refs_raw = _load_refs(cfg)
    if not refs_raw:
        print("!! no reference FASTA found — run scripts/11_fetch_barcode_references.py first")
        return 1

    print("\nSTAGE 12 — barcode verification against a known answer key")
    print("=" * 78)

    # ---- curate the public reference set BEFORE anything depends on it -----
    # Risk 10 names references that are "sparse OR CONFLICTING". Stage 11 measures
    # sparse; this measures conflicting, and it has to happen first, because a
    # mis-annotated record left in the reference set widens its species' apparent
    # intraspecific range and pushes every genuine query into the ambiguous bucket.
    print("\n  Reference curation (Risk 10, the 'conflicting' half)")
    print("  " + "-" * 74)
    refs_all: Dict[str, List[SeqRecord]] = {}
    dist_cache: Dict[str, Any] = {}
    curation: Dict[str, Any] = {}
    for L in mol["loci"]:
        lk = L["key"]
        recs = refs_raw.get(lk, [])
        if len(recs) < 4:
            refs_all[lk] = recs
            continue
        D = pairwise_distances(recs, mol["phylogeny"])
        dist_cache[lk] = (recs, D)
        cur = curate_references(recs, mol["phylogeny"], D)
        curation[lk] = {k: v for k, v in cur.items() if k != "curated"}
        refs_all[lk] = cur["curated"]
        if cur["n_flagged"]:
            print(f"    {lk:<11} {cur['n_flagged']} of {cur['n_input']} records discordant "
                  f"with their own species:")
            for f in cur["flagged"]:
                d = f.get("distance_to_consensus")
                print(f"        {f['accession']:<14} {f['taxon']:<22} "
                      f"d to consensus cluster (n={f['consensus_cluster_size']}) = "
                      f"{'—' if d is None else f'{d:.3f}'}  (threshold {f['threshold']})")
        else:
            print(f"    {lk:<11} {cur['n_input']} records, none discordant")

    n_flagged_total = sum(c["n_flagged"] for c in curation.values())
    if n_flagged_total:
        print(f"\n    {n_flagged_total} public record(s) excluded from the reference set and")
        print("    retained in the audit trail. Deciding a GenBank record is wrong is a")
        print("    taxonomic judgement, so the accession and its evidence are surfaced")
        print("    rather than silently dropped (§6.1.6 auditability).")

    kept, held = _split(refs_all, gen)
    loci_meta = {L["key"]: L for L in mol["loci"]}
    print(f"  references retained : {sum(len(v) for v in kept.values())}")
    print(f"  held out as vouchers: {sum(len(v) for v in held.values())}")

    vouchers = _build_vouchers(held, cfg, gen)
    print(f"  vouchers assembled  : {len(vouchers)} "
          f"({sum(len(v.reads) for v in vouchers)} reads across "
          f"{len(mol['loci'])} loci)\n")

    # ================= the §3.4 pipeline, voucher by voucher ===============
    certificates: List[Dict[str, Any]] = []
    qc_fail = defaultdict(int)
    chimera_flags = 0
    placements_run = placements_resolved = 0

    for v in vouchers:
        per_locus: Dict[str, Dict[str, Any]] = {}
        for locus, read in v.reads.items():
            trimmed = quality_trim(read, mol["qc"])
            qc = qc_check(trimmed, mol["qc"])
            if not qc["pass"]:
                for r in qc["reasons"]:
                    qc_fail[r.split()[0]] += 1
                per_locus[locus] = {"status": "qc_fail", "call": None,
                                    "reasons": qc["reasons"], "qc": qc, "hits": []}
                continue

            res = identify_locus(trimmed, kept.get(locus, []), mol["identification"])
            res["qc"] = qc

            ch = chimera_score(trimmed, kept.get(locus, []))
            res["chimera"] = ch
            if ch.get("suspect"):
                chimera_flags += 1
                res["status"], res["call"] = "chimera_suspect", None
                res.setdefault("reasons", []).append("possible chimera: halves disagree")

            # §3.4 adjudication: escalate an ambiguous similarity search to
            # phylogenetic placement rather than lowering the threshold.
            if res["status"] == "ambiguous" and \
                    mol["identification"]["ambiguous_action"] == "phylogenetic_placement":
                placements_run += 1
                pl = place_query(trimmed, kept.get(locus, []), mol["phylogeny"], gen)
                res["placement"] = pl
                if pl["status"] == "placed":
                    placements_resolved += 1
            per_locus[locus] = res

        cert = adjudicate(v, per_locus, mol, loci_meta)
        cert.update({
            "true_taxon": v.true_taxon, "true_class": v.true_class,
            "field_call": v.field_call, "sterile": v.sterile,
            "site_key": v.site_key, "season": v.season,
            "lat": v.lat, "lon": v.lon,
            "n_loci_attempted": len(v.reads),
        })
        cert["correct"] = (cert["status"] == "certified"
                           and cert["certified_taxon"] == v.true_taxon)
        certificates.append(cert)

    # ================= metrics =============================================
    n = len(certificates)
    certified = [c for c in certificates if c["status"] == "certified"]
    quarantined = [c for c in certificates if c["status"] == "quarantined"]
    correct = [c for c in certified if c["correct"]]
    wrong = [c for c in certified if not c["correct"]]

    print("  §3.4 pipeline outcome")
    print("  " + "-" * 74)
    print(f"    certified            {len(certified):>4} / {n}  ({len(certified) / n:.1%})")
    print(f"      of which correct   {len(correct):>4}       ({len(correct) / max(len(certified), 1):.1%} precision)")
    print(f"      of which WRONG     {len(wrong):>4}")
    print(f"    quarantined          {len(quarantined):>4} / {n}  ({len(quarantined) / n:.1%})")
    print(f"    phylogenetic placement run on {placements_run} ambiguous locus results, "
          f"{placements_resolved} resolved")
    if chimera_flags:
        print(f"    chimera-suspect reads flagged: {chimera_flags}")
    if qc_fail:
        print(f"    QC failures by first reason: {dict(qc_fail)}")

    if wrong:
        print("\n    !! WRONG certifications — the failure mode that matters:")
        for c in wrong[:5]:
            print(f"       {c['voucher_id']}  true {c['true_taxon']} -> "
                  f"certified {c['certified_taxon']} (conf {c['confidence']:.2f})")
    else:
        print("\n    No wrong certifications. Every specimen the gate passed was correct;")
        print("    the specimens it could not resolve were quarantined rather than guessed.")
        print("    That asymmetry is the design intent: §13.5 prefers a refusal to a")
        print("    confident error, because a wrong label propagates silently (Risk 9)")
        print("    while a quarantine merely costs a re-collection.")

    # ---- who gets quarantined, and why -----------------------------------
    by_taxon = defaultdict(lambda: {"n": 0, "certified": 0})
    for c in certificates:
        by_taxon[c["true_taxon"]]["n"] += 1
        by_taxon[c["true_taxon"]]["certified"] += int(c["status"] == "certified")
    print("\n  Certification rate by species (the Risk-10 view)")
    for t, d in sorted(by_taxon.items(), key=lambda kv: kv[1]["certified"] / max(kv[1]["n"], 1)):
        bar = "#" * int(round(18 * d["certified"] / max(d["n"], 1)))
        print(f"    {t:<24} {d['certified']:>2}/{d['n']:<3} {bar}")

    reason_tally = defaultdict(int)
    for c in quarantined:
        for r in c["reasons"]:
            reason_tally[r.split(":")[0].split("—")[0].strip()] += 1
    if reason_tally:
        print("\n  Why vouchers were quarantined")
        for r, k in sorted(reason_tally.items(), key=lambda kv: -kv[1]):
            print(f"    {k:>3}  {r}")

    # ================= barcode gap on REAL sequences =======================
    print("\n  Barcode gap by locus (real public sequences — Risk 10 measured)")
    print("  " + "-" * 74)
    gaps = {}
    for L in mol["loci"]:
        # Gaps are computed on the CURATED set: including a record already shown to
        # disagree with its own species would be measuring the defect, not the locus.
        g = barcode_gap(refs_all.get(L["key"], []), L["key"], mol["phylogeny"])
        gaps[L["key"]] = g
        if g["status"] != "ok":
            print(f"    {L['key']:<11} insufficient data "
                  f"({g['n_sequences']} seqs, {g['n_taxa']} taxa)")
            continue
        verdict = ("GAP" if g["barcode_gap"]
                   else ("robust only" if g["barcode_gap_robust"] else "no gap"))
        print(f"    {L['key']:<11} within max/p95 {g['max_within']:.4f}/{g['p95_within']:.4f}   "
              f"between min/p05 {g['min_between']:.4f}/{g['p05_between']:.4f}   -> {verdict}")
    with_gap = [k for k, g in gaps.items() if g.get("barcode_gap")]
    robust = [k for k, g in gaps.items() if g.get("barcode_gap_robust")]
    print(f"\n    strict gap: {len(with_gap)}/{len(gaps)} loci"
          + (f" ({', '.join(with_gap)})" if with_gap else ""))
    print(f"    robust gap: {len(robust)}/{len(gaps)} loci"
          + (f" ({', '.join(robust)})" if robust else ""))
    print("    The strict criterion is decided by two extreme order statistics, so one")
    print("    defective public record can sink a locus; the robust criterion uses the")
    print("    95th/5th percentiles. Both are reported rather than whichever flatters.")
    print("    Where there is no gap, that locus cannot carry a species call alone —")
    print("    which is why §13.5 requires two loci to agree rather than trusting one.")

    # ================= concordance: field call vs certified ================
    pairs = [(c["field_call"], c["certified_class"]) for c in certified
             if c["certified_class"]]
    conc = concordance([p[0] for p in pairs], [p[1] for p in pairs]) if pairs else {"n": 0}
    if conc.get("n"):
        print(f"\n  Visual field call vs barcode-certified identity (§5.1 mitigation 2)")
        print(f"    {conc['interpretation']}")
        st = [c for c in certified if c["sterile"] and c["certified_class"]]
        fe = [c for c in certified if not c["sterile"] and c["certified_class"]]
        for label, group in (("sterile", st), ("fertile", fe)):
            if group:
                agree = sum(1 for c in group if c["field_call"] == c["certified_class"])
                print(f"    {label:<8} specimens: {agree}/{len(group)} "
                      f"({agree / len(group):.0%}) visual calls correct")
        print("    The sterile/fertile split is the operational point: §5.1(3) proposes")
        print("    surveying inside the flowering window, and this is the quantified")
        print("    reason why — a fertile specimen is a far easier identification.")

    # ================= write ===============================================
    out = {
        "real": ["reference sequences", "held-out voucher sequences and their identities",
                 "reference coverage", "barcode gaps", "all identification outcomes"],
        "modelled": ["Sanger read degradation", "voucher assembly across loci",
                     "visual field calls (§13.7 rates)"],
        "n_vouchers": n,
        "n_certified": len(certified),
        "n_quarantined": len(quarantined),
        "n_correct": len(correct),
        "n_wrong": len(wrong),
        "certification_rate": round(len(certified) / max(n, 1), 4),
        "precision_of_certified": round(len(correct) / max(len(certified), 1), 4),
        "placements_run": placements_run,
        "placements_resolved": placements_resolved,
        "chimera_flags": chimera_flags,
        "qc_failures_by_reason": dict(qc_fail),
        "by_taxon": {k: dict(v) for k, v in by_taxon.items()},
        "quarantine_reasons": dict(reason_tally),
        "reference_curation": curation,
        "n_reference_records_flagged": n_flagged_total,
        "barcode_gap": gaps,
        "loci_with_gap": with_gap,
        "loci_with_robust_gap": robust,
        "concordance": conc,
        "certificates": certificates,
    }
    rep = os.path.join(PATHS.reports, "barcode_verification.json")
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    proc = os.path.join(PATHS.processed, "certificates.json")
    with open(proc, "w", encoding="utf-8") as fh:
        json.dump(certificates, fh, indent=1, default=str)

    _figures(out, gaps, by_taxon, cfg)

    print(f"\n  Report       -> {os.path.relpath(rep, PATHS.root)}")
    print(f"  Certificates -> {os.path.relpath(proc, PATHS.root)}")
    print(f"  Figures      -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig12*.png")
    print("STAGE 12 complete.\n")
    return 0


def _figures(out, gaps, by_taxon, cfg) -> None:
    # ---- fig12a: outcomes + per-species certification ---------------------
    fig, axes = plt.subplots(1, 3, figsize=(13.4, 4.3),
                             gridspec_kw={"width_ratios": [0.8, 1.25, 1.0]})

    ax = axes[0]
    vals = [out["n_correct"], out["n_wrong"], out["n_quarantined"]]
    cols = ["#1f8a70", "#c0392b", "#d98c1f"]
    labs = ["certified\ncorrect", "certified\nWRONG", "quarantined"]
    ax.bar(range(3), vals, color=cols, edgecolor="white", linewidth=0.7)
    for i, v in enumerate(vals):
        ax.annotate(str(v), (i, v + max(vals) * 0.02), ha="center", fontsize=9)
    ax.set_xticks(range(3))
    ax.set_xticklabels(labs, fontsize=8)
    ax.set(ylabel="vouchers", title=f"Pipeline outcome (n={out['n_vouchers']})")

    ax = axes[1]
    taxa = sorted(by_taxon, key=lambda t: by_taxon[t]["certified"] / max(by_taxon[t]["n"], 1))
    y = np.arange(len(taxa))
    rate = [by_taxon[t]["certified"] / max(by_taxon[t]["n"], 1) * 100 for t in taxa]
    ax.barh(y, rate, color=["#c0392b" if r < 50 else "#1f8a70" for r in rate], height=0.66)
    for i, t in enumerate(taxa):
        ax.annotate(f"{by_taxon[t]['certified']}/{by_taxon[t]['n']}",
                    (rate[i] + 1.5, y[i]), va="center", fontsize=7)
    ax.set_yticks(y)
    ax.set_yticklabels(taxa, fontsize=8, style="italic")
    ax.set(xlabel="certified (%)", xlim=(0, 115),
           title="Certification rate by species\n(low = public reference coverage too thin)")

    ax = axes[2]
    keys = [k for k, g in gaps.items() if g.get("status") == "ok"]
    x = np.arange(len(keys))
    # Robust percentiles as the bars, strict extremes as whiskers — so the reader
    # sees both criteria at once and can tell when a locus is sunk by one pair.
    ax.bar(x - 0.19, [gaps[k]["p95_within"] for k in keys], 0.38,
           label="within-species, p95", color="#d98c1f")
    ax.bar(x + 0.19, [gaps[k]["p05_between"] for k in keys], 0.38,
           label="between-species, p05", color="#1f8a70")
    for i, k in enumerate(keys):
        ax.plot([i - 0.19, i - 0.19], [gaps[k]["p95_within"], gaps[k]["max_within"]],
                color="#8a5a00", lw=1.1)
        ax.plot([i - 0.19], [gaps[k]["max_within"]], "_", color="#8a5a00", ms=9)
        ax.plot([i + 0.19, i + 0.19], [gaps[k]["min_between"], gaps[k]["p05_between"]],
                color="#12503f", lw=1.1)
        ax.plot([i + 0.19], [gaps[k]["min_between"]], "_", color="#12503f", ms=9)
        tag = ("strict gap" if gaps[k]["barcode_gap"]
               else ("robust only" if gaps[k]["barcode_gap_robust"] else "no gap"))
        col = "#1f8a70" if gaps[k]["barcode_gap"] else (
            "#d98c1f" if gaps[k]["barcode_gap_robust"] else "#c0392b")
        ax.annotate(tag, (i, max(gaps[k]["max_within"], gaps[k]["p05_between"]) * 1.07),
                    ha="center", fontsize=6.6, color=col, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(keys, fontsize=8)
    ax.set(ylabel="Jukes-Cantor distance",
           title="Barcode gap, real sequences\nbars = p95/p05, whiskers to the extremes")
    ax.legend(fontsize=6.8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig12a_verification.png"))
    plt.close(fig)

    # ---- fig12b: concordance confusion matrix -----------------------------
    conc = out.get("concordance", {})
    if not conc.get("n"):
        return
    M = np.array(conc["confusion_matrix"], dtype=float)
    labels = conc["labels"]
    fig, ax = plt.subplots(figsize=(5.8, 5.0))
    norm = M / np.maximum(M.sum(axis=1, keepdims=True), 1)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if M[i, j]:
                ax.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=8,
                        color="white" if norm[i, j] > 0.55 else "#12303f")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([l.replace("_", "\n") for l in labels], fontsize=7)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels([l.replace("_", "\n") for l in labels], fontsize=7)
    ax.set(xlabel="visual field call", ylabel="barcode-certified identity",
           title=f"Field call vs sequence (§5.1.2)\nagreement {conc['agreement']:.0%}, "
                 f"kappa {conc['cohens_kappa']:.2f}")
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig12b_concordance.png"))
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
