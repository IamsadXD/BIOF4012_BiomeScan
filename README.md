# MIKANIA-HSI

**Species-level invasive vine mapping by UAV hyperspectral imaging — reference implementation of the AFCD proposal.**

A complete, runnable pipeline for the business case in
[`../AFCD_Mikania_Hyperspectral_Proposal.md`](../AFCD_Mikania_Hyperspectral_Proposal.md):
detect *Mikania micrantha* in Hong Kong country parks, tell it apart from the
native climbers the Government's own guidance warns against clearing by mistake,
rank the infestations by severity, and measure whether treatment worked.

Fifteen pipeline stages across two tracks — spectral (v1.0) and molecular
(v2.0) — a Python package, a GIS deliverable set, a versioned reference
database, and a browser platform. Real open data where real data exists;
simulated scenes where the survey has not been flown yet — and the boundary
between the two marked everywhere it matters.

The molecular layer implements proposal v2.0: the genomic basis of separability
(§3.3), DNA-barcode certification of the training labels (§3.4), and the
reference database that §7.1 identifies as the company's actual asset. Its
documentation is in [`docs/`](docs/) — start with
[`docs/09_findings_vs_proposal.md`](docs/09_findings_vs_proposal.md), which is
where the implementation contradicts the document it implements.

---

## Quick start

```bash
cd mikania
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
./run_all.sh
.venv/bin/python platform/server.py     # → http://127.0.0.1:8790
```

First run downloads ~85 MB of open data (GBIF records, EcoSIS leaf spectra, one
EO-1 Hyperion scene, 185 barcode reference sequences from NCBI) and takes roughly
25 minutes end to end. `./run_all.sh --fast` skips the contrast sweep, which is
most of that; `--no-molecular` runs the v1.0 spectral track alone.

---

## What it actually establishes

Nine findings, all reproducible from the code. The first five are spectral; the
last four come from the molecular track and three of them **contradict the
proposal**.

**1. The hyperspectral advantage is real but seasonal.**
During the autumn bloom, every sensor tier — including a 3-band RGB camera —
separates Mikania from native climbers essentially perfectly. That is not a flaw
in the model: it *reproduces* the published finding that RGB deep learning works
on blooming outbreak points, and it validates the simulation. The commercial case
lives entirely in the foliage-only case:

| Sensor (foliage only) | Mikania vs native | False positives |
|---|---|---|
| RGB camera | 53.1% | 13.5% |
| 5-band multispectral | 62.0% | 14.5% |
| **VNIR hyperspectral** | **68.7%** | **7.9%** |

Each tier was given the best feature set it can physically compute (the 5-band
sensor gets all 25 pairwise ratios and normalised differences of its bands), and
all three ran through the same classifier under the same site-disjoint validation.

**2. Spatial leakage is enormous, and it is not an artefact of our simulation.**
On the Botswana EO-1 Hyperion scene — real satellite hyperspectral imagery this
project did not generate — random pixel splitting reports **93.7%** where
spatially blocked validation reports **58.9%**. A **+34.8 pp** inflation. This is
the number most published hyperspectral results quote, and proposal §5.1(6) is
right to insist on the alternative.

**3. Three catchments are not enough to clear the kill criterion.**
Leave-one-site-out gives Mikania-vs-native 80.4%, which passes the §7.3 threshold
of 75% — but the 95% confidence interval, bootstrapped over *sites* rather than
pixels, runs 50.8%–98.0%. The point estimate passes; the lower bound does not.
That is the quantitative argument for the multi-site Phase 1.

**4. Seasonal drift is measurable and material.**
A classifier trained mostly on flowering-season sites drops to 49% on the
dry-season site and 63% on the wet-season hold-out. This is §5.4 risk 6 showing
up empirically, and it supports the proposal's own mitigation: two acquisition
seasons, two classifiers.

**5. The proposal's §5.3 coverage table does not reconcile with itself.**
Two arithmetic problems, surfaced by stage 06 rather than quietly patched:
- the table gives a raw rate of "~46 ha/hr" from "36 m × 6 m/s", but 36 × 6 = **77.8 ha/hr**;
- it states an effective rate of 25–30 ha/hr *and* 80–120 ha per 6-hour field day,
  which implies 13–20 ha/hr. The two rows disagree by roughly 2×.

Neither error changes the strategic conclusion (the three-tier funnel is
mandatory), but a technical evaluator who multiplies 36 by 6 will find it.

**6. Risk 9 has its sign backwards, and the real harm is worse.**
The proposal says label error "inflates apparent accuracy while degrading real
performance". Measured: it *depresses* the apparent figure — 0.702 apparent
against 0.919 true, a −21.7 pp gap — under both site-disjoint and random-split
validation. Inflation would require the model's errors to correlate with the
*validation set's* label errors, which a site-disjoint split makes impossible.

The consequence is worse than the one described: a programme with uncertified
labels reads its own §7.3 go/no-go test as a **failure** while the classifier
clears it. HK$1.4M spent to reach a wrong **stop** decision.

