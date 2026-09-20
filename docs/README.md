# MIKANIA-HSI — molecular layer documentation (proposal v2.0)

The v1.0 spectral pipeline is documented in [`../README.md`](../README.md). These
documents cover the **molecular / bioinformatics layer** added by proposal v2.0:
the genomic desk study (§3.3), DNA-barcode certification of the label set (§3.4),
the reference database as an asset (§7.1), and the compliance surface a
biological workstream adds (§8.4).

| # | Document | Answers |
|---|---|---|
| 01 | [Implementation guide](01_implementation_guide.md) | How the whole thing is built and how to run it |
| 02 | [Genomic desk study](02_genomic_desk_study.md) | Why Mikania *should* be separable, and which bands to measure |
| 03 | [Barcode SOP](03_barcode_sop.md) | The auditable lab + bioinformatics procedure, step by step |
| 04 | [Reference database spec](04_reference_database_spec.md) | Schema, versioning, licensing, valuation |
| 05 | [Label error and Risk 9](05_label_error_and_risk9.md) | What wrong labels do — and why the proposal has the sign backwards |
| 06 | [Open data register](06_open_data_register.md) | Every external source, with licence and citation |
| 07 | [Phase 0 runbook](07_phase0_runbook.md) | What the field and lab teams actually do, week by week |
| 08 | [Compliance](08_compliance.md) | Permits, Nagoya, deposition policy, PDPO |
| 09 | [Findings vs the proposal](09_findings_vs_proposal.md) | Where the implementation contradicts the document it implements |
| 10 | [Solutions guide](10_solutions_guide.md) | The fix for each problem, measured, with the proposal text to change |
| 11 | [Improvements and next steps](11_improvements_and_next_steps.md) | Where the code is weak, what to fix in what order, and what the venture does next |

## The short version

Nine things this layer establishes, all reproducible from the code:

1. **The genomics gives a ranked, falsifiable prediction set**, and the ranking
   carries real information — Spearman ρ = +0.43 between predicted operational
   value and the effect sizes actually measured.
2. **The best-supported prediction is the least useful one.** The NIR plateau
   ranks #1 biologically and #8 operationally. A desk study reporting only the
   literature would have aimed the field campaign at the wrong feature.
3. **A constraint derived from genomics before any measurement held up.** Two of
   eight predictions reverse the *sign* of their effect between the flowering and
   foliage seasons.
4. **§3.3(a) is not implementable as written.** Band "weighting" is annihilated by
   the `StandardScaler` every sensible pipeline contains. Reimplemented as band
   selection it still does not beat random bands (−0.54 pp).
5. **Appendix B.9 is false.** Public reference coverage is *not* adequate:
   *Mikania cordata* — the native congener, the exact hard case §3.4 names —
   cannot be certified from public data at all.
6. **Only one of four loci has a strict barcode gap** (trnH-psbA); all four have
   a robust one. rbcL cannot separate the two *Mikania* congeners: their barcode
   regions are identical.
7. **The §3.4 pipeline makes no wrong calls** on a real answer key — 8/8 certified
   correctly, 14 quarantined rather than guessed.
8. **Risk 9 has the sign backwards.** Label error does not inflate apparent
   accuracy; it depresses it, and the real danger is *spuriously failing* the
   §7.3 kill criterion — abandoning a classifier that works.
9. **Certification does not pay for itself on avoided wrong-clearance alone**
   (benefit:cost 0.43). It pays for itself by protecting the go/no-go decision
   and by producing the asset. That is a different sales argument from the one
   the proposal makes, and a more defensible one.

All three failures are fixable, and [the fixes are measured](10_solutions_guide.md):
certifying the **validation** set rather than the training set restores go/no-go
reliability from 42% to 100% at no extra cost; the reference gap is a HK$510
problem on a taxon with one Hong Kong record; and §3.3(a) needs its claim
narrowed rather than its method replaced.
