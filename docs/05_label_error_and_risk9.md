# Label error, Risk 9, and what certification actually protects

Produced by `scripts/13_label_error_propagation.py` and `mikania/labelerror.py`.

## The claim under test

> **Proposal §9, Risk 9:** *"Training labels corrupted by field misidentification
> | Critical | High if unaddressed | ... This risk is severe precisely because it
> is silent — it inflates apparent accuracy while degrading real performance."*

Specific, directional, testable. So it was tested.

## The model

**The unit of corruption is a specimen, not a pixel.** This is the single most
important modelling decision here, and getting it wrong reverses the conclusion.
A surveyor does not label pixels; they identify one vine, and that judgement
propagates to every pixel of the training polygon drawn around it. Errors arrive
as spatially coherent blocks sharing one wrong label.

> An earlier version flipped labels independently per pixel and measured almost
> nothing: true accuracy sat at 0.93 even under 30% corruption. That result was
> correct for what it modelled and irrelevant to the field. Independent per-pixel
> flips are zero-mean noise a random forest averages away — they cannot teach a
> model anything, because there is nothing coherent to learn. This is exactly why
> §5.1 says label error "is systematic".

Only climber labels are corrupted. Nobody mistakes bare rock for a vine; the
error lives entirely in the discrimination §2.1(b) describes.

`bias` is the fraction of errors going *toward* Mikania — a surveyor working a
control programme is primed to find it. Bias 0.50 is the symmetric control.

## Result 1 — the direction is wrong

At the modelled rates (18% on sterile specimens, bias 0.65), leave-one-site-out:

| | |
|---|---|
| apparent Mikania-vs-native | **0.702** |
| true | **0.919** |
| gap | **−21.7 pp** |

Negative throughout the sweep, at every bias level including 0.90. Label error
**depresses** the apparent number; it does not inflate it.

### Why

Inflation requires the model's errors to correlate with the **validation set's**
label errors. Under a site-disjoint split they cannot: the validation catchment's
misidentifications are drawn independently of the training catchments'.

A random pixel split was run as well — the regime §5.1(6) already condemns —
on the theory that a corrupted patch straddling the boundary could be memorised
and reproduced:

| error rate | site-disjoint | random split |
|---|---|---|
| 5% | −0.2 pp | −1.6 pp |
| 10% | −10.4 pp | −5.9 pp |
| 20% | −16.8 pp | −10.9 pp |
| 30% | −24.4 pp | −15.9 pp |

Also negative. A mislabelled patch of *Bauhinia* is still spectrally *Bauhinia*,
and is outvoted by every correctly-labelled *Bauhinia* patch in training. The
classifier does not learn the surveyor's bias — it overrides it.

## Result 2 — the real harm is worse than the one described

**The §7.3 kill criterion is spuriously failed.**

- True Mikania-vs-native: **0.919** — clears the 0.75 threshold comfortably.
- Apparent, scored against the programme's own uncertified labels: **0.702** —
  fails it.

A programme with uncertified labels stops a project whose classifier works.
HK$1.4M spent to reach a wrong **stop** decision.

For a venture whose Phase 0 is *explicitly structured around a kill criterion*,
spurious abandonment is the more expensive of the two possible decision errors —
and it is invisible from inside, for exactly the reason Risk 9 gives, just
pointing the other way.

The residual harm the proposal does correctly identify: true false-positive rate
on native climbers is **understated by 4.7 pp** by the corrupted labels. A false
positive is a native climber cleared, which is the specific harm §2.1(b) warns
about.

## Result 3 — the cost case, honestly

| | |
|---|---|
| Certification cost, 148 vouchers | **HK$169,340** (inside the §7.3 HK$150–250k line) |
| Avoided wrong-clearance cost, 3,000 ha/yr | HK$73,483 |
| **Benefit : cost** | **0.43** |

**Below 1.** On avoided clearance cost alone, certification does not pay for
itself at this programme size. An evaluator with a calculator will find that, so
it should not be the argument.

Two costs are counted in the avoided figure: crews sent to the wrong polygon, and
the induced cost — §2.1(b) warns that clearing a native climber "may itself
create a niche for Mikania to invade", so a wrongly cleared patch is a seedbed,
not a neutral outcome. Both underlying fractions are modelled assumptions and are
reported alongside the result.

## What to sell it on instead

1. **It protects the HK$1.4M go/no-go decision.** Result 2. This is the strongest
   argument and it is not currently in the proposal.
2. **It is the auditability the client is actually buying.** §6.1(6): for a
   government client whose stated operational risk is clearing the wrong plant,
   "we can produce a barcode certificate for every specimen that trained this
   classifier" is a qualitatively different assurance from "our surveyor is
   experienced".
3. **It produces deliverable 4**, which has its own revenue line (§7.2) and
   survives even if the survey business does not.

## Recommended edit to the proposal

Replace Risk 9's mitigation text with the measured direction. Suggested:

> **Risk 9 — Training labels corrupted by field misidentification.** Impact:
> Critical. Likelihood: High if unaddressed. Uncertified labels do not flatter
> the accuracy figure — they depress it, by ~20 pp at plausible error rates,
> because the classifier overrides the surveyor's bias rather than learning it.
> The consequence is that a programme scoring against its own labels can fail the
> §7.3 kill criterion while the classifier is performing above it, and abandon a
> working method. Barcode certification gates entry to the training set (§3.4) and
> is what makes the go/no-go decision trustworthy.

## Caveats

- Pixels come from the **simulated** scenes of stage 03; error rates are
  **modelled** (§13.7). The *direction* is a structural consequence of
  independent train/test corruption and will hold in the field; the *magnitude*
  will not transfer.
- Phase 0 item 4 measures the real concordance between AFCD removal records and
  barcode identity. Until then, §13.7's `removal_record_concordance` is an
  assumption, and §14 of Appendix B is right that it "could equally reveal that
  the records are too noisy to serve as candidate-site guidance at all".
