# SOP — DNA barcode certification of reference vouchers

**Scope.** Every voucher entering the Biomescan spectral reference database.
**Authority.** Proposal §3.4; thresholds in `config/default.yaml` §13.
**Version.** Tied to `molecular.release` config and the pipeline version recorded
on each certificate.

> §3.4: *"Every voucher entering the reference library is barcode-verified before
> it can train anything."* This document is the procedure that claim refers to.
> It exists so that "our botanist identified them" becomes an auditable,
> reproducible, versioned operation — which is what a government client whose
> stated operational risk is *clearing the wrong plant* is actually buying.

---

## Stage 1 — Collection

Per specimen, at the point of collection:

1. **GPS fix** to ≤ 5 m; record horizontal accuracy.
2. **Paired field spectra** under standardised geometry, *before* any tissue is
   removed. A voucher without paired spectra is a herbarium specimen, not a row
   in the asset (config §13.6 `paired_spectra_required`).
3. **Photographs**: whole plant in situ, leaf adaxial and abaxial, stem, and any
   reproductive structure.
4. **Record `sterile` / `fertile`.** This is not bookkeeping — it drives the
   expected identification error rate (§13.7) and it is the variable that makes
   §5.1(3)'s flowering-window argument quantitative.
5. **Visual field call**, recorded *by the collector, before any laboratory
   result is known.* Blinding matters: the concordance measurement in §5.1(2) is
   worthless if the field call can be revised after the sequence comes back.
6. **Tissue**: 2–3 young, undamaged leaves into silica gel within 10 minutes.
7. **Voucher**: pressed specimen retained, labelled with the same `voucher_id`.
8. **Permit reference** recorded on every specimen (see `08_compliance.md`).

Collectors are briefed on the protected-plants schedule under the Forestry
Regulations. Target and look-alike taxa are common climbers, so the risk is low
but non-zero, and it is handled by briefing rather than by policy.

## Stage 2 — Extraction and amplification

- Standard CTAB or column extraction; quantify, normalise, record yield.
- **Four loci per voucher**: rbcL, matK (core) and ITS2, trnH-psbA
  (supplementary). Config §13.1 carries each locus's expected amplicon length and
  its `discrimination_rank`, which is what weights it during adjudication.
- **One negative control per plate, always.** ITS is nuclear and multi-copy and
  co-amplifies fungal endophyte template from field-collected leaves readily.
- Record failed reactions rather than silently re-running them. A locus that
  fails repeatedly for one taxon is a primer problem worth knowing about.

## Stage 3 — Sequencing

- **Sanger, bidirectional**, for routine vouchers.
- **Nanopore** for batch throughput and for specimens that reached escalation.
- Retain trace files. A consensus without its traces is not auditable.

## Stage 4 — QC and assembly

Automated: `mikania.barcode.quality_trim` then `qc_check`. Criteria (config §13.2):

| Criterion | Threshold | Why |
|---|---|---|
| Sliding-window end trim | 10 bp window, mean Q ≥ 25 | Sanger traces are unreliable at both ends; untrimmed ends are the dominant source of spurious mismatches, and a spurious mismatch against a 0.6 pp decision margin is a wrong species call |
| Minimum trimmed length | 200 bp | Shorter is not a barcode |
| Ambiguity fraction | ≤ 2% | A run of Ns near a primer is normal; in the middle it is a failed reaction |
| Mean Phred | ≥ 20 | Q20 = 1% error |
| Homopolymer run | ≤ 12 bp | Nanopore artefact guard, mostly trnH-psbA |
| Forward/reverse agreement | ≥ 0.98 | Disagreement means one direction is wrong |

`qc_check` returns **every** failed criterion, not the first. "Failed QC" is not
actionable; "failed QC, three reasons, all length" tells the lab to change the
primer.

**Chimera screen.** `chimera_score` splits the read and searches each half. A
PCR chimera is two templates spliced mid-amplicon, so its halves have different
best parents. Flagged reads do not proceed to identification.

## Stage 5 — Identification

`mikania.barcode.identify_locus`, per locus, against the curated reference set.

Three thresholds must **all** pass (config §13.3):

