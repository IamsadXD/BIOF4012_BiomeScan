"""
The reference database — deliverable 4, and the thing the company actually owns.

    "**Be precise about what that asset is.** It is not the drone, the sensor, or
     the classifier — all three are purchasable by anyone. It is the
     molecularly-verified spectral reference database of Hong Kong invasive flora
     (deliverable 4, §3.1): barcode-certified vouchers, paired field and airborne
     spectra, indexed across seasons, sites, infestation levels and illumination
     conditions, accumulating year on year."                     — proposal §7.1

A folder of CSVs cannot be that asset, for three reasons that each turn into a
requirement:

**A classifier must be able to name what trained it.** Accuracy figures are
meaningless without a versioned label set, so releases are immutable and
identified (``MIKANIA-REFDB-v1.2+2026-08-11.a1b2c3``), and every certificate
records the release it entered.

**A licensee must be able to prove what they received.** So every release
carries a content checksum computed over the rows themselves, not over a file
whose bytes change when SQLite vacuums.

**A price needs a basis.** §7.1 argues the pricing floor is replacement cost —
"several years and several million dollars". :func:`valuation` computes that from
actual row counts and the §14 field-day model instead of asserting it, so the
number moves when the database does.

The gate
--------
:func:`training_label_set` is the enforcement point for §3.4's central rule —
"Every voucher entering the reference library is barcode-verified before it can
train anything." It returns certified vouchers and nothing else, and
:func:`integrity_check` fails loudly if a quarantined voucher has leaked into a
label set. Putting the rule in a function that the training stage must call is
the difference between a policy and a control.

Storage is SQLite because it is in the standard library, is a single file an
evaluator can copy, and gives transactions and referential integrity for free.
The tables are deliberately normalised around the *linkage* — voucher to
sequence to spectrum to place — because §8.4 identifies that linkage, not any one
of its components, as what must never be published:

    "**Retain** the paired spectra, the georeferenced metadata and the linkage
     between them; that linkage is the asset (§7.1), and it is not
     reconstructable from public sequence data."
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

SCHEMA = """
PRAGMA foreign_keys = ON;

-- An immutable, identified snapshot. Nothing is ever deleted from a release;
-- corrections create a new one, so a model trained last year remains auditable.
CREATE TABLE IF NOT EXISTS release (
    release_id     TEXT PRIMARY KEY,
    version        TEXT NOT NULL,
    created_utc    TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    pipeline_ver   TEXT,
    n_vouchers     INTEGER,
    n_certified    INTEGER,
    n_quarantined  INTEGER,
    content_sha256 TEXT,
    note           TEXT
);

-- The physical specimen. lat/lon are the true collection point; lat_public /
-- lon_public are generalised per §13.10 and are the ONLY coordinates that may
-- leave the building with a deposited sequence.
CREATE TABLE IF NOT EXISTS voucher (
    voucher_id   TEXT PRIMARY KEY,
    site_key     TEXT NOT NULL,
    season       TEXT NOT NULL,
    lat          REAL,
    lon          REAL,
    lat_public   REAL,
    lon_public   REAL,
    collected_utc TEXT,
    sterile      INTEGER NOT NULL DEFAULT 1,
    field_call   TEXT,
    collector    TEXT,
    permit_ref   TEXT,
    release_id   TEXT REFERENCES release(release_id)
);

CREATE TABLE IF NOT EXISTS barcode (
    barcode_id   TEXT PRIMARY KEY,
    voucher_id   TEXT NOT NULL REFERENCES voucher(voucher_id),
    locus        TEXT NOT NULL,
    sequence     TEXT NOT NULL,
    length_bp    INTEGER NOT NULL,
    mean_phred   REAL,
    qc_pass      INTEGER NOT NULL,
    qc_reasons   TEXT,
    md5          TEXT NOT NULL,
    source       TEXT,
    UNIQUE (voucher_id, locus)
);

