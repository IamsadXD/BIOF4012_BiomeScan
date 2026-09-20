# Improvements and next steps

Where this implementation is weak, what to fix in what order, and what the
venture should do next. Written against the state after stage 16, with every
claim checked against the code rather than remembered.

Effort estimates are for someone already familiar with the repo.

---

## 0. Housekeeping — the repository moved

The project now lives at `/Users/james/Downloads/mikania` (it was under
`DeepHyperX/`). Everything works from the new location, but two things are stale:

| Item | State | Action |
|---|---|---|
| `.venv/pyvenv.cfg` | `command =` still records the old path | Cosmetic — the venv runs fine. Recreate only if you ever `python -m venv --upgrade` |
| Project `CLAUDE.md` | **None at the new location** | Write one (~20 lines): what the repo is, the two tracks, `run_all.sh`, don't-touch list |
| README's proposal link | `../AFCD_..._Proposal.md` | Now *more* correct than before — the proposal sits alongside |

One genuine benefit of the move: this is no longer a subdirectory of an unrelated
hyperspectral project, so the "no venv here, system python3 is 3.14" hazard in
`DeepHyperX/CLAUDE.md` no longer applies to it. It has its own venv on 3.14.3.

---

## 1. Implementation improvements

### P0 — do these before any real data arrives

#### P0.1 The release gate is implemented but not *enforced* in the training path

**This is the most important gap in the repository.**

`refdb.training_label_set()` returns certified vouchers and nothing else, and
stage 14 demonstrates it. But `scripts/04_train_validate.py` — the stage that
actually trains the classifier — trains on **simulated scene ground truth** and
never calls it. Verified: no reference to `training_label_set` or `refdb` in
stage 04.

That is defensible today (there are no real vouchers to gate), and it is exactly
the seam where an uncertified label will enter the moment there are. The whole
molecular layer exists to close it.

**Fix:**
- add `--labels-from-db <RELEASE_ID>` to stage 04, pulling labels via
  `training_label_set()`;
- record the release id on the saved model artefact
  (`outputs/models/operational_model.joblib`);
- extend `refdb.integrity_check` with a `critical` failure if a reported
  accuracy has no release id attached.

**Effort:** ~half a day. **Value:** highest in the repo — it converts the
control from demonstrated to enforced.

#### P0.2 There is no test suite, and this codebase specifically needs one

Verified: no `tests/` directory, no `test_*.py`.

That matters more here than in an average project, because **almost every bug hit
during development produced plausible-but-wrong output rather than an
exception**. A silent-wrongness bug is invisible to "did it run?"

Write regression tests for the ones already found — each is a one-liner to assert
and each cost real time to diagnose:

| Test | Guards against |
|---|---|
| FASTA round-trip preserves binomials | space-delimited deflines collapsing *M. micrantha* → "Mikania" |
| `align()` on identical / 5% subs / internal fragment / 20 bp indel / unrelated | semi-global alignment reporting 100% identity over 4 columns |
| `neighbour_joining()` recovers the textbook Saitou–Nei topology | silent topology errors |
| `place_query()` support = 1.0 on a clean two-species set | rooting-dependent clade reading |
| `curate_references()`: single outlier flagged; two-cluster keeps the **majority**; non-comparable **not** flagged | all three curation iterations that were wrong |
| `barcode_gap()` strict vs robust on a constructed set | one bad pair sinking a locus |
| `corrupt_labels()` block coherence — all pixels of a specimen share one label | per-pixel corruption reversing the Risk 9 conclusion |
| `refdb`: gate excludes quarantined; checksum stable across `VACUUM`; coordinates generalised on insert | gate bypass, file-hash drift |
| `band_prior_weights()` mean = 1.0, min ≥ floor | prior silently zeroing bands |

**Effort:** 1–2 days. **Value:** very high.

#### P0.3 `config._validate()` ignores §13 and §14

Verified: no reference to `molecular` or `reference_database` in
`mikania/config.py`. A typo in the molecular block currently fails deep inside
stage 12, or worse, silently changes a threshold.

Add checks: locus keys unique and `discrimination_rank` present;
`release.min_loci_agreeing` ≤ number of loci; identity/coverage thresholds in
[0,1]; licence tiers naming real tables; `valuation` fields present.

