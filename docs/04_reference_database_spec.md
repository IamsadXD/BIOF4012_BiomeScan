# Reference database specification — deliverable 4

**Proposal §3.1 deliverable 4, §7.1.** Implemented in `mikania/refdb.py`, built by
`scripts/14_reference_database.py`, stored at
`data/processed/reference_db.sqlite`.

> §7.1: *"It is not the drone, the sensor, or the classifier — all three are
> purchasable by anyone. It is the molecularly-verified spectral reference
> database of Hong Kong invasive flora ... **That database, not the aircraft, is
> the company's asset.**"*

## Why SQLite and why normalised this way

SQLite because it is in the standard library, is a single file an evaluator can
copy, and gives transactions and referential integrity for free.

Normalised around the **linkage** — voucher → sequence → spectrum → place —
because §8.4 identifies that linkage, not any of its components, as the thing
that must never be published:

> *"**Retain** the paired spectra, the georeferenced metadata and the linkage
> between them; that linkage is the asset (§7.1), and it is not reconstructable
> from public sequence data."*

## Schema (v2)

| Table | Holds | Notes |
|---|---|---|
| `release` | immutable identified snapshots | version, checksum, counts |
| `voucher` | the physical specimen | true *and* generalised coordinates |
| `barcode` | one sequence per voucher per locus | QC verdict and reasons stored |
| `certificate` | the §3.4 adjudication result | one per voucher; `status` is the gate |
| `spectrum` | paired leaf / canopy / airborne spectra | float32 blobs + geometry |
| `reference_sequence` | what the calls were made *against* | provenance; public DBs change |
| `deposition` | §8.4 per-sequence publish/withhold decisions | policy made demonstrable |
| `audit` | event log | who did what, when |

### Three decisions worth explaining

**Coordinates are generalised at write time, not export time.** `add_voucher`
computes `lat_public` / `lon_public` (5 km, config §13.10) on insert. If
generalisation happened only on the export path, one export written in a hurry
would publish exact collection points, and no later correction retrieves them.

**`reference_sequence` exists because public databases change.** A certificate
made against a 2026 GenBank snapshot cannot be re-derived from a 2029 one. Without
this table the certificates are not reproducible, only plausible.

**Quarantined vouchers are retained.** Config §13.5
`quarantine_rather_than_discard`. The set of specimens that cannot be identified
molecularly is the direct measurement of Risk 10, not a loss.

## Releases

```
MIKANIA-REFDB-v1.0+2026-08-11.35d9f5
└── prefix ──┘ └ver┘ └── date ──┘ └sha┘
```

Immutable. Corrections create a new release, so a model trained last year remains
auditable. The version string carries the date and a checksum prefix so two
releases made the same day from different data are distinguishable by eye.

**The checksum is over row content, not the file.** SQLite rewrites pages on
vacuum, on index rebuild and on version upgrade, so a file hash changes when
nothing scientific has. A licensee needs to verify that the rows they hold are
the rows they were sold.

## The release gate

`refdb.training_label_set()` returns certified vouchers **and nothing else**.

This is §3.4's release row expressed as a control rather than a policy:
quarantined vouchers are structurally unreachable through it, so a training stage
that calls it cannot include an uncertified specimen no matter how the calling
code is written.

`refdb.integrity_check()` fails the build on:

- foreign-key violations or orphaned barcodes;
- a certified voucher with no usable taxon/class (would enter training with a
  null label);
- **a certified voucher below the §13.5 confidence gate** — i.e. the gate was
  bypassed.

and warns on: certified vouchers with no paired spectra (§13.6 — a herbarium
specimen, not a row in the asset), and classes certified from fewer sites than
grouped CV needs.

## Licence tiers

| Tier | Tables | Spectra | Price |
|---|---|---|---|
| `academic` | voucher, barcode, certificate | aggregate only | free |
| `consultancy` | + spectrum | full | HK$80k–250k/yr |
| `internal` | all | full | — |

The **withheld** column is the commercial substance. `licence_manifest()` returns
it explicitly, because §7.1 calls database ownership *"the single most important
commercial term in the agreement"* and a manifest that states the boundary is
what makes it negotiable at signature rather than disputed later.

Sequences alone are a public good. Spectra alone are uninterpretable. The **link**
between them, plus its geography, is what took years to build — and it is what
the academic tier does not receive.

## Valuation

`refdb.valuation()` computes **replacement cost**, deliberately — not a DCF or a
revenue multiple. §7.1's argument is that a competitor with a better sensor still
needs the seasons.

```
field days      = vouchers ATTEMPTED / vouchers_per_field_day
field cost      = field days × field_day_hkd
lab cost        = vouchers × (extraction + 4×PCR + 8×Sanger)
replacement     = (field + lab) × overhead_multiplier
calendar years  = (seasons_required / 2) × years_to_replicate_multiplier
```

**Costed on vouchers attempted, not certified.** The quarantined ones cost exactly
the same to collect. Costing only the survivors would understate replacement by
the quarantine rate — which is precisely the rate a newcomer cannot predict.

**Current build:** 22 vouchers → HK$50,309 over 1.0 calendar years.

> That is a Phase 0 rehearsal, not the §7.1 figure. §7.1's "several years and
> several million dollars" describes a multi-year archive; this database holds one
> campaign. The number grows with every contract year, which is §6.1(4) in
> numeric form — *"Year two is worth more than year one ... By year three the
> dataset is the moat."*

**The money is a floor on price; the calendar time is the actual moat.** A rival
with twice the budget can field two crews and halve the field days. They cannot
make October come sooner.

## Extending to real vouchers

The schema is the production one; stage 12's held-out-sequence harness is a
rehearsal of the *process*, not of the *storage*. To load real material:

```python
from mikania import refdb
conn = refdb.connect("data/processed/reference_db.sqlite")
refdb.add_voucher(conn, {...})
refdb.add_barcode(conn, voucher_id, locus, sequence, qc)
refdb.add_spectrum(conn, voucher_id, "leaf", wl, reflectance, season=...)
refdb.add_certificate(conn, adjudicate(...))
refdb.create_release(conn, cfg, note="Phase 0 field campaign, autumn")
```

Run `integrity_check` before every release. It is cheap and it is the only thing
standing between a bypassed gate and a silently corrupted training set.