-- The auditable output of §3.4. One row per voucher; `status` is the release gate.
CREATE TABLE IF NOT EXISTS certificate (
    voucher_id      TEXT PRIMARY KEY REFERENCES voucher(voucher_id),
    status          TEXT NOT NULL CHECK (status IN ('certified','quarantined')),
    certified_taxon TEXT,
    certified_class TEXT,
    proposed_taxon  TEXT,
    confidence      REAL,
    loci_used       TEXT,
    n_loci_agreeing INTEGER,
    reasons         TEXT,
    detail_json     TEXT,
    adjudicated_utc TEXT NOT NULL,
    pipeline_ver    TEXT,
    release_id      TEXT REFERENCES release(release_id)
);

-- Paired spectra. Without these a voucher is a herbarium specimen; with them it
-- is a row in the asset (§13.6 paired_spectra_required).
CREATE TABLE IF NOT EXISTS spectrum (
    spectrum_id   TEXT PRIMARY KEY,
    voucher_id    TEXT NOT NULL REFERENCES voucher(voucher_id),
    kind          TEXT NOT NULL,          -- leaf | canopy_patch | airborne
    instrument    TEXT,
    season        TEXT,
    solar_zenith  REAL,
    view_zenith   REAL,
    canopy_fraction REAL,
    wavelengths   BLOB NOT NULL,
    reflectance   BLOB NOT NULL,
    n_bands       INTEGER NOT NULL,
    measured_utc  TEXT
);

-- Provenance of what the identifications were made AGAINST. Without this the
-- certificates are not reproducible: public databases change, and a call made
-- against a 2026 snapshot cannot be re-derived from a 2029 one.
CREATE TABLE IF NOT EXISTS reference_sequence (
    ref_id       TEXT PRIMARY KEY,
    accession    TEXT,
    taxon        TEXT NOT NULL,
    class_key    TEXT,
    locus        TEXT NOT NULL,
    length_bp    INTEGER,
    source       TEXT NOT NULL,
    retrieved_utc TEXT,
    md5          TEXT
);

-- §8.4 deposition policy decisions, recorded per sequence so the policy is
-- demonstrable rather than merely stated.
CREATE TABLE IF NOT EXISTS deposition (
    voucher_id   TEXT NOT NULL REFERENCES voucher(voucher_id),
    locus        TEXT NOT NULL,
    decision     TEXT NOT NULL CHECK (decision IN ('deposit','withhold')),
    rationale    TEXT,
    public_coverage INTEGER,
    decided_utc  TEXT,
    PRIMARY KEY (voucher_id, locus)
);

CREATE TABLE IF NOT EXISTS audit (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc     TEXT NOT NULL,
    actor      TEXT,
    action     TEXT NOT NULL,
    subject    TEXT,
    detail     TEXT
);

CREATE INDEX IF NOT EXISTS ix_barcode_voucher ON barcode(voucher_id);
CREATE INDEX IF NOT EXISTS ix_spectrum_voucher ON spectrum(voucher_id);
CREATE INDEX IF NOT EXISTS ix_cert_status ON certificate(status);
CREATE INDEX IF NOT EXISTS ix_ref_locus_taxon ON reference_sequence(locus, taxon);
"""


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ==========================================================================
# Connection and schema
# ==========================================================================
def connect(path: str, fresh: bool = False) -> sqlite3.Connection:
    """Open (creating if needed) the reference database and apply the schema."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if fresh and os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def log(conn: sqlite3.Connection, action: str, subject: str = "",
        detail: Any = None, actor: str = "pipeline") -> None:
    conn.execute(
        "INSERT INTO audit (ts_utc, actor, action, subject, detail) VALUES (?,?,?,?,?)",
        (_utc(), actor, action, subject,
         json.dumps(detail, default=str) if detail is not None else None))