**7. Appendix B.9 is false, on the exact taxon that matters.**
Public barcode coverage is *not* adequate. Across 185 real NCBI sequences,
*Mikania cordata* — the native congener §3.4 names as the hard case — cannot be
certified at all: one rbcL, one ITS2, no matK, no trnH-psbA. And rbcL cannot
separate it from *M. micrantha* anyway; their barcode regions are identical.

**8. §3.3(a) is not implementable as written.**
"Weight and interrogate the regions the biology predicts" cannot be done as a
weight: `StandardScaler` restores unit variance per band and annihilates it, and
tree ensembles are invariant to monotone rescaling. Reimplemented as band
*selection*, the prior scores −0.54 pp against random subsets of the same size.

**9. But the desk study earns its keep, twice.**
Spearman ρ = +0.43 between predicted operational value and measured effect size;
the top-ranked prediction is the strongest measured effect (red-edge position,
d = +1.01). And a constraint derived from genomics *before any measurement* held
up: two of eight predictions reverse the **sign** of their effect between the
flowering and foliage seasons, exactly as constraint A2 predicted.

---

## The honest scope of these numbers

Accuracy figures come from **simulated** scenes at a species contrast that was
chosen, not measured. They characterise the *pipeline*, not Hong Kong.

Proposal Appendix B.5 states the central unknown plainly: whether Mikania is
genuinely separable from *Bauhinia glauca* and *Byttneria aspera* in real canopy
conditions is unproven. So rather than assert a number, stage 05 **sweeps** that
unknown and reports accuracy as a curve, with two controls:

- **at contrast 0** the species are made spectrally identical and accuracy
  collapses to 50.9% — chance, as it must. If it did not, something would be
  leaking and every other figure would be void.
- **the required contrast** to reach the 75% kill criterion is ≈ **0.42** on the
  nominal scale.

That converts the deliverable from "the pipeline achieves X%" into something
AFCD can act on: *here is how much real spectral separability Phase 0's field
spectroradiometer campaign has to demonstrate before aerial capital is committed.*

When those field spectra exist, drop them in `data/raw/field_spectra/*.csv` and
the modelled species block is replaced automatically — the code path already exists.

---

## Pipeline stages

**Spectral track (v1.0)**

| # | Script | What it does | Proposal § |
|---|---|---|---|
| 00 | `00_genomic_desk_study.py` | Ranked, falsifiable spectral predictions from published genomics. No data, no capital, no counterparty | §3.3, §10.0 |
| 01 | `01_fetch_open_data.py` | GBIF occurrences, EcoSIS leaf spectra, Hyperion benchmark; writes a provenance manifest | §5.1 |
| 02 | `02_build_spectral_library.py` | Endmember library from real measured leaves; separability audit; sensor ablation | §5.1(1), §4.1 |
| 03 | `03_simulate_scenes.py` | Five Tier-2 acquisitions with terrain, BRDF, pushbroom artefacts, sub-canopy occlusion | §7.3 |
| 04 | `04_train_validate.py` | PLS-DA / RF / SVM under leave-one-**site**-out; leakage demo; kill-criterion check | §5.1(6), §7.3 |
| 05 | `05_contrast_sweep.py` | Accuracy vs true species separability, with the contrast-0 control | Appendix B.5 |
| 06 | `06_map_and_prioritise.py` | Classify, FCLS unmix, severity score, ranked treatment units, GeoTIFF/GeoJSON export | §3.1, §5.3 |
| 07 | `07_efficacy_reflight.py` | Treatment, re-flight, change detection, per-method re-emergence rates | §3.1(3) |
| 08 | `08_benchmark_real_hsi.py` | The same machinery on real EO-1 Hyperion imagery | control |

**Molecular track (v2.0)**

| # | Script | What it does | Proposal § |
|---|---|---|---|
| 10 | `10_test_genomic_predictions.py` | Falsifies each §3.3 prediction against the library, in two seasons | §3.2, §3.3(c) |
| 11 | `11_fetch_barcode_references.py` | 185 real sequences from NCBI/BOLD; measures reference coverage | §4.2, B.9 |
| 12 | `12_barcode_verify_vouchers.py` | The §3.4 pipeline against a real answer key; barcode gaps; concordance | §3.4 |
| 13 | `13_label_error_propagation.py` | What wrong labels do; what certification is worth | §9 Risk 9 |
| 14 | `14_reference_database.py` | Builds, versions, checksums and values the asset | §3.1(4), §7.1, §8.4 |
| 15 | `15_export_platform.py` | Assembles the browser bundle | — |

## Package layout

