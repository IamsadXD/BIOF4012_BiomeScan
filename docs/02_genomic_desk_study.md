# The genomic desk study

**Proposal §3.3 and §10 action 0.** *"Zero capital, a few weeks of analyst time,
uses only open data, and it determines what the field campaign should measure.
This is now the true first action."*

Produced by `scripts/00_genomic_desk_study.py`; tested by
`scripts/10_test_genomic_predictions.py`.

## What it is for

v1.0 asserted that *Mikania micrantha* is spectrally separable from native
climbers on the strength of one published accuracy figure. An evaluator is
entitled to ask *why the difference should exist* and *whether it will persist*.
The genomics answers both — but only if the inference from gene to band is made
explicit enough to be wrong.

## Method

Three layers, in `config/genomic_priors.yaml`:

**Findings** (8) — claims taken from named papers, each with a DOI and an
`evidence` tier: `published_genomic`, `published_physiological`,
`published_transcriptomic`.

**Traits** (5) — the inferential step. Each names the findings it rests on and
carries tier `inferred_trait`. This is where §3.2's caveat bites: *"the genomic
and transcriptomic findings are published, the causal chain to a specific band is
inference."*

**Predictions** (8) — each names a spectral window, a **measurement function**, a
**signed direction**, and a **falsification test**. A prediction without a sign is
unfalsifiable, because any observed difference confirms it. Every row commits.

### Confidence propagation

Confidence is **floored by the weakest link**, not averaged. A chain passing
through one unmeasured inferential step is exactly as speculative as that step,
regardless of how solid the genomics at the far end is. All eight chains
terminate in `inferred_optical`, so the honest headline is:

> No leaf-optical measurement linking these genes to reflectance exists for Hong
> Kong material — by us or, as far as we are aware, by anyone. (Appendix B.8)

### Two rankings, deliberately

| Score | Means |
|---|---|
| `biological_score` | how well the published literature supports it |
| `operational_score` | the same, discounted by `nuisance_exposure` — how badly leaf area index, leaf angle, slope and illumination corrupt that feature |

Reporting only the first would send the field campaign to measure the wrong
thing. The divergence between them is the deliverable.

## Results

### The ranking

| # | Prediction | Window (nm) | Dir | Bio | Ops | Nuisance | Sensor |
|---|---|---|---|---|---|---|---|
| 1 | red edge position | 680–760 | + | 0.364 | **0.273** | 0.25 | hyperspectral |
| 2 | green peak position | 520–600 | + | 0.364 | 0.255 | 0.30 | hyperspectral |
| 3 | stem shape ratio | 670–900 | − | 0.378 | 0.245 | 0.35 | multispectral |
| 4 | derivative shape | 690–750 | ± | 0.375 | 0.223 | 0.30 | hyperspectral |
| 5 | carotenoid depth | 470–520 | − | 0.386 | 0.212 | 0.45 | hyperspectral |
| 6 | water band | 950–1000 | − | 0.391 | 0.176 | 0.55 | hyperspectral |
| 7 | anthocyanin shoulder | 550–580 | − | 0.358 | 0.143 | 0.60 | hyperspectral |
| 8 | **NIR plateau amplitude** | 780–900 | − | **0.391** | **0.059** | 0.85 | multispectral |

### Finding 1 — the best-supported prediction is the least useful

The NIR plateau ranks **#1 biologically and #8 operationally**, a seven-place
shift. It rests on directly measured photosynthetic physiology, and leaf area
index and slope move it far more than species does. §3.2's own NIR row already
says amplitude differences are "confounded by illumination"; the desk study puts
a number on it.

### Finding 2 — the literature does not tell you which band to measure

Biological scores span **0.033** across all eight predictions. They all share the
same weakest link, so the biological ranking barely discriminates. *All* the
discriminating information in the final ranking comes from nuisance exposure —
that is, from remote-sensing physics, not from genomics.

Worth saying out loud to a genomics-literate evaluator who might expect the
opposite. The genomics establishes that a mechanism plausibly exists; it does not
choose the band.

