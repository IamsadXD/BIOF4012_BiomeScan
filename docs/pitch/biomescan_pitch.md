# Biomescan pitch (pre-seed, BIOF4012/BBMS4012)

Prepared 12 November 2026. Final version after five critique rounds; see
[refinement log](refinement_log.md). Sources: the repository docs and outputs,
and the lead's sizing framework (TAM/SAM/SOM, pricing assumptions and Hong Kong
context figures). Team members appear as role placeholders.

**Status in one line:** a runnable Mikania research demonstrator on *simulated*
survey scenes, plus a browser platform. Nothing is field-validated. The
standing-water workstream is planned, not built. No customer has agreed to pay,
and the repository records no completed discovery interviews.

---

## Positioning line

Biomescan turns survey imagery, including flights a client already commissions,
into checked evidence for land managers: where an invasive plant or visible
standing water is, which spots a crew should visit first, and whether the work
held.

## 30-second version

Flying a drone in Hong Kong is routine: 164 organisations hold advanced
operating permission, and the government's hygiene department flies its own.
What is missing is evidence a manager can act on. Biomescan builds it: maps
trained on specimen-checked labels, tested on sites the model has never seen, a
ranked list of where to send a crew, and a repeat survey showing whether the work
held. Our Mikania pipeline runs on simulated scenes; nothing is field-tested.
We ask for access first, and funding only after each test passes.

---

## 3-minute spoken script

*(457 words; about 3 minutes at 150 words a minute.)*

Flying a drone in Hong Kong is no longer special. One hundred and sixty-four
organisations hold the advanced flying permission, including construction firms
we hope to serve, and the government's hygiene department flies its own
drones to find stagnant water. So Biomescan is not selling flights.

We build the hard part: evidence a manager can act on. Two jobs show the gap.
Government contracts already pay crews to remove Mikania, a fast-growing
invasive vine, and regrowth can mean clearing the same site again. Yet the government
says current figures for its area are not available. The last estimate, from
2002, is about one hundred hectares. Construction sites are advised to check for standing water at least weekly, and in the first
eight months of 2025 there were ninety-five construction-site prosecutions for
mosquito breeding.

Our service takes imagery, from our sensor or the client's own drone, and
returns three things: a map of the target, a ranked list of work units telling a
crew where to go first, and a repeat survey that shows whether the work held.
Behind each map sits a reference library designed so every training label
is checked against a specimen, by DNA barcode where needed, and tied to its
spectrum, place and season.

What is real today: a working research pipeline and browser platform for
Mikania. Its five survey scenes are simulated, not flown. On them,
a hyperspectral camera beat an ordinary colour camera when the vine is not
flowering: sixty-nine per cent against fifty-three, with fewer native
plants wrongly flagged. That is still below our own seventy-five per cent bar.
When the vine flowers, an ordinary camera works just as well, and we say so. On
real satellite imagery, we showed that the usual way of testing these models
overstates accuracy: ninety-four per cent against fifty-nine. Nothing has been
tested in the field. Our standing-water work is planned, not built, and it looks
only for visible water, never mosquitoes or larvae.

On stated assumptions, the Hong Kong market we could serve is eight and a half
to eighteen million Hong Kong dollars a year, and a realistic year-three share is
half a million to one point two million. No one has agreed to pay yet.

So our ask is staged. First, access: interviews with site and park managers,
clearance records, a field spectrometer, and two or three sites for a water test
against an ordinary camera. Each stage has a stop rule. If field spectra cannot
separate Mikania from native climbers, we stop before buying aerial equipment. If
an ordinary camera finds water as well as the infrared one, we use ordinary
cameras. Next-stage money follows only a passed test.

Biomescan: know where to send the crew, and whether the work held.

---

## Slide outline (12 slides)

