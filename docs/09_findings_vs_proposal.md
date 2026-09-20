# Findings vs the proposal

Where the implementation disagrees with the document it implements.

This file exists because a reference implementation that only ever confirms its
proposal is not evidence — it is decoration. Everything below was produced by
running the code, and each item names the stage that produces it so a sceptical
evaluator can re-derive it.

The proposal's own standard, from §3.2, is the one applied here:

> "rows that fail should be struck rather than quietly retained."

**Every problem below has a fix, and the fixes are measured rather than asserted.
See [`10_solutions_guide.md`](10_solutions_guide.md).**

---

## 1. Risk 9 has the sign backwards — and the real harm is worse

**Proposal §9, Risk 9:** *"This risk is severe precisely because it is silent —
it inflates apparent accuracy while degrading real performance."*

**Measured (stage 13):** at the modelled field-error rate, apparent
Mikania-vs-native accuracy is **0.702** while true accuracy is **0.919**. The gap
is **−21.7 pp** — label error *depresses* the reportable number, it does not
inflate it. The result holds under both validation regimes: site-disjoint
(the reportable one) and a random pixel split (the leaky one, tested precisely
because that is where memorisation could have produced the predicted inflation).

**Why the proposal's reasoning fails.** Inflation requires the model's errors to
correlate with the *validation set's* label errors. Under a site-disjoint split
they cannot — the validation catchment's misidentifications are drawn
independently of the training catchments'. Under a random split a mislabelled
patch of *Bauhinia* is still spectrally *Bauhinia*, and is outvoted by every
correctly-labelled *Bauhinia* patch in training. The classifier does not learn
the surveyor's bias; it overrides it.

**The harm is real and larger than described.** A programme with uncertified
labels reads its own §7.3 go/no-go test as a **failure** while the classifier is
fine: true 0.919 clears the 0.75 threshold, apparent 0.702 does not. That is
HK$1.4M spent to reach a wrong **stop** decision. For a venture whose Phase 0 is
explicitly structured around a kill criterion, spurious abandonment is the more
expensive of the two possible decision errors.

**What to change in the proposal.** Rewrite Risk 9's mitigation column to claim
what is demonstrable: certification protects the *go/no-go decision*, not the
accuracy figure. This is a stronger argument, because it attaches the molecular
spend directly to the HK$1.4M at risk.

> One caveat stated plainly: this is measured on simulated scenes with a modelled
> error rate. The *direction* is a structural consequence of independent train/test
> corruption and will hold in the field; the magnitude will not transfer.

---

## 2. Appendix B.9 is false — and it fails on the exact taxon that matters

**Proposal B.9:** *"Barcode reference coverage is assumed adequate for
M. micrantha, Bauhinia glauca, Byttneria aspera and the dominant host canopy
species in BOLD/GenBank. Unverified."*

**Measured (stage 11), on 185 real sequences downloaded from NCBI:** four of
28 taxon × locus cells are empty and four more are below the two-sequence floor.
**Mikania cordata cannot be certified from public references at all** — one rbcL
sequence, one ITS2, no matK, no trnH-psbA. It cannot reach the two-locus
agreement §13.5 requires, and it has no usable core locus.

That is the native congener. §3.3 explicitly flags it as the comparison that
matters and marks it **[VERIFY whether *M. cordata* occurs in Hong Kong]**. The
answer to the *adjacent* question is now known: whether or not it occurs here,
public sequence data cannot tell it apart from the invasive at the standard loci.