# ==========================================================================
# Writing
# ==========================================================================
def add_voucher(conn: sqlite3.Connection, v: Dict[str, Any],
                generalise_km: float = 5.0) -> str:
    """
    Insert a voucher, computing its public (generalised) coordinates at write
    time rather than at export time.

    Doing it here is the safer order. §13.10 caps published precision at 5 km;
    if generalisation happened only on the export path, one export written in a
    hurry would publish exact collection points for a species whose locations
    have commercial and conservation sensitivity, and no later correction
    retrieves them.
    """
    # ~111 km per degree of latitude; longitude scaled by cos(lat).
    step_lat = generalise_km / 111.0
    lat, lon = float(v["lat"]), float(v["lon"])
    step_lon = generalise_km / max(111.0 * float(np.cos(np.radians(lat))), 1e-6)

    conn.execute(
        """INSERT OR REPLACE INTO voucher
           (voucher_id, site_key, season, lat, lon, lat_public, lon_public,
            collected_utc, sterile, field_call, collector, permit_ref, release_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (v["voucher_id"], v["site_key"], v["season"], lat, lon,
         round(round(lat / step_lat) * step_lat, 4),
         round(round(lon / step_lon) * step_lon, 4),
         v.get("collected_utc", _utc()), int(bool(v.get("sterile", True))),
         v.get("field_call"), v.get("collector", "Phase 0 field team"),
         v.get("permit_ref"), v.get("release_id")))
    return v["voucher_id"]


def add_barcode(conn: sqlite3.Connection, voucher_id: str, locus: str,
                sequence: str, qc: Dict[str, Any], source: str = "sanger") -> str:
    bid = f"{voucher_id}:{locus}"
    conn.execute(
        """INSERT OR REPLACE INTO barcode
           (barcode_id, voucher_id, locus, sequence, length_bp, mean_phred,
            qc_pass, qc_reasons, md5, source) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (bid, voucher_id, locus, sequence, len(sequence), qc.get("mean_phred"),
         int(bool(qc.get("pass"))), json.dumps(qc.get("reasons", [])),
         hashlib.md5(sequence.encode()).hexdigest(), source))
    return bid


def add_certificate(conn: sqlite3.Connection, cert: Dict[str, Any],
                    pipeline_ver: str = "2.0.0") -> None:
    conn.execute(
        """INSERT OR REPLACE INTO certificate
           (voucher_id, status, certified_taxon, certified_class, proposed_taxon,
            confidence, loci_used, n_loci_agreeing, reasons, detail_json,
            adjudicated_utc, pipeline_ver)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cert["voucher_id"], cert["status"], cert.get("certified_taxon"),
         cert.get("certified_class"), cert.get("proposed_taxon"),
         cert.get("confidence"), json.dumps(cert.get("loci_used", [])),
         cert.get("n_loci_agreeing", 0), json.dumps(cert.get("reasons", [])),
         json.dumps(cert.get("per_locus", {}), default=str), _utc(), pipeline_ver))


def add_spectrum(conn: sqlite3.Connection, voucher_id: str, kind: str,
                 wavelengths: Sequence[float], reflectance: Sequence[float],
                 **meta) -> str:
    wl = np.asarray(wavelengths, dtype=np.float32)
    rf = np.asarray(reflectance, dtype=np.float32)
    sid = f"{voucher_id}:{kind}:{meta.get('season', 'na')}"
    conn.execute(
        """INSERT OR REPLACE INTO spectrum
           (spectrum_id, voucher_id, kind, instrument, season, solar_zenith,
            view_zenith, canopy_fraction, wavelengths, reflectance, n_bands, measured_utc)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, voucher_id, kind, meta.get("instrument", "field spectroradiometer"),
         meta.get("season"), meta.get("solar_zenith"), meta.get("view_zenith"),
         meta.get("canopy_fraction"), wl.tobytes(), rf.tobytes(), int(rf.size),
         meta.get("measured_utc", _utc())))
    return sid


