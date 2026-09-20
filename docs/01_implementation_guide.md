# Implementation guide — molecular layer

Everything needed to run, understand, extend or audit the v2.0 molecular
workstream.

## 1. Install and run

```bash
cd mikania
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
./run_all.sh                 # everything, 00 → 15
```

Useful variants:

| Command | Effect |
|---|---|
| `./run_all.sh --fast` | skips the contrast sweep (stage 05), most of the runtime |
| `./run_all.sh --no-fetch` | reuse cached downloads; stage 11 runs in `--offline` mode |
| `./run_all.sh --no-molecular` | v1.0 scope only — stages 00–08 and 15 |

The molecular stages alone, in order:

```bash
.venv/bin/python scripts/00_genomic_desk_study.py        # no data needed at all
.venv/bin/python scripts/10_test_genomic_predictions.py  # needs stage 02
.venv/bin/python scripts/11_fetch_barcode_references.py  # ~185 seqs from NCBI
.venv/bin/python scripts/12_barcode_verify_vouchers.py   # ~3 min (all-pairs alignment)
.venv/bin/python scripts/13_label_error_propagation.py   # needs stage 03
.venv/bin/python scripts/14_reference_database.py        # needs stage 12
.venv/bin/python scripts/15_export_platform.py           # rebuild the browser bundle
```

Then:

```bash
.venv/bin/python platform/server.py
```

→ <http://127.0.0.1:8790>, views 09–12 are the molecular layer.

Stage 00 is deliberately first and deliberately free: proposal §10 action 0 is
the only item on the next-actions list that needs no data, no capital and nobody
else's cooperation. It runs on a laptop on a plane and it determines what the
HK$400–500k field campaign should measure.

## 2. Stage map

| Stage | Script | Proposal § | Depends on | Produces |
|---|---|---|---|---|
| 00 | `00_genomic_desk_study.py` | §3.3, §10.0 | — | `genomic_priors.json`, `band_prior_weights.json` |
| 10 | `10_test_genomic_predictions.py` | §3.2, §3.3(c) | 00, 02 | `genomic_validation.json` |
| 11 | `11_fetch_barcode_references.py` | §4.2, B.9 | — | `barcode_refs/*.fasta`, `barcode_reference_coverage.json` |
| 12 | `12_barcode_verify_vouchers.py` | §3.4 | 11 | `barcode_verification.json`, `certificates.json` |
| 13 | `13_label_error_propagation.py` | §9 Risk 9 | 03 | `label_error.json` |
| 14 | `14_reference_database.py` | §3.1(4), §7.1, §8.4 | 12, 02 | `reference_db.sqlite`, `reference_database.json` |

## 3. Module map

| Module | Implements | Key entry points |
|---|---|---|
| `mikania/genomics.py` | §3.3 desk study | `desk_study`, `evidence_chain`, `band_prior_weights`, `evaluate_predictions` |
| `mikania/barcode.py` | §3.4 seven-stage pipeline | `quality_trim`, `qc_check`, `identify_locus`, `place_query`, `curate_references`, `barcode_gap`, `adjudicate` |
| `mikania/refdb.py` | §3.1(4), §7.1 | `connect`, `create_release`, `training_label_set`, `integrity_check`, `valuation`, `licence_manifest` |
| `mikania/labelerror.py` | §9 Risk 9 | `corrupt_labels`, `propagate_sweep`, `concordance`, `certification_value` |

## 4. Configuration

Two files, both with provenance comments on every number:

- `config/default.yaml` §13 `molecular:` — loci, QC thresholds, identity and
  margin cutoffs, phylogeny settings, the release gate, the voucher plan, the
  field-error model, reference sources, costs, deposition policy.
- `config/default.yaml` §14 `reference_database:` — path, schema version, licence
  tiers, valuation model.
- `config/genomic_priors.yaml` — the published findings, the trait chains, and
  the spectral predictions, each with a citation, an evidence tier, a **signed**
  direction and a **falsification test**.

No molecular constant lives in code. If a number matters, it is in YAML with a
comment explaining where it came from and whether it is measured, cited, or an
explicit assumption.