### Finding 3 — the ranking predicts measurability

Spearman ρ between operational score and measured effect size (stage 10,
site-blocked, foliage season) is **+0.43**. The top-ranked prediction is also the
strongest measured effect: red-edge position, d = **+1.01**, SUPPORTED.

This is the return on the exercise: a few weeks on open literature, no capital,
producing a ranking that beats reading the papers in publication order.

### Finding 4 — an acquisition constraint, derived before any measurement

Two constraints fall out of the genomics that a band-ranking exercise alone would
have missed:

**A1 — diurnal window.** Night-time CO₂ uptake and diurnally-structured expression
of photosynthetic genes imply the physiological state varies through the day.
Mixing morning and afternoon sorties within a comparison introduces a batch
effect that looks exactly like species variance. *Cost consequence:* narrows
usable hours below the ~8 h assumption in §5.2, worsening §5.3 coverage economics.

**A2 — measure out of bloom.** A constitutive photosystem signal must be measured
outside the flowering window to be worth anything; measuring in bloom and
inferring the rest assumes the conclusion.

**A2 was then tested.** Five of eight predictions change verdict between seasons,
and **two reverse the sign of their effect** (anthocyanin shoulder, NIR plateau).
The autumn bloom adds a bright, spectrally flat floral component that fills the
red absorption well and lifts the NIR plateau, so features built on those
quantities inherit the flower rather than the photosystem.

A constraint predicted from genomics *before* any spectrum was measured, then
confirmed by measurement, is the strongest single item this desk study produces.

### Finding 5 — §3.3(a)'s claim does not survive

§3.3(a) says biology-informed band weighting "reduces overfitting risk on a small
Phase 0 training set". Two problems:

**It is not implementable as a weight.** Every sensible pipeline standardises each
band to unit variance before the model, which annihilates a constant per-band
weight; tree ensembles are additionally invariant to monotone rescaling. The
first version of the experiment returned three identical numbers to four decimals.

**As selection, it does not help.** Prior-chosen 40 bands score **−0.54 pp**
against random 40-band subsets under leave-one-site-out at Phase 0 sample sizes,
beating only 4 of 12 individual random draws.

Reported as measured. The defensible claim is narrower and still valuable: the
prior directs the *field campaign*, it does not improve the *model*.

## Falsification results (stage 10, foliage season, site-blocked)

| Prediction | d foliage | d in bloom | Verdict |
|---|---|---|---|
| red edge position | +1.01 | +0.95 | **SUPPORTED** |
| derivative shape | −0.57 | −0.54 | **SUPPORTED** |
| water band | −1.09 | −0.62 | **SUPPORTED** |
| green peak position | +0.23 | +0.39 | not supported |
| stem shape ratio | +0.02 | +4.65 | not supported |
| carotenoid depth | −0.12 | −1.34 | not supported |
| anthocyanin shoulder | +0.02 | −1.08 | not supported |
| NIR plateau amplitude | −0.00 | +0.47 | not supported |

**3 supported, 5 not supported, 0 refuted.**

> **Scope, stated plainly.** These spectra come from the stage-02 library, whose
> species contrasts are *modelled* on a real measured leaf base and swept in
> stage 05. This validates the falsification machinery and shows the shape of the
> Phase 0 deliverable. **It establishes nothing about Hong Kong material.** When
> real field spectra exist, drop them in `data/raw/field_spectra/` and re-run —
> the verdicts become real.

## What this buys commercially

1. **A ranked measurement list** for the HK$400–500k spectroradiometer campaign,
   with the two rankings separated so the campaign measures what is useful rather
   than what is best cited.
2. **An acquisition constraint** (A2) with direct cost consequences, derived
   before any spend.
3. **A defensible answer** to a government ecologist asking *why* the difference
   should exist — with the inferential steps labelled as inference.
4. **A falsification protocol** that converts §3.2's mechanism table from
   assertion into a set of tests that can strike their own rows.
