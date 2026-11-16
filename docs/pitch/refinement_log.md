# Biomescan pitch: refinement log

Record of how [the pitch](biomescan_pitch.md) was iterated on 12 November 2026.
Each round critiques the current draft from one viewpoint, lists the weaknesses
found, and records the changes. Every claim was rechecked against the repository
(README, `docs/`, `config/default.yaml`, `outputs/reports/*.json`) and the lead's
sizing framework. Full earlier drafts are not kept.

## Framing decision

Three framings were considered:

1. **"Hyperspectral drones find invasive species."** Rejected: flying is a
   commodity (164 permit holders, FEHD flies its own), the repo's own figure
   shows RGB matches hyperspectral when Mikania flowers, and nothing is field-tested.
2. **"Analytics layer for other people's drones."** Partly true, but the
   standing-water detector is not built, and RGB analytics alone is easy to copy.
3. **"Evidence layer": checked labels, site-held-out testing, ranked work units
   and repeat-survey checks, with whatever sensor suits the target and season.**
   Chosen. Every part of it is already demonstrated in the pipeline on simulated
   data, it stays true whichever sensor wins, and it turns the sensor tests into
   gates instead of hidden risks. Framing 2 is kept as the fallback if RGB matches
   SWIR at Gate 1.

---

## Round 1: sceptical seed investor (critiquing version 1)

**Version 1 positioning:** "Biomescan uses hyperspectral drones and verified
reference libraries to map invasive species such as Mikania, so land managers can
target clearance and prove it worked."

**Version 1 script opening:** "Mikania micrantha, the mile-a-minute weed, is
smothering Hong Kong's hillsides. Today crews find it on foot, clear it, and have
no way to know if it comes back. Biomescan's hyperspectral drones see what the eye
misses."

**Weaknesses found**
- Leads with drones, which 164 organisations (including target customers) can
  already fly; FEHD flies its own. No reason to buy.
- "Smothering hillsides" is unsupported: the only official area is ~100 ha from
  2002, and current figures are "not available".
- "Have no way to know if it comes back" repeats a deck assertion the market
  assessment forbids (no efficacy loop exists).
- The Mikania line of the SAM is only HK$1.0–2.4M; v1 hid that most of SOM
  depends on the unbuilt standing-water workstream.
- Hyperspectral is presented as the edge, but `fig02d` shows RGB separates
  flowering Mikania as well.
- Ask was a single lump ("fund Phase 0") with no gate or stop rule.
- "Prove it worked" claims an outcome nothing has shown.

**Changes**
- Repositioned as the evidence layer; sensor chosen per target and season; the
  client's own flights accepted.
- Problem slide rebuilt on documented work (Long Valley tender, AFCD regrowth
  note, FEHD weekly-check advice); area uncertainty stated.
- Market slide shows the SAM line by line and states that SOM rests mostly on
  standing-water surveys.
- Ask split into access now, then gated money; four gates with stop/pivot rules.
- "Prove" replaced by "whether the work held".

**Positioning after:** "Biomescan is the evidence layer for invasive-species
surveys: verified references, honest validation and ranked work lists that tell
a land manager where to send a crew and whether the work held."

**Opening after:** "Flying a drone in Hong Kong is no longer special. One hundred
and sixty-four organisations hold the advanced flying permission. So Biomescan is
not selling flights; we sell evidence a manager can act on."

## Round 2: Hong Kong government land manager / contractor who would pay

**Weaknesses found**
- Price vs penalty: seven wet-season visits at the assumed HK$3,000–6,000 cost
  HK$21,000–42,000 per site, more than the HK$25,000 maximum fine. v2 implied
  fine avoidance justified the spend.
- FEHD already uses drones with 3D mapping for *concealed* stagnant water; v2 did
  not say what aerial imaging cannot see.
- "Land manager" is too vague: a contractor's site manager, a pest-control
  operator, a consultancy and AFCD buy differently. No payer or purchase route.
- Ignores existing contracts: pest-control programmes and consultancy botanists
  may already solve the problem; for AFCD the bottleneck may be clearance
  capacity, not locating.
- Outputs must fit existing tools; v2 did not say GeoJSON/GeoTIFF/CSV.
- Standing water missing from the positioning, although it carries most of SOM.

**Changes**
- Business-model slide states the price-vs-fine arithmetic and says value must
  come from saved inspection effort or client evidence (untested).
- Competition slide names walking checks, pest-control programmes,
  consultancies, in-house drones and FEHD as substitutes; "doing nothing new" is
  called the strongest one.
- Who-has-it slide uses the six-segment table with "evidence that would weaken
  the hypothesis".
- GTM targets channels that hold contracts (pest-control operators,
  consultancies); no government purchase route assumed.
- Output formats added; concealed containers listed as out of scope.
- Positioning names both targets and the client's own flights.

**Positioning after:** "Biomescan turns survey imagery, including flights a
client already commissions, into checked evidence for land managers: where an
invasive plant or standing water is, which spots a crew should visit first, and
whether the work held."

**Opening after:** "Flying a drone in Hong Kong is no longer special. One hundred
and sixty-four organisations hold the advanced flying permission, and the
government's hygiene department already flies its own drones to find stagnant
water. So Biomescan is not selling flights."

## Round 3: remote-sensing scientist checking every claim against the repo

**Weaknesses found**
- v3 quoted leave-one-site-out 80.4% as the headline without its 95% CI
  (50.8–98.0%, three training sites), whose lower bound fails the 75% gate.
