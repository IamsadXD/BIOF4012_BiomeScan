# Solutions guide — fixing the three problems

[`09_findings_vs_proposal.md`](09_findings_vs_proposal.md) reports three proposal
claims that do not survive measurement. This document is the remedy for each:
what to change in the code, what to change in the proposal text, what it costs,
and — for every fix — **the measurement showing whether it actually works**.

That last part is not ceremony. §3.3(a) failed *precisely because* it claimed a
benefit nobody tested. A remediation guide proposing untested fixes would repeat
the error it exists to correct. So every fix below is implemented in
[`mikania/remediation.py`](../mikania/remediation.py) and measured by
[`scripts/16_remediation.py`](../scripts/16_remediation.py):

```bash
.venv/bin/python scripts/16_remediation.py
```

---

## Summary

| # | Problem | Fix | Works? | Cost |
|---|---|---|---|---|
| 1 | Go/no-go decision unreliable | Certify the **validation** set, not the training set | **Yes** — 42% → 100% decision reliability | **Zero** — it reallocates the existing §7.3 line |
| 1b | Certification budget spread thin | Rank specimens by model–label disagreement | **Yes** — 3.0× enrichment over random | Saves ~70% of sequencing for the same error recovery |
| 2 | Reference coverage inadequate (B.9 false) | Sequence the gap taxon — after scoping it | **Yes, and it is trivial** | **HK$510** consumables |
| 3 | Band prior not implementable (§3.3a) | Apply after standardisation, penalised model, no PCA | **Half** — now expressible, still not informative | Free; but the *claim* must be narrowed |

**The headline: two of the three fixes cost essentially nothing, because they are
reallocations rather than additions.** The third is not a fix to the method but a
correction to what is claimed for it.

---

# Fix 1 — Protect the go/no-go decision

## Diagnosis

Stage 13 measured that label error *depresses* apparent accuracy (0.702 apparent
against 0.919 true) rather than inflating it, and the harm is that a programme
**fails its own §7.3 kill criterion while the classifier works** — HK$1.4M spent
to reach a wrong stop decision.

## The fix

**Certify the validation plots exhaustively; sample the training plots.**

This inverts §3.4 as written, which says *"every voucher entering the reference
library is barcode-verified before it can train anything"* — allocating the
sequencing budget across the whole voucher set, weighted toward training data
because that is where most vouchers are.

### Why the inversion is right

Two facts combine:

1. The §7.3 kill criterion is evaluated on the **hold-out**, so the verdict is
   read off the validation labels.
2. Stage 13 showed the classifier **overrides** training-label noise rather than
   learning it — a mislabelled patch of *Bauhinia* is still spectrally
   *Bauhinia*, and is outvoted by every correctly-labelled *Bauhinia* patch.

So training-label errors barely move the model, while validation-label errors
move the number the decision is read from, one-for-one. Certifying training data
buys accuracy you already had. Certifying validation data buys a trustworthy
decision.

## The evidence

12 trials (6 replicates × 2 error rates, 0.18 and 0.30). Truth: accuracy 0.9345,
verdict **PASS**. 514 specimens in the validation catchment.

**P(go/no-go decision is correct)**

| Certified | none | train_only | val_only | both |
|---|---|---|---|---|
| 0% | 42% | 42% | 42% | 42% |
| 25% | 42% | 50% | **83%** | 83% |
| 50% | 42% | 50% | **100%** | 100% |
| 75% | 42% | 42% | **100%** | 100% |
| 100% | 42% | **50%** | **100%** | 100% |

Read the two end columns against each other. **Certifying 100% of the training
set leaves the decision right 50% of the time — a coin flip.** Certifying 50% of
the *validation* set makes it right every time.

The `both` column is identical to `val_only` at every fraction, which is the
result stated most sharply: **the entire benefit of §3.4's certification plan
comes from the validation half.** Everything spent on the training half bought
nothing for this decision.

## What it costs

Nothing. It is a reallocation inside the existing HK$150–250k line.

In fact it *releases* budget: 50% of the validation set is 257 specimens against
the §13.6 plan of 148 vouchers per season across all sites. Restated for
planning: **stop sizing certification by total vouchers and start sizing it by
validation plots.**

## Fix 1b — spend what remains where the errors are

Rank specimens by how much the classifier disagrees with their label (using
out-of-fold predictions, so no specimen is scored by a model that trained on it),
then sequence from the top.

| Budget | Sequenced | Errors found | Recall | Enrichment |
|---|---|---|---|---|
| 10% | 253 | 24/103 | 23% | 2.3× |
| 20% | 505 | 57/103 | 55% | 2.8× |
| **30%** | **758** | **92/103** | **89%** | **3.0×** |
| 50% | 1,263 | 99/103 | 96% | 1.9× |