**Effort:** 1–2 hours. **Value:** high — the config *is* the science here.

#### P0.4 NCBI politeness parameters are placeholders

`config/default.yaml:727` still reads `email: "afcd-phase0@example.org"`. NCBI
blocks by IP for unattributed bulk use. Set a real address and tool name, and add
an optional `api_key` (raises the limit from 3 to 10 requests/second).

**Effort:** 15 minutes.

### P1 — before the first real vouchers

| # | Improvement | Why | Effort |
|---|---|---|---|
| P1.1 | **Affine gap penalties** in `align()` | Currently linear. trnH-psbA has genuine length variation and mononucleotide repeats — exactly where linear gaps mis-score. Implementable with the same max-plus prefix scan applied to the `Iy` recurrence | ~half day |
| P1.2 | **`.ab1` / ABIF trace reader** | `qc_check` already consumes a `phred` array; real Sanger output is `.ab1`. Without this the SOP's stage 4 has no input path | 1 day |
| P1.3 | **MAFFT shell-out with star-alignment fallback** | The star alignment drops insertions relative to the anchor — declared, but real for ITS2/trnH-psbA. Use MAFFT when present, keep the fallback so the laptop-reproducible property survives | ~half day |
| P1.4 | **Reference-set bootstrap** alongside the site bootstrap | Current support means "the alignment columns support this", not "the database sampling does". For a taxon with three submissions the second is the larger uncertainty — and the module already says so without measuring it | ~half day |
| P1.5 | **Cache pairwise distances** | Stage 12 computes them twice (curation, then gap analysis). Roughly halves the stage's runtime | 1 hour |
| P1.6 | **Schema migration path** | `schema_version` is recorded but there is no migration code. The first schema change will orphan existing releases | ~half day |

### P2 — scale and polish

- **Stage 12 is O(n²) alignments.** Fine at 185 references; it will not survive
  a few thousand. Add the k-mer prefilter (already written for
  `similarity_search`) to the all-pairs step, or band the DP.
- **Specimen-level grouped CV.** Validation is currently leave-one-*site*-out.
  Once real vouchers exist, the specimen is a finer unit of correlation and
  should be the CV group — the same §5.1(6) argument, one level down.
- **Platform**: certificate list is capped at 24 with no search or filter; the
  release has no download link.
- **Chimera detection** is a halves check — it will not catch a chimera between
  two similar parents. Acceptable (such a chimera gives the same species call),
  but worth stating in the SOP rather than only in the code.

---

## 2. What turns "modelled" into "measured"

Three data unlocks, in order of how much they change the answer. Everything
currently caveated resolves through one of them.

### 2.1 Field spectroradiometer data — the big one

**Unlocks:** the central unknown. Species contrasts in the stage-02 library are
modelled; stage 05 sweeps them and reports the required contrast (≈0.42 on the
nominal scale) rather than asserting a number.

**What to do:** drop CSVs into `data/raw/field_spectra/`; the v1.0 code path
already exists. Re-run stages 02 → 10.

**What becomes real:** the eight falsification verdicts; the separability audit;
where Hong Kong sits on the contrast curve — i.e. whether there is a product.