## 5. Design decisions worth knowing before you extend it

**Algorithms are implemented, not shelled out.** BLAST, MAFFT and RAxML are the
production tools and `03_barcode_sop.md` names them for real laboratory use. They
are not used here because the repository has to run end to end from
`pip install -r requirements.txt` with no bioinformatics stack and no compiled
binaries — the same constraint that produced a stdlib-only platform server. The
methods implemented are the standard ones (Needleman–Wunsch with a linear gap
penalty, Jukes–Cantor distances, neighbour-joining, site bootstrap). Where they
would give a different answer from the production tools, the specimen belongs in
the escalation bucket (§5.4 Risk 10) rather than in a better tree.

**Alignment is vectorised through a max-plus prefix scan.** The within-row
dependency `H[i][j] = max(D[i][j], H[i][j-1] + g)` is normally sequential; with a
linear gap penalty it resolves to `j*g + cummax(D[i][k] - k*g)`, so each row costs
a handful of numpy operations instead of a Python loop. ~11 ms for a 700×700
alignment.

**Alignment is semi-global, with a minimum-overlap guard.** Free end gaps are
required — a trimmed 250 bp ITS2 read must not be punished against a 700 bp
GenBank submission spanning ITS1–5.8S–ITS2. But free end gaps let an alignment
stop early and report 100% identity over four columns, so identity is returned as
zero below 50 aligned columns.

**Distances are direct pairwise, not projected through a star alignment.** An
earlier version anchored on the longest sequence; GenBank holds 268 bp fragments
alongside 1,722 bp full-gene records for the same locus, and projecting through a
long anchor put two sequences with 100.0% direct identity at a Jukes–Cantor
distance of 0.262. Star alignment is retained only for phylogenetic placement,
which needs columns for the bootstrap, and there the anchor is the **medoid**.

**Placement reads bipartitions, not rooted clades.** An NJ tree is unrooted and
the "root" this implementation produces is wherever the join loop stopped, so
"the smallest clade containing the query" depends on join order. Reading each
internal edge as a split and taking the smallest side containing the query is
rooting-invariant. Getting this wrong gave a correct placement 0.32 bootstrap
support with 0.62 for the wrong species; after the fix, 1.00.

**Label corruption operates on specimen blocks, not pixels.** A surveyor
identifies one vine and that judgement propagates to every pixel of the polygon
drawn around it. Independent per-pixel flips are zero-mean noise a random forest
averages away — they cannot teach a model anything, because there is nothing
coherent to learn.

**The release gate is a function.** `refdb.training_label_set()` returns certified
vouchers and nothing else, so a training stage cannot include an uncertified
specimen however the calling code is written. A rule in a document is a policy; a
rule in a function signature is a control.

## 6. Extending it

**Real field spectra** — drop CSVs in `data/raw/field_spectra/` (the v1.0 code
path already exists) and re-run stages 02 and 10. The modelled species block is
replaced automatically and the falsification verdicts become real.

**Real vouchers** — write them into the database via `refdb.add_voucher` /
`add_barcode` / `add_spectrum`, then run adjudication. Stage 12's held-out-sequence
harness is a rehearsal; the schema is the production one.

**More loci** — add to `config/default.yaml` §13.1 with a `discrimination_rank`
and an `ncbi_query`. Everything downstream (fetch, coverage matrix, gap analysis,
weighted adjudication) picks it up without code changes.

**A different target species** — replace `references.taxa` and the class scheme.
The pipeline has no Mikania-specific logic outside the config and the priors file.

## 7. Runtime and reproducibility

| Stage | Wall clock |
|---|---|
| 00 | < 2 s |
| 10 | ~40 s |
| 11 | ~2 min (network) |
| 12 | ~3 min (all-pairs alignment) |
| 13 | ~4 min (many classifier fits) |
| 14 | ~10 s |

One seed (`project.random_seed`) drives everything, offset per stage. Verified on
CPython 3.14.3, macOS. Every stage is idempotent; a failed run resumes by
invoking the remaining scripts directly.