**What to change.** B.9 becomes a measured statement rather than an assumption,
and §5.4 mitigation 9 ("sequence and curate our own vouchers; the resulting
reference set becomes an asset rather than a cost") is promoted from a
contingency to a **Phase 0 requirement** for *Mikania* specifically.

---

## 3. §3.3(a) is not implementable as written

**Proposal §3.3(a):** *"Rather than feeding 200+ bands to a classifier and hoping
feature selection finds something, we can weight and interrogate the regions the
biology predicts. This reduces overfitting risk on a small Phase 0 training set."*

**Measured (stage 10):** applying the prior as per-band feature weights produces
**exactly zero** effect. Every sensible pipeline standardises each band to unit
variance before the model, which annihilates any constant per-band weight applied
beforehand; tree ensembles are additionally invariant to monotone per-feature
rescaling. The first version of this experiment returned three identical numbers
to four decimal places.

Reimplemented as band **selection** — the only form in which a band prior can
enter — the prior-chosen 40 bands score **−0.54 pp** against random 40-band
subsets, and beat only 4 of 12 individual random draws.

**What to change.** Drop the performance claim. The demonstrated value of the
desk study is that it tells the *field campaign* what to measure (see §4 below),
which is a real and cheaper benefit. Claiming a classifier improvement invites an
evaluator to test it, and it does not survive the test.

---

## 4. What the desk study *is* worth — and the constraint it got right

Not everything here is a correction.

**The ranking carries information.** Spearman ρ between predicted operational
score and measured effect size is **+0.43** across eight predictions. The
top-ranked prediction (red-edge position) is also the strongest measured effect
(d = +1.01, SUPPORTED). A few weeks of analyst time on open literature, with no
capital, produced a ranking that beats reading the papers in publication order.

**A constraint predicted before any measurement held up.** Stage 00 derived
constraint A2 from the genomics alone: a constitutive photosystem signal must be
measured *out* of the flowering window. Stage 10 tested it — five of eight
predictions change verdict between seasons and **two reverse the sign of their
effect**. Measuring in bloom alone would have produced confident, wrongly-signed
conclusions about a constitutive trait.

**The most-cited prediction is the least useful.** The NIR plateau rests on
directly measured photosynthetic physiology and ranks **#1 biologically, #8
operationally**, because leaf area index, leaf angle and slope move it far more
than species does. A desk study reporting only the literature ranking would have
sent the HK$400–500k spectroradiometer campaign to measure the wrong feature.
This divergence is the actual deliverable of §10 action 0.

---

## 5. Only one locus has a strict barcode gap

**Measured (stage 12), real sequences:** trnH-psbA is the only locus with a
strict barcode gap (minimum interspecific distance above maximum intraspecific).
All four have a *robust* gap on the 95th/5th percentiles. **rbcL cannot separate
*M. micrantha* from *M. cordata* at all** — their barcode regions are identical
(distance 0.0000), which is textbook behaviour for rbcL within a genus and is
exactly why §13.1 assigns it the lowest discrimination rank.

Both criteria are reported rather than whichever flatters. The strict criterion
is decided by two extreme order statistics, so a single defective public record
can sink a locus — which is not hypothetical: seven records were excluded as
discordant with their own species, and one *M. micrantha* rbcL pair differs by
20% over a 657 bp overlap while both members agree with the other nine.

**What this vindicates.** §13.5's requirement that **two loci agree** before a
voucher is certified is not conservatism, it is necessary. No single locus in the
panel can carry a species call for this taxon set.

---

## 6. The §3.4 pipeline works, and fails in the right direction

**Measured (stage 12):** on 22 vouchers built from real held-out GenBank
sequences, **8 certified, 8 correct, 0 wrong**, 14 quarantined.

The asymmetry is the design intent and worth stating to an evaluator: the gate
never guessed. Everything it passed was right; everything it could not resolve it
refused. A wrong label propagates silently across every hectare surveyed; a
quarantine costs one re-collection.

The 64% quarantine rate is not a pipeline failure — it is the public-database
coverage problem of §2 above, arriving downstream. Quarantine reasons are
dominated by "only 1 locus agrees; need 2" and "no core locus produced a usable
result", both of which are reference-depth problems, not specimen problems.

---

## 7. Certification does not pay for itself on the argument the proposal implies

**Measured (stage 13):** certification costs **HK$169,340** for 148 vouchers,
which sits inside the §7.3 line of HK$150–250k. Avoided wrong-clearance cost on a
3,000 ha programme is **HK$73,483/yr** — a benefit:cost ratio of **0.43**.

Below 1. On avoided clearance cost alone, certification does not pay for itself
at this programme size, and an evaluator with a calculator will find that.

**What to change.** Sell it on the three things that do hold: it protects the
HK$1.4M go/no-go decision (§1 above); it is the auditability a government client
whose stated operational risk is *clearing the wrong plant* is actually buying
(§6.1.6); and it produces deliverable 4, which has its own revenue line (§7.2).

---

## 8. Two taxonomy traps that fail silently

The README already documents the GBIF version: querying for *Bauhinia glauca*
returns zero Hong Kong occurrences because the accepted name is *Phanera glauca*.

**The sequence-database version is worse, because it fails nowhere.** Both names
return records, many of them the same records. Treated as two taxa they generate
"interspecific" pairs at ~zero distance, which collapses the minimum
between-species distance and makes *every* locus report no barcode gap. The
pipeline would then conclude that DNA barcoding cannot separate Hong Kong
climbers — a conclusion about the method drawn from a nomenclatural artefact.
Handled by grouping on `accepted_name` (config §13.8).

**And one in our own file format.** Writing FASTA deflines with space-separated
`key=value` metadata is unparseable for species names, because a binomial
contains a space. The first run read every taxon back as a bare genus, silently
merged *M. micrantha* with *M. cordata*, and reported inflated within-species
distances that destroyed the barcode gap for three of four loci. It did not
error; it produced a confident, plausible, wrong answer. Fixed by pipe-delimiting
(`mikania/barcode.py`, `META_SEP`).

---

## Summary table

| # | Proposal claim | Verdict | Stage |
|---|---|---|---|
| 1 | Risk 9: label error inflates apparent accuracy | **Refuted** — it deflates; real harm is spurious project abandonment | 13 |
| 2 | B.9: public barcode coverage adequate | **Refuted** — *M. cordata* uncertifiable from public data | 11 |
| 3 | §3.3(a): band weighting reduces overfitting | **Refuted** — not implementable as a weight; no benefit as selection | 10 |
| 4 | §3.3: genomics predicts which bands carry signal | **Supported** — ρ = +0.43; and A2 constraint confirmed | 00, 10 |
| 5 | §13.1: multi-locus needed, rbcL weak on congeners | **Supported** — rbcL identical across *Mikania* congeners | 12 |
| 6 | §3.4: barcoding makes labels auditable | **Supported** — 8/8 correct, 0 wrong, 14 refused | 12 |
| 7 | §3.4: "cheap relative to a flying day" | **Supported on cost, weak on stated benefit** — B:C 0.43 | 13 |
| 8 | §7.1: the database is the asset | **Supported structurally**; valuation is Phase-0-scale, not the §7.1 figure | 14 |