**Measure these first** (stage 00's operational ranking, confirmed by stage 10):

| Priority | Feature | Window | Measured effect |
|---|---|---|---|
| 1 | Red-edge **position** | 680–760 nm | d = +1.01, SUPPORTED |
| 2 | Water band depth | 950–1000 nm | d = −1.09, SUPPORTED |
| 3 | Red-edge derivative shape | 690–750 nm | d = −0.57, SUPPORTED |
| — | **NIR plateau amplitude** | 780–900 nm | d = −0.00. **Do not spend the campaign on it** |

And obey the two constraints the desk study derived *before* any measurement:
**A1** fixed solar-time window; **A2** measure out of bloom (two of eight
predictions reverse sign in flower).

### 2.2 Real vouchers with traces

**Unlocks:** the one thing stage 12's design structurally cannot test. Vouchers
there pair independent GenBank accessions of the same species, so the pipeline is
never shown a specimen whose loci genuinely disagree — hybridisation,
introgression, a contaminated reaction. That is precisely what quarantine exists
for.

**Needs:** P1.2 (`.ab1` reader) first.

### 2.3 AFCD removal records

**Unlocks:** §5.1(2)'s concordance measurement against *operational* records
rather than modelled field calls. Appendix B.14 is right that this could equally
reveal the records are too noisy to guide site selection — which is itself worth
knowing, and is a finding AFCD has never had.

**Cost:** a conversation. It is proposal §10 action 1 for a reason.

---

## 3. Next steps for the venture

### Now — free, no counterparty (1–2 weeks)

1. **Apply the proposal edits** in [`10_solutions_guide.md`](10_solutions_guide.md):
   §3.4 (validation-first certification), §9 Risk 9 (direction), §3.3(a)
   (narrowed claim), Appendix B.9 (measured, false), §7.3 (kill criterion on
   certified labels only). Costs nothing and removes three claims an evaluator
   would test and break.
2. **Resolve the desk-answerable [VERIFY]s.** §3.3 *M. cordata* is already
   resolved (1 HK record, 1991, unverified). Remaining: CAD SUA provisions,
   sensor swath at 90 m AGL, current ECF round.
3. **Do P0.1–P0.4** above.

### Months 1–2 — access before equipment

Proposal §10 is emphatic that the first commercial ask precedes any purchase, and
nothing found here changes that.

4. **AFCD, via Country and Marine Parks Branch** — removal records *and*
   herbarium access for *M. cordata* material (the HK$510 gap needs a loan, not
   a field trip; the plant does not grow here).
5. **Laboratory access in writing** (§10.8). Do not build a wet lab — §9 Risk 12.
6. **Real sequencing quotations** to replace the modelled §13.9 figures.
7. **Settle the deposition policy** before any sequence exists (§8.4).

### Months 3–8 — two field seasons

8. **Split the voucher plan** into validation and training targets. This is the
   single highest-leverage change to the Phase 0 design: certifying 100% of
   *training* vouchers leaves the go/no-go decision a coin flip; certifying 50%
   of *validation* vouchers makes it reliable.
9. **Certify validation exhaustively**; spend the remainder on
   disagreement-ranked training specimens (89% of errors for 30% of sequencing).
10. **Record field calls blind**, before any lab result. The concordance
    measurement is worthless if the call can be revised afterwards.
11. **Both seasons.** Non-negotiable per constraint A2.

### Months 6–10 — analysis and the decision

12. Re-run stages 02, 10, 12, 13, 16 against real data.
13. **Evaluate the kill criterion against barcode-certified validation labels
    only.** Without that, there is a ~58% chance of a wrong verdict.

---

## 4. Decision gates — what should stop this

Unchanged from the proposal, with one addition:

| Gate | Trigger | Timing |
|---|---|---|
| **1. Separability** | Field-measured contrast below ≈0.42 on the stage-05 scale, i.e. Mikania-vs-native below ~75% | After the ground campaign, **before** aerial spend |
| **2. Mechanism** | Predicted spectral features absent from the ground library **in both seasons** | Same |
| **3. Decision validity** *(new)* | The kill criterion is being read off uncertified labels | Continuously — this is a process gate, not a data gate |

Gate 3 is the addition this work produced. Gates 1 and 2 are only meaningful if
the labels they are computed against are certified; otherwise the programme is
measuring its field team rather than its classifier, and stage 13 measured how
often that goes wrong.

---

## 5. Honest assessment of what has and has not been shown

**Shown, on real data:**
- Public barcode reference coverage, and that it fails for *M. cordata*
- Barcode gaps per locus, including that rbcL cannot separate the *Mikania*
  congeners
- That the §3.4 pipeline makes no wrong calls on a real answer key (8/8, 14
  refused)
- That seven public reference records disagree with their own species
- That *M. cordata* is effectively absent from Hong Kong

**Shown, on modelled data — direction reliable, magnitude not:**
- Label error depresses rather than inflates apparent accuracy
- Certifying validation rather than training repairs the go/no-go decision
- Disagreement ranking concentrates label errors
- The genomic prior does not improve the classifier

**Not shown at all:**
- Whether Mikania is separable from native climbers in real Hong Kong canopy.
  That is the central assumption (Appendix B.5), it is what Phase 0 exists to
  test, and no amount of further engineering substitutes for the field campaign.

The last line is the one to keep in view. The molecular layer makes the Phase 0
answer *trustworthy*; it does not make it *favourable*.