def add_reference_sequences(conn: sqlite3.Connection, records: Iterable[Any]) -> int:
    n = 0
    for r in records:
        conn.execute(
            """INSERT OR REPLACE INTO reference_sequence
               (ref_id, accession, taxon, class_key, locus, length_bp, source,
                retrieved_utc, md5) VALUES (?,?,?,?,?,?,?,?,?)""",
            (f"{r.source}:{r.locus}:{r.id}", r.accession, r.taxon, r.class_key,
             r.locus, len(r.seq), r.source, _utc(),
             hashlib.md5(r.seq.encode()).hexdigest()))
        n += 1
    return n


def read_spectrum(row: sqlite3.Row) -> Dict[str, np.ndarray]:
    return {"wavelengths": np.frombuffer(row["wavelengths"], dtype=np.float32),
            "reflectance": np.frombuffer(row["reflectance"], dtype=np.float32)}


# ==========================================================================
# Releases
# ==========================================================================
def content_checksum(conn: sqlite3.Connection) -> str:
    """
    SHA-256 over the *content* of the scientific tables, in a defined order.

    Not over the file. SQLite rewrites pages on vacuum, on index rebuild, and on
    a version upgrade, so a file hash changes when nothing scientific has. A
    licensee needs to verify that the rows they hold are the rows they were sold,
    and this is the quantity that answers that question.
    """
    h = hashlib.sha256()
    queries = [
        "SELECT voucher_id, site_key, season, lat, lon, sterile, field_call FROM voucher ORDER BY voucher_id",
        "SELECT barcode_id, locus, md5, qc_pass FROM barcode ORDER BY barcode_id",
        "SELECT voucher_id, status, certified_taxon, confidence FROM certificate ORDER BY voucher_id",
        "SELECT spectrum_id, kind, n_bands FROM spectrum ORDER BY spectrum_id",
        "SELECT ref_id, taxon, locus, md5 FROM reference_sequence ORDER BY ref_id",
    ]
    for q in queries:
        for row in conn.execute(q):
            h.update(("|".join("" if v is None else str(v) for v in tuple(row))).encode())
        h.update(b"##")
    return h.hexdigest()