A 30% budget recovers 89% of genuine label errors. Random sampling recovers 30%,
by construction. This is standard active label cleaning, and it matters here
because it makes partial certification *disproportionately* effective — which is
what makes Fix 1 affordable in the field, where 100% validation certification may
not be reachable.

**Operational rule:** certify all validation plots you can reach; spend the
remainder on the training specimens the classifier disputes, never on a random
sample.

## Proposal edits

**§3.4, replace the bolded sentence.**

> *Before:* **Every voucher entering the reference library is therefore
> barcode-verified before it can train anything.**

> *After:* **Every voucher used to validate a classifier is barcode-verified
> without exception, and training vouchers are certified in priority order.**
> The asymmetry is deliberate and measured: a classifier overrides label noise in
> training rather than learning it, but the §7.3 go/no-go verdict is read
> directly off the validation labels. Certifying the full training set leaves
> that verdict correct about half the time; certifying half the validation set
> makes it correct every time. Remaining certification capacity is directed at
> the training specimens the classifier disagrees with, which recovers ~89% of
> label errors for 30% of the sequencing.

**§9, Risk 9 — replace impact and mitigation.**

> *After:* Uncertified labels do not flatter the accuracy figure — they depress
> it by ~20 pp at plausible error rates, because the classifier overrides the
> surveyor's bias rather than learning it. The consequence is that a programme
> scoring against its own labels can **fail** the §7.3 kill criterion while the
> classifier performs well above it, and abandon a working method. Mitigation:
> exhaustive barcode certification of the validation set (§3.4), which restores
> the decision from ~42% reliable to 100%.

**§7.3, kill criteria — add one clause.**

> The threshold is evaluated **only against barcode-certified validation
> labels**. A kill decision computed against uncertified labels is not a
> measurement of the classifier; it is a measurement of the field team.

## Implementation checklist

- [ ] Split the voucher plan (config §13.6) into `validation_targets` and
      `training_targets`; size the first from validation plots, not total area.
- [ ] Make `refdb.integrity_check` fail when any validation-site voucher is
      uncertified — a `critical`, not a `warning`.
- [ ] Run `disagreement_targeting` before each sequencing batch; sequence in
      rank order.
- [ ] Record which release a reported accuracy was computed against
      (`certificate.release_id` already carries this).

---

# Fix 2 — Close the reference gap, after scoping it

## Diagnosis

Appendix B.9 assumes public barcode coverage is adequate. It is not:
*Mikania cordata* cannot be certified from public references at all (1 rbcL,
1 ITS2, no matK, no trnH-psbA), and rbcL cannot separate it from *M. micrantha*
anyway — their barcode regions are identical.

## Scope it before you fix it

The proposal's own **[VERIFY]** in §3.3 asks whether *M. cordata* occurs in Hong
Kong. GBIF answers it for the cost of one API call:

| Taxon | HK georeferenced records | Global |
|---|---|---|
| *Mikania micrantha* | **557** | 15,799 |
| *Mikania cordata* | **1** | 895 |

And that single record is a **1991 preserved specimen with no
`identificationVerificationStatus` and no institution code**. *M. cordata*'s
actual range is centred on Taiwan, Papua New Guinea, West Africa and Indonesia.

Two things follow, and they point in opposite directions:

**The operational problem largely dissolves.** The congener that public
references cannot certify is effectively absent from Hong Kong. A field surveyor
will not encounter it, so the classifier does not need to discriminate it, and
Risk 10's severity for *this* taxon drops from high to low.

**The comparative-genomic argument does not dissolve.** §3.3 rests substantially
on the published *M. micrantha* vs *M. cordata* contrast (finding F5, the
chromosome-scale genomes of both). That argument is about *why a spectral
difference should exist*, and it is unaffected by whether the congener grows
here.

**And a third thing, which is a small commercial opportunity.** That 1991
specimen is a prime candidate for barcode re-verification — *M. micrantha* was
historically misidentified as *M. cordata* across the region, which is exactly
the confusion the standalone molecular verification service in §7.2 exists to
resolve. It is a cheap, concrete demonstration piece to offer AFCD or the HK
Herbarium.

## The fix, costed

| Taxon | Current | Needs | Cost | Priority |
|---|---|---|---|---|
| *Mikania cordata* | rbcL 1, matK 0, ITS2 1, trnH-psbA 0 | 3 sequences across 2 loci | **HK$510** | Low (1 HK record) |

Total to close every gap in the panel: **HK$510** in consumables. There is no
high-priority gap.

That number is small enough to be worth stating plainly: **the reference-coverage
problem that falsifies Appendix B.9 costs about five hundred Hong Kong dollars of
consumables to fix**, assuming material is obtainable. The binding constraint is
not money, it is **access to verified *M. cordata* tissue** — which means a
herbarium loan, not a field trip, since the plant does not grow here.