```
mikania/
├── config/default.yaml       every constant, with provenance comments
├── mikania/
│   ├── config.py             loading, validation, derived constants
│   ├── io_hsi.py             ENVI / GeoTIFF / npz, georeferencing
│   ├── preprocess.py         Savitzky-Golay derivatives, SNV, continuum removal
│   ├── features.py           red-edge position, indices, sensor-tier ablation
│   ├── spectral_library.py   endmembers, species operators, sampling
│   ├── simulate.py           Tier-2 scene generation
│   ├── unmixing.py           FCLS abundance, conditioning diagnostics
│   ├── classify.py           PLS-DA/RF/SVM, leave-one-site-out, bootstrap CIs
│   ├── severity.py           five-factor scoring, treatment units, GeoJSON
│   ├── change.py             efficacy, detection floors, per-method rates
│   └── economics.py          coverage model, funnel, pricing, §5.3 consistency check
├── config/genomic_priors.yaml published findings -> traits -> signed predictions
├── docs/                     molecular-layer documentation (10 files)
├── scripts/                  the fifteen stages
├── platform/                 stdlib server + no-build dark UI
└── outputs/                  reports (JSON), figures (PNG), deliverables (GIS)
```

`config/default.yaml` is the single source of truth. Every number in it is
either taken from the proposal, taken from cited literature, or flagged as an
explicit modelling assumption. No magic constants are buried in code.

---

## The platform

`python platform/server.py` → <http://127.0.0.1:8790>

Thirteen views. Spectral: overview, sensor evidence, survey viewer (click any
pixel to read its spectrum), spectral lab, validation, work plan, efficacy loop,
and an economics calculator that recomputes coverage live. Molecular: the genomic
desk study with its evidence chains and falsification verdicts, barcode
certification with the real coverage matrix and voucher certificates,
label-error risk, and the reference database with its release checksum and
licence manifest. Plus a data-provenance page separating what is real from what
is simulated.

Standard library only, no build step, no CDN — it has to open on an evaluator's
laptop with no network. The UI **renders**; it never **computes**. Every
scientific number arrives from the pipeline via `data/bundle.json`, and the one
live recomputation (coverage economics) is delegated to the server, which calls
the same `mikania.economics` functions the pipeline uses. Two implementations of
a metric is one too many.

---

## Data provenance

**Real, downloaded, cited** — manifest at `data/raw/PROVENANCE.json`:

- **1,107 GBIF occurrence records** inside Hong Kong: 557 *Mikania micrantha*
  plus five native/confusable climbers. Drives Tier-1 site screening and the
  per-site ecological context layer.
  *Trap worth knowing:* querying GBIF for "Bauhinia glauca" returns **zero** HK
  records — the accepted name is *Phanera glauca*. A pipeline that silently took
  the empty result would have trained a Mikania classifier with nothing to be
  confused by, and reported a beautiful, meaningless accuracy.
- **242 leaf reflectance spectra** (EcoSIS, 350–2500 nm ASD, tropical broadleaf).
  These are the physical base of the endmember library, and their principal modes
  of variation supply the within-class scatter — so the synthetic covariance
  resembles real vegetation rather than white noise.
- **Botswana EO-1 Hyperion scene**, 145 bands, 14 vegetation classes.
- **185 barcode reference sequences** (NCBI GenBank, optionally BOLD) across 7
  accepted taxa and 4 loci — rbcL, matK, ITS2, trnH-psbA. The coverage gaps and
  barcode gaps computed from them are real, and so is the finding that seven
  public records disagree with their own species.
  *Second taxonomy trap, worse than the GBIF one:* querying GenBank for both
  "Bauhinia glauca" and "Phanera glauca" returns records under both names, many
  of them the same records. Treated as two species they generate "interspecific"
  pairs at ~zero distance, which erases the barcode gap for every locus — a
  conclusion about DNA barcoding drawn from a nomenclatural artefact. Handled by
  grouping on accepted name.

**Simulated:** all five catchment scenes and their ground truth, infestation
geometry, treatment outcomes and re-flights. Species spectral differences are
modelled from the mechanism table in §3.2 on top of the real measured leaf base.

**Simulated in the molecular track:** Sanger read degradation applied to real
held-out GenBank sequences; the pairing of four loci into one "voucher" (a real
voucher's loci come from one plant, these come from independent accessions of
the same species); and the visual field calls. Every identification outcome is
real, because the sequences and their identities are.

---

## Notes and caveats

- **Validation is leave-one-site-out, always.** `random_split_leakage_demo()`
  exists only to quantify the inflation and is marked `reportable: False`.
- **Sub-canopy Mikania is excluded from both imagery and ground truth**
  (§5.2, last row). It is physically unobservable from nadir; scoring against it
  would manufacture a false penalty and hide the real limitation. The occluded
  fraction (18%) is reported instead, and accuracy is scoped to canopy level.
- **Treatment assignment is confounded by design** — the expensive method goes to
  the worst units, as a real programme would allocate. Raw per-method comparison
  therefore penalises it; the severity-stratified breakdown is in the JSON, and
  the confound is stated in the report rather than corrected away.
- **Measured re-emergence rates sit below the true rates** because small patches
  fall under the detection floor. That gap is reported, not hidden.
- Verified on CPython 3.14.3, macOS. Exact resolved versions in `requirements.lock.txt`.