def create_release(conn: sqlite3.Connection, cfg: Dict[str, Any],
                   note: str = "", pipeline_ver: str = "2.0.0") -> Dict[str, Any]:
    """
    Freeze the current contents as an identified, checksummed release.

    The version string carries the date and a checksum prefix, so two releases
    made on the same day from different data are distinguishable by eye — which
    matters when a report says "trained on v1.3" and someone has to find it.
    """
    rd = cfg["reference_database"]
    n_v = conn.execute("SELECT COUNT(*) FROM voucher").fetchone()[0]
    n_c = conn.execute("SELECT COUNT(*) FROM certificate WHERE status='certified'").fetchone()[0]
    n_q = conn.execute("SELECT COUNT(*) FROM certificate WHERE status='quarantined'").fetchone()[0]
    prior = conn.execute("SELECT COUNT(*) FROM release").fetchone()[0]

    chk = content_checksum(conn)
    version = f"{rd['release_prefix']}-v{prior + 1}.0"
    release_id = f"{version}+{dt.date.today().isoformat()}.{chk[:6]}"

    conn.execute(
        """INSERT OR REPLACE INTO release
           (release_id, version, created_utc, schema_version, pipeline_ver,
            n_vouchers, n_certified, n_quarantined, content_sha256, note)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (release_id, version, _utc(), int(rd["schema_version"]), pipeline_ver,
         n_v, n_c, n_q, chk, note))
    conn.execute("UPDATE voucher SET release_id = ? WHERE release_id IS NULL", (release_id,))
    conn.execute("UPDATE certificate SET release_id = ? WHERE release_id IS NULL", (release_id,))
    log(conn, "create_release", release_id,
        {"n_vouchers": n_v, "n_certified": n_c, "n_quarantined": n_q})
    conn.commit()

    return {"release_id": release_id, "version": version, "content_sha256": chk,
            "n_vouchers": n_v, "n_certified": n_c, "n_quarantined": n_q,
            "created_utc": _utc(), "note": note}


# ==========================================================================
# The gate  (§3.4 "Release")
# ==========================================================================
def training_label_set(conn: sqlite3.Connection,
                       release_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    The certified label set — the ONLY thing permitted to train a classifier.

    This function is §3.4's release row expressed as a control rather than a
    policy: quarantined vouchers are structurally unreachable through it, so a
    training stage that calls it cannot accidentally include an uncertified
    specimen no matter how the calling code is written.
    """
    q = ("SELECT v.voucher_id, v.site_key, v.season, v.lat, v.lon, v.sterile, "
         "       v.field_call, c.certified_taxon, c.certified_class, c.confidence, "
         "       c.n_loci_agreeing, c.loci_used "
         "FROM certificate c JOIN voucher v USING (voucher_id) "
         "WHERE c.status = 'certified'")
    args: List[Any] = []
    if release_id:
        q += " AND c.release_id = ?"
        args.append(release_id)
    return [dict(r) for r in conn.execute(q + " ORDER BY v.voucher_id", args)]


def quarantine_report(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Everything the gate refused, and why.

    §13.5 keeps these rather than discarding them because the set of specimens
    that cannot be identified molecularly is a measurement, not a loss: it is the
    direct quantification of Risk 10 (loci lacking resolution between the
    confusable taxa) and the evidence base for escalating specific specimens to
    genome skimming.
    """
    rows = [dict(r) for r in conn.execute(
        "SELECT voucher_id, proposed_taxon, confidence, reasons, loci_used "
        "FROM certificate WHERE status='quarantined' ORDER BY voucher_id")]
    tally: Dict[str, int] = {}
    for r in rows:
        for reason in json.loads(r["reasons"] or "[]"):
            key = reason.split(":")[0].split("—")[0].strip()
            tally[key] = tally.get(key, 0) + 1
    return {"n_quarantined": len(rows), "reason_counts":
            dict(sorted(tally.items(), key=lambda kv: -kv[1])), "vouchers": rows}


# ==========================================================================
# Integrity
# ==========================================================================
def integrity_check(conn: sqlite3.Connection, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Structural and policy checks, run before any release is published.

    ``critical`` failures are ones that would let wrong science out of the door;
    ``warnings`` are ones that make the asset less valuable but not incorrect.
    Keeping the two apart is what lets this be run in CI without being ignored.
    """
    critical: List[str] = []
    warnings: List[str] = []

    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk:
        critical.append(f"{len(fk)} foreign-key violation(s)")

    orphan_bc = conn.execute(
        "SELECT COUNT(*) FROM barcode WHERE voucher_id NOT IN (SELECT voucher_id FROM voucher)"
    ).fetchone()[0]
    if orphan_bc:
        critical.append(f"{orphan_bc} barcode(s) with no voucher")

    # THE control: a certified voucher whose certificate names no taxon would
    # silently enter a training set carrying a null label.
    bad_cert = conn.execute(
        "SELECT COUNT(*) FROM certificate WHERE status='certified' AND "
        "(certified_taxon IS NULL OR certified_class IS NULL OR certified_class='')"
    ).fetchone()[0]
    if bad_cert:
        critical.append(f"{bad_cert} certified voucher(s) with no usable taxon/class")

    min_conf = float(cfg["molecular"]["release"]["min_confidence"])
    weak = conn.execute(
        "SELECT COUNT(*) FROM certificate WHERE status='certified' AND confidence < ?",
        (min_conf,)).fetchone()[0]
    if weak:
        critical.append(f"{weak} certified voucher(s) below the §13.5 confidence gate "
                        f"({min_conf}) — the release gate has been bypassed")

    if cfg["molecular"]["voucher_plan"].get("paired_spectra_required", True):
        no_spec = conn.execute(
            "SELECT COUNT(*) FROM certificate c WHERE c.status='certified' AND "
            "c.voucher_id NOT IN (SELECT voucher_id FROM spectrum)").fetchone()[0]
        if no_spec:
            warnings.append(f"{no_spec} certified voucher(s) have no paired spectra — "
                            "these are herbarium specimens, not rows in the asset (§13.6)")

    # Population coverage: a species represented from one site cannot support
    # grouped cross-validation, which §5.1(6) requires the unit of correlation
    # (the site) to define.
    min_sites = int(cfg["molecular"]["voucher_plan"]["min_sites_per_species"])
    for r in conn.execute(
        "SELECT c.certified_class AS k, COUNT(DISTINCT v.site_key) AS n "
        "FROM certificate c JOIN voucher v USING (voucher_id) "
        "WHERE c.status='certified' GROUP BY c.certified_class"):
        if r["n"] < min_sites:
            warnings.append(f"class {r['k']} certified from {r['n']} site(s); "
                            f"§13.6 asks for >= {min_sites} for grouped CV")

    return {"ok": not critical, "critical": critical, "warnings": warnings,
            "checked_utc": _utc()}


# ==========================================================================
# Licensing and valuation  (§7.1, §7.2)
# ==========================================================================
def licence_manifest(conn: sqlite3.Connection, cfg: Dict[str, Any],
                     tier: str) -> Dict[str, Any]:
    """
    What a licensee at ``tier`` actually receives, and — more usefully — what
    they do not.

    The withheld list is the commercial substance. §7.1: "Contracts must reserve
    database ownership to us while granting the client unlimited use of derived
    maps and reports ... it is the single most important commercial term in the
    agreement." A manifest that states the boundary explicitly is what makes that
    term negotiable at signature rather than disputed later.
    """
    tiers = cfg["reference_database"]["licence_tiers"]
    if tier not in tiers:
        raise KeyError(f"unknown licence tier {tier!r}; have {sorted(tiers)}")
    spec = tiers[tier]

    all_tables = ["voucher", "barcode", "certificate", "spectrum",
                  "reference_sequence", "deposition", "release", "audit"]
    granted = all_tables if spec["tables"] == "all" else list(spec["tables"])
    withheld = [t for t in all_tables if t not in granted]

    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in granted}

    notes = []
    if spec.get("spectra") == "aggregate_only":
        notes.append("Spectra supplied as per-class means and covariances only; "
                     "individual voucher spectra and their coordinates are withheld.")
    if "voucher" in granted:
        notes.append(f"Coordinates generalised to "
                     f"{cfg['molecular']['deposition']['coordinate_generalisation_km']} km (§13.10).")
    if "spectrum" not in granted:
        notes.append("The sequence-to-spectrum linkage — the asset itself (§7.1, §8.4) "
                     "— is not included at this tier.")

    return {"tier": tier, "tables_granted": granted, "tables_withheld": withheld,
            "row_counts": counts, "spectra": spec.get("spectra"),
            "price_hkd_per_year": spec.get("price_hkd_per_year"), "notes": notes}


def valuation(conn: sqlite3.Connection, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replacement cost of the database — the basis for §7.1's pricing floor.

    Deliberately a *replacement* cost, not a discounted-cash-flow or a
    revenue multiple. §7.1's argument is that a competitor with a better sensor
    still needs the seasons: "the replacement cost of a multi-season,
    barcode-verified, HK-specific reference set is several years and several
    million dollars, regardless of how good a competitor's sensor is."

    The calendar-time term is the part that cannot be bought out of. Two seasons
    of phenology take two seasons; a rival with twice the budget can field two
    crews and halve the field days, but cannot make October come sooner. The
    money is a floor on price; the time is the actual moat.
    """
    val = cfg["reference_database"]["valuation"]
    n_cert = conn.execute("SELECT COUNT(*) FROM certificate WHERE status='certified'").fetchone()[0]
    n_total = conn.execute("SELECT COUNT(*) FROM voucher").fetchone()[0]
    n_spec = conn.execute("SELECT COUNT(*) FROM spectrum").fetchone()[0]
    n_seasons = conn.execute("SELECT COUNT(DISTINCT season) FROM voucher").fetchone()[0]
    n_sites = conn.execute("SELECT COUNT(DISTINCT site_key) FROM voucher").fetchone()[0]

    # Field cost is driven by vouchers ATTEMPTED, not vouchers certified: the
    # quarantined ones cost exactly the same to collect. Costing only the
    # survivors would understate replacement by the quarantine rate, which is
    # precisely the rate a newcomer cannot predict in advance.
    field_days = n_total / max(float(val["vouchers_per_field_day"]), 1e-9)
    field_cost = field_days * float(val["field_day_hkd"])

    m = cfg["molecular"]["costs_hkd"]
    n_loci = len(cfg["molecular"]["loci"])
    lab_per_voucher = (m["extraction_per_sample"] + n_loci * m["pcr_per_reaction"]
                       + n_loci * 2 * m["sanger_per_reaction"])
    lab_cost = n_total * lab_per_voucher

    subtotal = field_cost + lab_cost
    total = subtotal * float(val["overhead_multiplier"])

    seasons_needed = max(int(val["seasons_required"]), 1)
    years = (seasons_needed / 2.0) * float(val["years_to_replicate_multiplier"])

    return {
        "n_vouchers": n_total, "n_certified": n_cert, "n_spectra": n_spec,
        "n_seasons": n_seasons, "n_sites": n_sites,
        "field_days_equivalent": round(field_days, 1),
        "field_cost_hkd": round(field_cost),
        "lab_cost_per_voucher_hkd": round(lab_per_voucher),
        "lab_cost_hkd": round(lab_cost),
        "overhead_multiplier": val["overhead_multiplier"],
        "replacement_cost_hkd": round(total),
        "calendar_years_to_replicate": round(years, 2),
        "licence_price_range_hkd_per_year":
            cfg["reference_database"]["licence_tiers"]["consultancy"]["price_hkd_per_year"],
        "note": (
            "Replacement cost of the CURRENT contents at Phase 0 scale. It is not the "
            "value of the finished asset: §7.1's 'several million dollars' describes a "
            "multi-year archive, and this database holds one campaign. The figure grows "
            "with every contract year, which is the §6.1(4) argument in numeric form."),
    }


def summary(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Row counts and composition — what the platform's asset page displays."""
    def rows(q, args=()):
        return [dict(r) for r in conn.execute(q, args)]

    return {
        "counts": {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                   for t in ("voucher", "barcode", "certificate", "spectrum",
                             "reference_sequence", "release", "deposition")},
        "by_class": rows("SELECT certified_class AS class_key, COUNT(*) AS n "
                         "FROM certificate WHERE status='certified' "
                         "GROUP BY certified_class ORDER BY n DESC"),
        "by_status": rows("SELECT status, COUNT(*) AS n FROM certificate GROUP BY status"),
        "by_site": rows("SELECT site_key, COUNT(*) AS n FROM voucher GROUP BY site_key ORDER BY n DESC"),
        "by_season": rows("SELECT season, COUNT(*) AS n FROM voucher GROUP BY season"),
        "barcodes_by_locus": rows("SELECT locus, COUNT(*) AS n, "
                                  "SUM(qc_pass) AS n_qc_pass FROM barcode GROUP BY locus"),
        "references_by_locus": rows("SELECT locus, COUNT(*) AS n, COUNT(DISTINCT taxon) AS n_taxa "
                                    "FROM reference_sequence GROUP BY locus"),
        "releases": rows("SELECT release_id, version, created_utc, n_vouchers, n_certified, "
                         "n_quarantined, content_sha256 FROM release ORDER BY created_utc DESC"),
    }


__all__ = [
    "connect", "log", "add_voucher", "add_barcode", "add_certificate",
    "add_spectrum", "add_reference_sequences", "read_spectrum",
    "content_checksum", "create_release", "training_label_set",
    "quarantine_report", "integrity_check", "licence_manifest", "valuation",
    "summary", "SCHEMA",
]