- Foliage-only hyperspectral (68.7%) is itself below the 75% gate even in
  simulation; v3 presented it only as a win over RGB (53.1%).
- "Verified reference libraries" in present tense: the repo has a database design
  and a *rehearsal* release (8 certified, 14 quarantined) built from real
  sequences with simulated read damage and synthetic voucher pairing; reference
  spectra are modelled endmembers.
- The Botswana benchmark (93.7% random vs 58.9% blocked) validates the testing
  method, not Mikania detection; v3 blurred this.
- "Standing water" in the positioning should be "visible standing water"; SWIR
  advantage over RGB is a hypothesis, and FS62 ownership is deck-reported only.
- Missing known limits: seasonal drift (49% / 63% on hold-outs), 18% sub-canopy
  occlusion, *M. cordata* uncertifiable from public barcodes, rbcL identical
  between the two *Mikania* species.
- Change detection is simulated, with a 0.02 ha detection floor; re-emergence
  measured below true rates.

**Changes**
- Evidence slide split into real inputs, simulated results (with CI and the gate
  failures) and "not shown".
- Library described as "designed so every training label is checked"; rehearsal
  status stated.
- Botswana result described as a test of the evaluation method.
- "Visible" added to positioning; SWIR-vs-RGB moved into Gate 1 with an RGB
  pivot; hardware access listed as an ask.
- Risks slide carries drift, occlusion, barcode gaps and label-error risk.
- Script now says the result is below the 75% bar and that RGB is as good in bloom.

**Positioning after:** "Biomescan turns survey imagery, including flights a
client already commissions, into checked evidence for land managers: where an
invasive plant or visible standing water is, which spots a crew should visit
first, and whether the work held."

**Opening after:** unchanged from round 2 except "including construction firms we
hope to serve" was added after "advanced flying permission", so the commodity
point lands on target customers.

## Round 4: course assessor grading clarity and honesty

**Weaknesses found**
- Script 479 words, over the 420–460 target; 30-second version 98 words, too long
  to say in 30 seconds.
- Jargon in the spoken text ("leave-one-site-out", "VNIR", "SAM") and too many
  numbers to follow by ear.
- Some slide headlines were topics ("Market", "Evidence"), not takeaways.
- The ask had no figure and no note on where any figure came from; the team slide
  needed explicit placeholders and named gaps.
- One script sentence was ungrammatical after editing; the regrowth point was
  unclear.
- "Every number traceable" needed checking: the 75% gate, HK$1.4M and 0.42 come
  from the repo; the HK$21,000–42,000 range is arithmetic on the sizing assumptions.

**Changes**
- Script trimmed to 457 words and kept to about a dozen spoken numbers, all rounded
  from the slides; 30-second version cut to 88 words.
- Plain wording in speech ("hyperspectral camera", "ordinary colour camera",
  "the usual way of testing").
- Every headline rewritten as a takeaway sentence.
- Stage 2 ask cites the repo's modelled HK$1.4M over 10 months, labelled as
  modelled and to be replaced by quotes; stage 1 cash left as a placeholder because
  no quotations exist.
- Team slide uses [Member A–D] placeholders and lists missing roles.
- "Simulated scenes – not field results" footer specified for demonstrator slides.

**Positioning after:** unchanged from round 3.

**Opening after:** "Flying a drone in Hong Kong is no longer special. One hundred
and sixty-four organisations hold the advanced flying permission, including
construction firms we hope to serve, and the government's hygiene department
flies its own drones to find stagnant water. So Biomescan is not selling
flights." (Wording simplified; the next paragraph now opens "We build the hard
part: evidence a manager can act on.")

## Round 5: all four critics re-read the final draft

**Investor:** the strategic weaknesses (commodity flying, small Mikania market,
unbuilt standing-water revenue, no WTP) are each stated with a gate. No material
weakness. Weak spot accepted rather than fixed: the stage-1 cash amount is a
placeholder until quotes exist.

**Land manager / contractor:** price-vs-fine, concealed water, existing
contracts and the RGB-on-own-drone option are covered. No material weakness.

**Remote-sensing scientist:** each number checked against `outputs/reports/` and
the docs (68.7/53.1, 7.9/13.5, 80.4 with 50.8–98.0, 93.7/58.9, 49/63, 18%,
8/14, 185, 1,107, 242, 0.42). No material weakness. Not fixable from the repo: Gate 1 has
no numeric threshold because the repo specifies only "a substantial measured
advantage over RGB"; the pitch says the threshold will be fixed before testing.

**Assessor:** all required sections present; 12 slides with headline, 2–4 points,
visual and speaker note; script 457 words; eight questions with two- or
three-sentence answers. No material weakness.

Iteration stopped here.

## Summary of positioning lines

| Version | Positioning line |
|---|---|
| v1 | Biomescan uses hyperspectral drones and verified reference libraries to map invasive species such as Mikania, so land managers can target clearance and prove it worked. |
| v2 | Biomescan is the evidence layer for invasive-species surveys: verified references, honest validation and ranked work lists that tell a land manager where to send a crew and whether the work held. |
| v3 | Biomescan turns survey imagery, including flights a client already commissions, into checked evidence for land managers: where an invasive plant or standing water is, which spots a crew should visit first, and whether the work held. |
| v4–final | Same as v3 with "visible standing water". |