Every figure named below is in `outputs/figures/`; every view is in the browser
platform (`python3 platform/server.py`, then <http://127.0.0.1:8790>). Show the
footer "Simulated scenes – not field results" on every slide that carries a
demonstrator number.

### 1. Problem: managers pay for clearance and inspection, but lack checked evidence of where to act and whether it held

- Mikania clearance is recurring contracted work; AFCD notes regrowth can need
  repeat clearing, and the 2024 Long Valley maintenance tender includes removing
  Mikania identified by the government representative.
- No current official Mikania area exists: about 100 ha affected (2002), 4.3 ha
  cleared by all departments (2012); area statistics are "not available".
- FEHD advises construction sites to check for standing water at least weekly;
  95 construction-site prosecutions for mosquito breeding, January–August 2025.
- Whether *better location evidence* changes decisions is our central untested
  hypothesis.
- **Visual:** two-column text slide, "Mikania" and "Standing water", each with
  "work already paid for" and "what is not known".
- **Speaker note:** "The work already exists; what we must prove is that better
  evidence changes where crews go."

### 2. Who has the problem: six buyer types, each already solving it another way

- Construction contractors and pest-control operators: weekly walking checks,
  in-house drones, existing pest-control contracts.
- Ecology consultancies: botanist surveys plus GIS within a client-funded scope.
- AFCD and habitat-site managers: term contracts, crews identify and remove
  Mikania on site.
- Property managers and conservation groups: staff inspections; budgets
  uncertain.
- **Visual:** the segment table from `docs/customer-discovery/market_assessment.md`
  (job, payer, evidence that would weaken the hypothesis).
- **Speaker note:** "Our competitor in every segment is the way they do it now,
  and some of it may already work."

### 3. Solution: three outputs a crew can use – a map, a ranked work list, and a repeat-survey check

- Target map with uncertainty, delivered as GeoTIFF, GeoJSON and CSV.
- Ranked work units: where to send a crew first, exportable as a field shortlist.
- Repeat survey: change layer showing cleared, regrown and new patches.
- Imagery can come from our sensor or the client's own flights; the sensor is
  chosen per target and season.
- **Visual:** platform **Work planner** then **Change & monitoring**;
  `fig06_deliverables.png`.
- **Speaker note:** "We sell the decision, not the flight; every map shown here
  is from a simulated scene."

### 4. How it works: checked labels in, honestly tested model, decision-ready outputs out

- Reference library links each label to a specimen or ground check, DNA
  barcode where needed, spectrum, location and season; uncertain labels are
  quarantined.
- Models are tested only on held-out sites and seasons, never on random pixels
  from the training area.
- Each survey reports false positives, missed detections and what the sensor
  cannot see (e.g. sub-canopy vine; concealed containers).
- **Visual:** pipeline diagram (reference → model → map → work units → repeat
  survey); platform **Reference library**; `fig14_reference_db.png`.
- **Speaker note:** "The discipline is the product: a map is only as good as the
  labels and the test behind it."

### 5. Evidence: the method runs end to end on simulated scenes; the field question is still open

- Real inputs: 1,107 GBIF records in Hong Kong, 242 measured leaf spectra, 185
  public barcode sequences, a real Botswana Hyperion scene.
- Simulated Mikania scenes, foliage only: hyperspectral 68.7% vs RGB 53.1%
  Mikania-vs-native; false positives 7.9% vs 13.5%. Below the 75% gate. In
  bloom, all sensors separate it.
- Leave-one-site-out 80.4%, 95% CI 50.8–98.0% (three training sites): the lower
  bound fails the gate. Real Hyperion: random split 93.7% vs spatially blocked
  58.9%.
- Barcode rehearsal (real sequences, simulated read damage and voucher pairing):
  8 certified, all correct; 14 quarantined. Not shown: real Hong Kong canopy
  separability; anything for standing water.
- **Visual:** `fig02d_seasonal_sensor_ablation.png` and
  `fig08_benchmark_botswana.png`; platform **Evidence room** provenance page.
- **Speaker note:** "These numbers describe our pipeline under assumptions, not
  Hong Kong; the field campaign decides whether there is a product."

### 6. Market: a small Hong Kong niche on our assumptions – HK$8.5–18.0M a year serviceable, HK$0.5–1.2M obtainable by year 3

- TAM (HK + Guangdong, every eligible unit buys): HK$108–245M a year (about
  US$14–31M). 1,602 HK construction sites × 7 visits × HK$3,000–6,000; 44,842 ha
  HK country parks and special areas × HK$500–1,200/ha; 34,500 ha Guangdong
  forest with Mikania × 3 search multiple (assumption) × HK$500–1,200/ha
  (mainland prices likely lower).
- SAM (HK, services the current design could deliver): HK$8.5–18.0M. 261
  large+medium construction sites (5.5–11.0M); ~40 consultancy mapping
  projects (1.2–3.2M); AFCD habitat contracts × 3–5% survey share (0.84–1.41M);
  Mikania hotspots, ~100 ha (2002) × 10 search multiple × 2 surveys
  (1.0–2.4M).
- SOM (year 3): HK$0.5–1.2M: 13 construction sites, 4–6 consultancy projects,
  1 habitat-site pilot.
- All prices are assumptions; no willingness to pay is validated. Most of SOM
  depends on the standing-water workstream, which is not built.
- **Visual:** three stacked bars (TAM, SAM, SOM) with every multiplier printed
  beside its segment and "ASSUMPTION" tags on prices and shares.
- **Speaker note:** "We show the arithmetic so you can change any assumption you
  disagree with."

### 7. Competition: flying is a commodity, so we compete on evidence, and the strongest substitute is doing nothing new

- In-house and contracted drones: 164 CAD Advanced Operations Permission
  holders, including Gammon, Hip Hing, Build King, Urban and Savills; FEHD flies
  its own drones with 3D mapping for concealed stagnant water.
- Walking inspections and pest-control programmes (e.g. Rentokil) may already
  solve the problem economically.
- Ecology consultancies supply botanists and GIS; published RGB deep learning
  already finds flowering Mikania.
- Our difference: checked labels, site-held-out testing, stated blind spots and
  repeat-survey checks, usable on others' imagery. It is a method, not yet a
  moat; the moat would be a Hong Kong reference library that does not yet exist.
- **Visual:** 2×2 grid, axes "who flies" (client / us) × "evidence checked"
  (no / yes), substitutes placed honestly.
- **Speaker note:** "If a contractor's own drone plus our analysis is enough, that
  is a cheaper product, not a loss."

### 8. Business model: per-survey and per-project fees, repeat surveys built in – all prices are assumptions to test

- Vegetation survey HK$500–1,200 per hectare (repo modelling assumption; no
  public HK price found).
- Standing-water site survey HK$3,000–6,000 per visit (assumption). Seven
  wet-season visits cost HK$21,000–42,000 per site, against a maximum fine of
  HK$25,000 (+HK$450/day), so value must come from saved inspection time or
  client evidence, not fine avoidance. Untested.
- Consultancy mapping subcontract HK$30,000–80,000 per project (assumption).
- Flights subcontracted to permit holders or supplied by the client; reference
  data licensing is a later option, not a current revenue line.
- **Visual:** platform **Map explorer** with GeoTIFF/GeoJSON download; a price
  table stamped "ASSUMPTION".
- **Speaker note:** "Interviews will test these prices against what buyers
  already spend on inspection."

### 9. Go-to-market: problem interviews first, through channels that already sell to site managers

- Six-week plan from 2 November 2026: 30 prospects (construction, pest control,
  ecology consultancies, property, 8 farms), problem-first emails, consent
  materials drafted; no interviews are recorded in the repo.
- Evidence ladder: a specific recent event, how often it recurs and what it
  costs → a named budget owner and purchase route → an agreed evaluation scope →
  paid repeat work.
- Likely channels: pest-control operators and ecology consultancies, who already
  hold the client contracts.
- Government (AFCD, FEHD) as stakeholders and data holders; no purchase route
  assumed.
- **Visual:** the weekly table from `docs/customer-discovery/outreach_plan.md`
  and the evidence ladder.
- **Speaker note:** "Compliments and interest in drones count as weak evidence;
  we are looking for a budget owner."

### 10. Roadmap: four gates, each able to stop or redirect us before money is spent

- Gate 0, discovery (by mid-December 2026): continue a segment only with a
  recurring, costly locating or checking problem and a known budget owner.
- Gate 1, standing water: SWIR vs RGB on the same water and look-alike scenes
  (depth, surface, shade, glint), threshold fixed before testing. If RGB is
  as good, build RGB analytics for clients' own drones.
- Gate 2, Mikania: field spectra in two seasons must reach the required contrast
  (≈0.42 on the stage-05 scale, ~75% Mikania-vs-native) on barcode-certified
  validation labels, before any aerial spend.
- Gate 3, paid pilot: an agreed evaluation scope, then paid repeat work, before
  scaling operations.
- **Visual:** gate flowchart with stop/pivot arrows; `fig05_contrast_sweep.png`.
- **Speaker note:** "Each gate has a written stop rule, and a negative result is
  a result."

### 11. Team needs and the ask: access now, money only behind passed gates

- Team (placeholders): [Member A – bioinformatics and ML pipeline],
  [Member B – customer discovery and commercial], [Member C – field ecology and
  vouchers], [Member D – GIS and platform].
- Gaps: field spectroscopy / remote-sensing adviser, botanist for herbarium
  material, molecular lab access in writing, a licensed drone operator partner.
- Ask, stage 1 (now): introductions to site and park managers; AFCD clearance
  records and herbarium access; loan of a field spectroradiometer and VNIR
  access; two or three sites for the water test. Cash: [amount from quotations,
  not yet obtained].
- Ask, stage 2 (only if Gates 0–2 pass): the Mikania field phase, modelled in the
  original proposal at HK$1.4M over 10 months (a modelled figure, to be
  replaced by real quotes).
- **Visual:** a two-row ask table (stage, what, gate that releases it).
- **Speaker note:** "We are not asking anyone to fund aircraft or sensors before
  the field test says they are needed."

### 12. Risks: the biggest risks are biological and commercial, and each has a test

- Mikania may not be separable from native climbers outside bloom (Gate 2);
  accuracy drops to 49% and 63% on dry- and wet-season hold-outs in simulation.
- Buyers may not pay more than walking checks cost; FEHD and contractors fly
  their own drones (Gate 0, Gate 3).
- Reference gaps: native *Mikania cordata* cannot be certified from public
  barcodes, and rbcL cannot separate it from *M. micrantha*.
- Unseen targets: sub-canopy vine (18% occluded in simulation) and concealed
  containers are outside what aerial imaging can claim; uncertified labels can
  produce a wrong stop decision.
- **Visual:** risk table (risk, evidence so far, test, gate).
- **Speaker note:** "We would rather find a fatal flaw in three months than after
  buying equipment."

---

## Anticipated questions

**1. Contractors and FEHD already fly drones. Why would anyone need you?**
Because flying is not the hard part; knowing whether a map is right is. We aim
to supply checked labels, site-held-out testing and repeat-survey checks that
can run on imagery a client already collects. If interviews show their current
inspections already work, we will stop that segment.

**2. Every accuracy number you have is simulated. Why should we believe any of it?**
You should not treat it as field performance, and we do not. The simulation
shows the pipeline runs end to end and tells us how much real spectral
difference we need (about 0.42 on our contrast scale); the real-imagery
benchmark shows our testing method catches inflated accuracy. The first funded
step is the field measurement that could prove us wrong.

**3. If an ordinary camera finds flowering Mikania, why hyperspectral?**
In our simulation it only helps outside bloom, and even there it reaches 68.7%,
below our 75% bar. We choose the sensor per target and season; if RGB is enough,
we use RGB, which is cheaper for everyone. The service is the checked evidence,
not a particular camera.

**4. Hong Kong's Mikania problem may be about 100 hectares. Is there a business here?**
Possibly not on Mikania alone: that line is HK$1.0–2.4M of a HK$8.5–18.0M
serviceable market, and the area figure dates from 2002. Most of our assumed
near-term revenue is standing-water surveys on construction sites and
consultancy mapping, and both need to be confirmed in interviews. Guangdong is a
larger possible market but is not part of our near-term plan.

**5. A wet season of surveys could cost a contractor more than the maximum fine. Who pays, and has anyone said yes?**
Nobody has said yes; the repository records no completed interviews. Our
assumed seven visits cost HK$21,000–42,000 against a HK$25,000 maximum fine, so
fine avoidance alone will not justify it. The value would have to come from
fewer repeat inspections or evidence a client demands, and Gate 0 tests exactly
that.

**6. What stops someone copying you?**
Today, very little: the method is published practice applied with discipline.
The defensible asset would be a Hong Kong reference library linking checked
specimens, spectra, places, seasons and repeat-survey history, which takes field
seasons to build. It does not exist yet; we have the database design and a
rehearsal release.

**7. Can you detect mosquitoes, or the water that actually matters?**
No. The planned survey looks only for visible standing water and never detects
mosquitoes, eggs or larvae. Concealed containers are outside what we claim, and
FEHD's own drone work already targets concealed water, so we must show visible
water is worth surveying.

**8. How much money do you want, and what happens if the gates fail?**
Stage 1 is mainly access, with a small cash amount we will set from real quotes.
Stage 2, the Mikania field phase, was modelled at HK$1.4M over 10 months and is
released only if discovery and field tests pass. If Gate 2 fails we stop
Mikania before aerial spend; if RGB matches SWIR we pivot to RGB analytics.
