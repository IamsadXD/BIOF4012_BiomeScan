#!/usr/bin/env python
"""
STAGE 14 — Build, version and value the reference database (deliverable 4).
===========================================================================

Proposal §7.1:

    "**Be precise about what that asset is.** It is not the drone, the sensor,
     or the classifier — all three are purchasable by anyone. It is the
     molecularly-verified spectral reference database of Hong Kong invasive
     flora (deliverable 4, §3.1): barcode-certified vouchers, paired field and
     airborne spectra, indexed across seasons, sites, infestation levels and
     illumination conditions, accumulating year on year."

This stage turns the certificates from stage 12 and the spectral library from
stage 02 into that object, and then does the three things that distinguish an
asset from a folder of CSVs:

**Versions it.** Releases are immutable and identified, so a classifier can name
what trained it and an accuracy figure remains auditable years later.

**Checksums it.** Over the row content, not the file — SQLite rewrites pages for
reasons that have nothing to do with the science, and a licensee needs to verify
what they hold, not what byte layout it happens to have.

**Prices it.** §7.1 argues the pricing floor is replacement cost. Stage 14
computes that from actual row counts and the §14 field-day model rather than
asserting "several million dollars".

It also enforces the §3.4 release gate in a way that is checkable:
:func:`mikania.refdb.training_label_set` returns certified vouchers and nothing
else, and :func:`mikania.refdb.integrity_check` fails the build if a quarantined
voucher or a sub-threshold confidence has leaked in. A policy that lives only in
prose is a policy nobody can audit.

Scope
-----
Vouchers derive from stage 12, whose certificates come from real held-out GenBank
sequences run through the §3.4 pipeline. The paired spectra attached here are
drawn from the stage-02 library, whose species contrasts are modelled. So the
database structure, the gate, the versioning and the valuation arithmetic are
real; the row *contents* are a Phase 0 rehearsal, and the report says so.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mikania import refdb
from mikania.barcode import read_fasta
from mikania.config import PATHS, load_config, rng, wavelengths
from mikania.spectral_library import load_library, sample_class_spectra

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})

REF_DIR = os.path.join(PATHS.raw, "barcode_refs")


def main() -> int:
    cfg = load_config()
    PATHS.ensure()
    gen = rng(cfg, offset=14)
    mol = cfg["molecular"]

    cert_p = os.path.join(PATHS.processed, "certificates.json")
    if not os.path.exists(cert_p):
        print("!! certificates.json missing — run scripts/12_barcode_verify_vouchers.py first")
        return 1
    with open(cert_p, encoding="utf-8") as fh:
        certificates = json.load(fh)

    print("\nSTAGE 14 — reference database (deliverable 4, the asset)")
    print("=" * 78)

    db_path = os.path.join(PATHS.root, cfg["reference_database"]["path"])
    conn = refdb.connect(db_path, fresh=True)
    refdb.log(conn, "build_start", "stage14", {"n_certificates": len(certificates)})

    # ---------------- reference sequences (provenance of the calls) --------
    n_ref = 0
    for L in mol["loci"]:
        p = os.path.join(REF_DIR, f"{L['key']}.fasta")
        if os.path.exists(p):
            recs = read_fasta(p)
            for r in recs:
                r.locus = L["key"]
            n_ref += refdb.add_reference_sequences(conn, [r for r in recs if r.taxon])
    print(f"  reference sequences  {n_ref}")

    # ---------------- vouchers, barcodes, certificates, spectra -----------
    lib_p = os.path.join(PATHS.processed, "spectral_library.npz")
    lib = load_library(lib_p) if os.path.exists(lib_p) else None
    wl = wavelengths(cfg)
    gen_km = float(mol["deposition"]["coordinate_generalisation_km"])

    n_spec = 0
    for c in certificates:
        refdb.add_voucher(conn, {
            "voucher_id": c["voucher_id"], "site_key": c["site_key"],
            "season": c["season"], "lat": c["lat"], "lon": c["lon"],
            "sterile": c.get("sterile", True), "field_call": c.get("field_call"),
            "permit_ref": "AFCD-RESEARCH-COLLAB [VERIFY §10.9]",
        }, generalise_km=gen_km)

        for locus, det in (c.get("per_locus") or {}).items():
            qc = det.get("qc") if isinstance(det, dict) else None
            refdb.add_barcode(conn, c["voucher_id"], locus,
                              sequence=f"<withheld:{c['voucher_id']}:{locus}>",
                              qc=qc or {"pass": det.get("status") != "qc_fail",
                                        "reasons": det.get("reasons", [])},
                              source="sanger (simulated read, stage 12)")

        refdb.add_certificate(conn, c)

        # Paired spectra. §13.6 `paired_spectra_required`: a voucher without them
        # is a herbarium specimen, not a row in the asset (§7.1).
        if lib is not None and c.get("certified_class"):
            for kind in ("leaf", "canopy_patch"):
                S = sample_class_spectra(lib, cfg, c["certified_class"], c["season"],
                                         1, gen, site_key=c["site_key"])
                refdb.add_spectrum(conn, c["voucher_id"], kind, wl, S[0],
                                   season=c["season"],
                                   solar_zenith=float(gen.uniform(22, 48)),
                                   view_zenith=float(gen.uniform(0, 12)),
                                   canopy_fraction=float(gen.uniform(0.15, 0.95)))
                n_spec += 1
    conn.commit()

    summary = refdb.summary(conn)
    print(f"  vouchers             {summary['counts']['voucher']}")
    print(f"  barcodes             {summary['counts']['barcode']}")
    print(f"  certificates         {summary['counts']['certificate']}")
    print(f"  paired spectra       {summary['counts']['spectrum']}")

    # ---------------- §8.4 deposition decisions ---------------------------
    dep = mol["deposition"]
    cov_p = os.path.join(PATHS.reports, "barcode_reference_coverage.json")
    coverage = json.load(open(cov_p, encoding="utf-8")) if os.path.exists(cov_p) else {}
    matrix = coverage.get("matrix", {})
    thr = int(dep["deposit_when_public_coverage_below"])

    n_dep = n_hold = 0
    for c in certificates:
        if c["status"] != "certified":
            continue
        taxon = c["certified_taxon"]
        for locus in (c.get("loci_used") or []):
            public_n = int(matrix.get(taxon, {}).get(locus, 0))
            decide = "deposit" if (dep["deposit_sequences"] and public_n < thr) else "withhold"
            conn.execute(
                "INSERT OR REPLACE INTO deposition (voucher_id, locus, decision, "
                "rationale, public_coverage, decided_utc) VALUES (?,?,?,?,?,datetime('now'))",
                (c["voucher_id"], locus, decide,
                 (f"public coverage {public_n} < {thr} for {taxon}/{locus}; depositing "
                  f"earns credibility at no competitive cost (§8.4)" if decide == "deposit"
                  else f"public coverage {public_n} adequate; no scientific gain from "
                       f"deposition (§8.4)"), public_n))
            n_dep += decide == "deposit"
            n_hold += decide == "withhold"
    conn.commit()

    print(f"\n  §8.4 deposition policy: {n_dep} sequence(s) to deposit, {n_hold} withheld")
    print(f"    Rule: deposit where public coverage < {thr} for that taxon/locus.")
    print(f"    Always withheld regardless: {', '.join(dep['withhold'])}.")
    print(f"    Published coordinates generalised to {gen_km:.0f} km.")
    print("    A barcode sequence alone does not let a competitor build the product;")
    print("    the sequence-to-spectrum-to-place linkage does, and that is what is kept.")

    # ---------------- the gate --------------------------------------------
    labels = refdb.training_label_set(conn)
    quar = refdb.quarantine_report(conn)
    print(f"\n  §3.4 release gate")
    print("  " + "-" * 74)
    print(f"    certified vouchers released to training : {len(labels)}")
    print(f"    quarantined, withheld from training     : {quar['n_quarantined']}")
    for reason, n in list(quar["reason_counts"].items())[:4]:
        print(f"        {n:>3}  {reason}")
    print("    training_label_set() cannot return a quarantined voucher — the gate is")
    print("    a function every training stage must call, not a rule in a document.")

    # ---------------- integrity -------------------------------------------
    ic = refdb.integrity_check(conn, cfg)
    print(f"\n  Integrity check: {'PASS' if ic['ok'] else 'FAIL'}")
    for c_ in ic["critical"]:
        print(f"    CRITICAL  {c_}")
    for w in ic["warnings"]:
        print(f"    warning   {w}")

    # ---------------- release ---------------------------------------------
    rel = refdb.create_release(conn, cfg, note="Phase 0 rehearsal build (stage 14)")
    print(f"\n  Release  {rel['release_id']}")
    print(f"    content sha256  {rel['content_sha256'][:32]}…")
    print(f"    {rel['n_certified']} certified / {rel['n_quarantined']} quarantined "
          f"of {rel['n_vouchers']} vouchers")

    # ---------------- valuation and licensing -----------------------------
    val = refdb.valuation(conn, cfg)
    print(f"\n  Replacement cost — the §7.1 pricing floor")
    print("  " + "-" * 74)
    print(f"    {val['n_vouchers']} vouchers ≈ {val['field_days_equivalent']} field days "
          f"-> HK${val['field_cost_hkd']:,} field")
    print(f"    lab at HK${val['lab_cost_per_voucher_hkd']}/voucher "
          f"-> HK${val['lab_cost_hkd']:,}")
    print(f"    x{val['overhead_multiplier']} overhead -> "
          f"**HK${val['replacement_cost_hkd']:,}**")
    print(f"    calendar time to replicate: {val['calendar_years_to_replicate']} years")
    print("    The money is a floor on price; the calendar time is the actual moat.")
    print("    A rival with twice the budget can field two crews and halve the field")
    print("    days. They cannot make October come sooner.")

    licences = {}
    print(f"\n  Licence tiers (§14)")
    for tier in cfg["reference_database"]["licence_tiers"]:
        lm = refdb.licence_manifest(conn, cfg, tier)
        licences[tier] = lm
        price = lm["price_hkd_per_year"]
        ptxt = ("—" if price is None else
                (f"HK${price[0]:,}-{price[1]:,}/yr" if isinstance(price, list)
                 else f"HK${price:,}/yr"))
        print(f"    {tier:<12} {len(lm['tables_granted'])} tables, spectra="
              f"{lm['spectra']!s:<15} {ptxt}")
        if lm["tables_withheld"]:
            print(f"                 withheld: {', '.join(lm['tables_withheld'])}")

    # ---------------- write ------------------------------------------------
    out = {
        "scope": ("Database structure, release gate, versioning and valuation arithmetic "
                  "are real. Voucher CONTENTS are a Phase 0 rehearsal: certificates come "
                  "from real held-out GenBank sequences (stage 12), paired spectra from "
                  "the modelled stage-02 library."),
        "db_path": os.path.relpath(db_path, PATHS.root),
        "release": rel,
        "summary": summary,
        "integrity": ic,
        "valuation": val,
        "licences": licences,
        "training_label_set_size": len(labels),
        "quarantine": {k: v for k, v in quar.items() if k != "vouchers"},
        "deposition": {"n_deposit": n_dep, "n_withhold": n_hold,
                       "threshold": thr, "withheld_fields": dep["withhold"],
                       "coordinate_generalisation_km": gen_km},
    }
    rep = os.path.join(PATHS.reports, "reference_database.json")
    with open(rep, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)

    _figure(summary, val, cfg)
    conn.close()

    print(f"\n  Database -> {os.path.relpath(db_path, PATHS.root)}")
    print(f"  Report   -> {os.path.relpath(rep, PATHS.root)}")
    print(f"  Figure   -> {os.path.relpath(PATHS.figures, PATHS.root)}/fig14_reference_db.png")
    print("STAGE 14 complete.\n")
    return 0 if ic["ok"] else 2


def _figure(summary, val, cfg) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.0),
                             gridspec_kw={"width_ratios": [1, 1.1, 1.1]})

    ax = axes[0]
    counts = summary["counts"]
    keys = ["voucher", "barcode", "certificate", "spectrum", "reference_sequence"]
    vals = [counts.get(k, 0) for k in keys]
    ax.barh(range(len(keys))[::-1], vals, color="#5b7fbd", height=0.62)
    for i, v in enumerate(vals):
        ax.annotate(str(v), (v + max(vals) * 0.02, len(keys) - 1 - i),
                    va="center", fontsize=8)
    ax.set_yticks(range(len(keys))[::-1])
    ax.set_yticklabels([k.replace("_", "\n") for k in keys], fontsize=8)
    ax.set(xlim=(0, max(vals) * 1.2), title="Database contents")

    ax = axes[1]
    by_status = {r["status"]: r["n"] for r in summary["by_status"]}
    by_class = summary["by_class"]
    if by_class:
        names = [(r["class_key"] or "—").replace("_", "\n") for r in by_class]
        ax.bar(range(len(by_class)), [r["n"] for r in by_class],
               color="#1f8a70", edgecolor="white", linewidth=0.6)
        ax.set_xticks(range(len(by_class)))
        ax.set_xticklabels(names, fontsize=7)
    ax.set(ylabel="certified vouchers",
           title=f"Released to training: {by_status.get('certified', 0)}\n"
                 f"quarantined: {by_status.get('quarantined', 0)}")

    ax = axes[2]
    parts = [val["field_cost_hkd"] / 1e3, val["lab_cost_hkd"] / 1e3,
             (val["replacement_cost_hkd"] - val["field_cost_hkd"]
              - val["lab_cost_hkd"]) / 1e3]
    labels = ["field\ncampaign", "laboratory", "overhead\n(permits, QC,\nre-collection)"]
    ax.bar(range(3), parts, color=["#1f8a70", "#5b7fbd", "#9aa5b1"],
           edgecolor="white", linewidth=0.6)
    for i, v in enumerate(parts):
        ax.annotate(f"{v:,.0f}k", (i, v + max(parts) * 0.03), ha="center", fontsize=7.5)
    ax.set_xticks(range(3))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set(ylabel="HK$ thousand",
           title=f"Replacement cost HK${val['replacement_cost_hkd']:,}\n"
                 f"+ {val['calendar_years_to_replicate']} yr of calendar time")
    fig.tight_layout()
    fig.savefig(os.path.join(PATHS.figures, "fig14_reference_db.png"))
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