## Proposal edits

**Appendix B.9 — replace the assumption with the measurement.**

> *After:* Public barcode reference coverage was **measured**, not assumed
> (185 sequences, NCBI, stage 11). It is adequate for *M. micrantha*, *Phanera
> glauca*, *Bauhinia championii*, *Byttneria aspera*, *Paederia foetida* and
> *Dalbergia benthamii*. It is **inadequate for *M. cordata***, which cannot
> reach the two-locus agreement requirement from public data. GBIF records one
> Hong Kong occurrence of *M. cordata* (a 1991 preserved specimen, unverified)
> against 557 for *M. micrantha*, so this gap is a credibility and
> comparative-genomics issue rather than an operational one. Closing it costs
> ~HK$510 in consumables and requires herbarium material.

**§3.3 — resolve the [VERIFY].**

> *After:* **[RESOLVED]** *M. cordata* is effectively absent from Hong Kong
> (1 GBIF record, 1991, unverified). The comparative-genomic argument stands on
> the published genomes regardless of local occurrence; the operational
> discrimination problem is against *Bauhinia glauca*/*Phanera glauca*,
> *Byttneria aspera* and *Paederia foetida*, for all of which public reference
> coverage is adequate.

**§5.4, Risk 10 — downgrade with the reason.**

> *After:* Severity **Low–Medium** (was Medium). Measured: only one taxon in the
> panel is uncertifiable from public references, and it barely occurs in Hong
> Kong. Retain the multi-locus panel — rbcL was measured to be **incapable** of
> separating the *Mikania* congeners, which is why §13.5 requires two loci to
> agree rather than trusting one.

## Implementation checklist

- [ ] Request *M. cordata* material from the HK Herbarium (AFCD) or a regional
      herbarium — a loan, not a collection.
- [ ] Sequence matK and trnH-psbA for it; deposit both (§8.4 rule fires:
      public coverage < 5).
- [ ] Offer to barcode the 1991 HK specimen as a demonstration of the §7.2
      verification service.
- [ ] Re-run stage 11 quarterly; `retrieved_utc` in the coverage report exists so
      drift is visible.

---

# Fix 3 — The band prior, applied where it survives

## Diagnosis

§3.3(a) claims biology-informed band weighting "reduces overfitting risk on a
small Phase 0 training set". Two problems: it is not implementable as a weight,
and as selection it did not help.

## The fix — operation order

The weighting failed for a mechanical reason, not a conceptual one. Multiplying
features by weights and handing them to a pipeline whose first step is
`StandardScaler` restores unit variance per band and **annihilates the weight
exactly**. Tree ensembles are additionally invariant to monotone per-feature
rescaling.

Applied *after* standardisation to a model with an L2 penalty, a per-band weight
is no longer cosmetic: scaling standardised feature *j* by *w<sub>j</sub>* is
algebraically identical to giving its coefficient a penalty of λ/*w<sub>j</sub>*².
That is a textbook informative prior — and it is what §3.3(a) was reaching for.

Three conditions must hold, all violated in the original attempt:

| Condition | Why |
|---|---|
| Prior applied **after** `StandardScaler` | before it, the weights are undone exactly |
| Model must be **penalised** | an unpenalised model ignores feature scale entirely |
| **No PCA** | PCA rotates the band basis away, destroying the identity the prior is written in |

Implemented as `remediation.PriorScaler` + `remediation.prior_model`.

## The evidence

Leave-one-site-out, foliage season, Phase 0 sample sizes. The control is a
**permuted** prior — the same weight distribution assigned to the wrong bands —
which isolates "the biology picked good bands" from "uneven regularisation helps".

| C | uniform | genomic prior | permuted prior | Δ vs permuted | beat |
|---|---|---|---|---|---|
| 0.01 | 0.825 | 0.823 | 0.825 | −0.24 pp | 4/12 |
| 0.05 | 0.830 | 0.820 | 0.821 | −0.14 pp | 4/12 |
| 0.5 | 0.800 | 0.799 | 0.799 | −0.02 pp | 5/12 |

**Not supported.** And the strongest evidence that this is a true null rather
than an underpowered test: an earlier run of the identical experiment gave
**+0.72, +0.51, −0.30 pp** — the sign flipped between runs. An effect that
changes sign under reseeding is an effect of size zero.

## What this means

The fix is real but partial, and it is worth being precise about which half
succeeded:

- **The prior is now expressible.** It is no longer silently annihilated, and
  the implementation is available if a future, better-grounded prior (one built
  on *measured* leaf optics rather than inferred ones) is worth testing.
- **It is not informative.** On this data, the genomics does not pick better
  bands than chance.

That is not surprising in hindsight, and stage 00 predicted it: biological scores
span only **0.033** across all eight predictions, because every chain terminates
in the same `inferred_optical` tier. *The literature establishes that a mechanism
plausibly exists; it does not choose the band.* A prior that barely discriminates
between its own predictions cannot be expected to discriminate between bands.

## What to claim instead

The desk study has **two demonstrated benefits**, and they are not classifier
performance:

1. **It directs the field campaign.** Spearman ρ = +0.43 between predicted
   operational value and measured effect size; the top-ranked prediction is the
   strongest measured effect (red-edge position, d = +1.01). For a few weeks of
   analyst time and no capital, that is a real return on a HK$400–500k campaign.
2. **It produced a falsifiable acquisition constraint that held.** Constraint A2
   (measure out of bloom) was derived from genomics before any measurement; two
   of eight predictions then reversed the **sign** of their effect between
   seasons.

## Proposal edits

**§3.3(a) — replace entirely.**

> *Before:* **(a) Band prioritisation becomes hypothesis-driven.** Rather than
> feeding 200+ bands to a classifier and hoping feature selection finds
> something, we can weight and interrogate the regions the biology predicts. This
> reduces overfitting risk on a small Phase 0 training set — the regime where
> blind feature selection fails hardest.

> *After:* **(a) The field campaign becomes hypothesis-driven.** The genomics
> yields a ranked, signed, falsifiable list of spectral regions, which tells the
> Phase 0 spectroradiometer campaign what to measure and — through the
> acquisition constraints it implies — when. Tested against the ground library,
> the ranking correlates with measured effect size (Spearman ρ = +0.43) and its
> top-ranked prediction is the strongest measured effect. We make **no claim**
> that the prior improves classifier performance: implemented correctly as a
> penalty on a regularised model, it does not beat a permuted prior of the same
> weight distribution. The value is in aiming the measurement campaign, which is
> where the money is.

**Appendix B — add an assumption that was tested and failed.**

> **15. Biology-informed band prioritisation was assumed to improve classifier
> performance.** Tested and not supported. The claim has been narrowed to
> campaign direction (§3.3a).

## Implementation checklist

- [ ] Use `remediation.prior_model` if testing any future prior — it enforces the
      three conditions.
- [ ] Re-test when **measured** leaf optics exist for HK material; the current
      null is a statement about an inferred prior, not about all priors.
- [ ] Keep the permuted-prior control in any future test. Without it, uneven
      regularisation is indistinguishable from informative biology.

---

# Consolidated changes

## Budget (§7.3) — unchanged in total

| Workstream | Before | After | Change |
|---|---|---|---|
| Field spectroradiometry | HK$400–500k | unchanged | — |
| Molecular verification | HK$150–250k | unchanged in total, **reallocated** | validation-first, disagreement-targeted; +HK$510 for the *M. cordata* gap |
| UAV acquisition | HK$400–500k | unchanged | — |
| Analysis and reporting | HK$200–300k | unchanged | — |

**No new money is required to fix any of the three problems.**

## Risk register (§9)

| # | Change |
|---|---|
| 9 | Rewrite direction (deflation, not inflation); mitigation becomes validation-set certification; likelihood of a wrong go/no-go without it: **58%** |
| 10 | Downgrade to Low–Medium; add the measured barcode-gap result (only trnH-psbA has a strict gap; rbcL cannot separate the congeners) |
| — | **New Risk 13:** the §7.3 kill criterion is evaluated against uncertified labels and spuriously fails. Impact Critical, Likelihood High if unaddressed, Mitigation Fix 1 |

## Next actions (§10)

| # | Change |
|---|---|
| 0 | Keep as-is — it earned its place (ρ = +0.43, constraint A2 confirmed) |
| 3.3 [VERIFY] on *M. cordata* | **Resolved** — 1 HK record, 1991, unverified |
| B.9 | **Resolved** — measured, and false |
| — | **New:** request *M. cordata* herbarium material to close the reference gap (HK$510) |
| — | **New:** split the voucher plan into validation and training targets |

## What an evaluator should be told

The three corrections make the proposal *stronger*, not weaker, and it is worth
saying so directly:

1. **Risk 9's fix is now cheaper and better-aimed.** "Certify the validation set"
   is a smaller, more defensible ask than "certify everything", and it attaches
   the molecular spend directly to the HK$1.4M go/no-go decision.
2. **B.9's failure is a HK$510 problem** on a taxon that barely occurs here — and
   discovering that cost one afternoon of open-data work rather than a Phase 0
   surprise.
3. **§3.3(a)'s retraction removes a claim an evaluator would have tested and
   broken.** What remains — that the desk study directs the field campaign — is
   demonstrated rather than asserted.

A proposal that reports three of its own claims failing, with fixes and
measurements attached, is more credible than one that reports none.