| Threshold | Default | Note |
|---|---|---|
| Best-hit identity | ≥ 0.970 | |
| Query coverage | ≥ 0.800 | of trimmed query length |
| **Margin over the next species** | **≥ 0.6 pp** | **The one most pipelines omit** |
| References for the called species | ≥ 2 | one sequence cannot establish an intraspecific range |

**On the margin.** A 99.4% identity to *M. micrantha* licenses nothing if
*M. cordata* also matches at 99.3%. What permits a species call is the
*separation* between the best hit and the best hit of any *other* species, not
the absolute identity. Omitting this check is how a barcoding pipeline produces
confident wrong answers inside a genus — the exact case §3.4 flags.

A locus that cannot separate is **not a failure of the specimen.** It is a
measurement of the locus, and it is recorded as such.

### Reference curation (run before any identification)

`curate_references` flags public records that disagree with their own species:
records are linked when within `max_within_species_distance`, the largest
connected component is the consensus, and anything outside it **with positive
evidence** (a finite distance above threshold to a consensus member) is withheld.

- Not being comparable is *not* evidence of discordance. GenBank is full of
  records covering different subregions of the same gene.
- Flagged records are **reported, not deleted**. Deciding a public record is
  wrong is a taxonomic judgement; the pipeline surfaces the accession, its
  nearest consensus partner and the distance, for a human to adjudicate.

Current run: **7 of 185** records withheld.

## Stage 6 — Adjudication

For specimens where similarity search returns `ambiguous`, escalate to
`place_query`: reference-anchored alignment → Jukes–Cantor distances →
neighbour-joining → **site bootstrap** (200 replicates), accepting a placement at
≥ 0.80 support.

Read placements as **bipartitions, not rooted clades** — an NJ tree is unrooted
and the root this implementation produces is an artefact of join order.

> **Stated limitation.** Support is a *site* bootstrap: it means "the alignment
> columns support this placement", not "the public database sampling supports
> it". For a taxon with three GenBank submissions the second is the larger
> uncertainty, which is why the certificate reports reference depth alongside
> support.

Placements that resolve an ambiguous search contribute at a **0.8 weight
discount** — they resolved a case the primary method could not, and the
confidence should record that rather than pretending the ambiguity never happened.

## Stage 7 — Release

`mikania.barcode.adjudicate`, then the gate.

**Loci are weighted by `discrimination_rank`, not counted.** A confident rbcL call
is genus-level evidence; a confident ITS2 call is species-level evidence.
Counting them equally would let two weak plastid loci outvote the one locus that
can resolve congeners.

**Disagreement between loci is disqualifying, not averaged.** Plastid and nuclear
markers disagreeing is a real biological signal — hybridisation, introgression,
or a contaminated reaction — and the correct response is to quarantine and
escalate, not to take a majority.

Release requires (config §13.5): composite confidence ≥ 0.90, **≥ 2 loci
agreeing**, and **≥ 1 core locus** (rbcL or matK) with a usable result.

**Quarantine, do not discard.** The set of specimens that cannot be identified
molecularly is itself the direct measurement of Risk 10, and the evidence base
for escalating specific specimens to genome skimming.

## Escalation

| Situation | Action |
|---|---|
| Loci disagree | Re-extract from a second leaf; if it persists, genome-skim |
| No core locus amplifies | Re-amplify with alternative matK primers |
| Ambiguous within *Mikania* | Genome skimming — plastome + rDNA cistron |
| Reference depth < 2 for the called taxon | Sequence additional vouchers of that taxon and deposit (§8.4) |

## What the current run establishes

On 22 vouchers built from real held-out GenBank sequences:

- **8 certified, 8 correct, 0 wrong.** The gate never guessed.
- **14 quarantined**, dominated by "only 1 locus agrees; need 2" and "no core
  locus produced a usable result" — both reference-depth problems, not specimen
  problems.
- **Only trnH-psbA has a strict barcode gap**; all four have a robust one.
  **rbcL cannot separate the two *Mikania* congeners** — identical barcode
  regions. This is why the two-locus rule is necessary rather than conservative.

The asymmetry is the design intent, and it is what to tell an evaluator: a wrong
label propagates silently across every hectare surveyed; a quarantine costs one
re-collection.
