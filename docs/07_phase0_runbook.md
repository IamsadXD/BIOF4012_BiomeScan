# Phase 0 runbook — molecular workstream

Maps proposal §7.3's Phase 0 (Months 1–10, HK$1.4M) onto what people actually do.
The molecular line is HK$150–250k of that envelope and, per §7.3, *"displaces
nothing: it runs during periods when weather prevents flying, and it uses the same
field visits that were already being made to collect spectra."*

## Sequencing of work

```
Month  1   2   3   4   5   6   7   8   9   10
       │
  00   ██                                        genomic desk study (no capital)
  ACC      ████                                   AFCD records, lab access, permits
  FLD          ████████        ████████           two field seasons (spectra + vouchers)
  LAB            ██████████████████               extraction → sequencing → certification
  ANL                  ████████████████████       analysis, concordance, reporting
  FLY                      ██████                 Tier-2 hyperspectral acquisition
```

**Stage 00 is the true first action** and it gates the field campaign design: it
determines which spectral features the spectroradiometer work should target, and
it produces constraint A2 (measure out of bloom), which decides the season
calendar.

## Month 1 — desk work, zero capital

- [ ] Run `scripts/00_genomic_desk_study.py`. Output is the ranked measurement
      list and the acquisition constraints.
- [ ] Run `scripts/11_fetch_barcode_references.py`. **Do this before committing
      to the locus panel** — it tells you which taxa public references cannot
      certify. Current answer: *Mikania cordata* cannot be certified at all.
- [ ] Decide whether the *M. cordata* gap is worth closing by sequencing our own
      congener vouchers. On current evidence: yes, and it is the cheapest
      differentiator in the plan.

## Months 2–3 — access, not equipment

Proposal §10 is emphatic that the first commercial ask precedes any purchase.

- [ ] **AFCD removal records** via Country and Marine Parks Branch, framed as a
      research collaboration (§10.1).
- [ ] **Laboratory access arrangement in writing** — university or commercial
      (§10.8, §8.4). §7.3 assumes outsourced sequencing plus bench access rather
      than building a wet lab; §9 Risk 12 warns against building one in Phase 0.
- [ ] **Collection permit** under Cap. 96 / Cap. 208 (§10.9). Non-issue *if AFCD
      is client or research partner*; a genuine obstacle otherwise.
- [ ] **Quotations** for Sanger and nanopore at Phase 0 volumes, to replace the
      modelled figures in config §13.9.
- [ ] Settle the **deposition policy** (§8.4, §10.10) before any data exists.

## Months 3–8 — two field seasons

Per config §13.6, targets across all sites per season:

| Class | Vouchers |
|---|---|
| *Mikania micrantha* | 24 |
| *Bauhinia glauca* / *Phanera glauca* | 14 |
| *Byttneria aspera* | 14 |
| *Paederia foetida* | 12 |
| host canopy | 10 |

Seasons: `autumn_flower` and `wet_summer`. **Both are required** — constraint A2
says a constitutive signal measured only in bloom is worthless, and stage 10
confirms two predictions reverse sign between seasons.

Minimum **3 sites per species**: fewer, and grouped cross-validation has no unit
of correlation to group on, which is what §5.1(6) requires.

Per specimen, follow `03_barcode_sop.md` stage 1. Two points that are easy to get
wrong and expensive to redo:

- **Paired spectra before tissue removal.** A voucher without them is a herbarium
  specimen, not a row in the asset.
- **The visual field call is recorded blind**, before any lab result. The §5.1(2)
  concordance measurement is worthless if it can be revised afterwards.

## Months 4–9 — laboratory and bioinformatics

Runs during weather that stops flying. Follow `03_barcode_sop.md` stages 2–7.

Batch discipline: one negative control per plate, always. Retain traces. Record
failed reactions rather than silently re-running them.

## Months 6–10 — analysis and reporting

- [ ] **Concordance**: AFCD removal records and blind field calls against barcode
      identity (§5.1.2). Report the sterile/fertile split — it is the quantified
      version of §5.1(3)'s flowering-window argument.
- [ ] **Falsification**: re-run stage 10 against the *real* library. The verdicts
      in `02_genomic_desk_study.md` become real at this point. Strike the rows
      that fail (§3.2).
- [ ] **Reference database release** with integrity check (stage 14).
- [ ] **Kill-criterion evaluation against certified labels only.** §7.3: *"This
      threshold is now measured against barcode-certified labels, which makes it
      a real test rather than a measure of agreement with our own field
      judgement."* Stage 13 shows why this matters: uncertified labels can fail
      the criterion while the classifier passes it.

## Kill criteria

| # | Criterion | Source |
|---|---|---|
| 1 | Mikania-vs-native accuracy < ~75% **against barcode-certified labels**, or false-positive rate unacceptable | §7.3 |
| 2 | Predicted spectral features absent from the ground library across **both** seasons | §7.3 |

Criterion 2 can trigger before any flying spend. That is the point of running the
ground campaign first.

## What survives a kill

§9: *"a Phase 0 that kills the survey business still leaves behind a
barcode-verified reference collection and a molecular verification service (§7.2)
that has customers of its own. The downside is no longer zero."*

Concretely, the assets that persist: the curated barcode reference set (including
whatever closes the *M. cordata* gap), the certified voucher collection with
paired spectra, the concordance measurement — which is saleable to AFCD on its
own — and the versioned database with its licence manifest.
