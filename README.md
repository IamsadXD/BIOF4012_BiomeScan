# Biomescan

**Invasive species mapping and surveying, supported by hyperspectral sensing,
verified reference libraries, and GIS.**

Biomescan develops surveys that help land managers locate invasive species,
prioritise inspections and control work, and assess changes after treatment.
The platform’s scope includes invasive plants, animals, and harmful insects,
with sensing and field verification selected for each target. Mikania is the
first reference demonstrator, within a broader surveying platform.

The updated platform concept combines sensor hardware, classification models,
and validated, geographically linked reference libraries. Drones carry the
sensors; shared calibration, survey operations, GIS delivery, and data management
support each service. The initial focus is Hong Kong, with further markets and
species subject to local validation.

> **Current status:** this repository contains a runnable Mikania research
> demonstrator. Its five survey scenes and treatment outcomes are simulated.
> Aedes breeding-habitat mapping and additional plant, animal, and insect surveys
> are planned workstreams, not implemented or field-validated capabilities.

## Survey scope

| Workstream | Survey question and intended outputs | Method and current status |
|---|---|---|
| Invasive plants: Mikania first | Where are infestations, how severe are they, and where should crews work? Species maps, abundance estimates, ranked work units, and repeat-survey change layers. | VNIR hyperspectral imaging, reference spectra, and voucher/DNA verification. Implemented as the reference demonstrator with simulated survey scenes; real canopy separability remains to be validated. |
| Harmful insects: Aedes habitat first | Where is visible standing water that warrants inspection for breeding risk? Planned habitat polygons, inspection priorities, and persistence/change layers. | Planned SWIR water measurements with ground checks and an RGB comparison. Targets breeding habitat associated with 白紋伊蚊 (*Aedes albopictus*); does not detect or count mosquitoes, larvae, or eggs. |
| Further invasive plants and animals | Which species, occurrences, or habitat indicators can be surveyed reliably at a useful cost? | Roadmap. Each target needs a suitable sensing or field method, reference data, and independent validation. The Mikania model does not establish animal or other insect detection. |

The concept deck identifies an owned FS62 SWIR sensor (900–1700 nm) for the
Aedes habitat workstream and a required FS60-class VNIR sensor (400–1000 nm)
for airborne Mikania work. The repository models a generic VNIR sensor; it does
not demonstrate operation of either physical instrument. One sensor or spectral
library cannot be assumed to identify every invasive species.

## Who the service is for

- Government departments and conservation managers: survey planning, species
  confirmation, prioritisation, and monitoring of control work.
- Environmental groups, ecology consultancies, and land managers: repeatable
  baseline maps and evidence for site management.
- Contractors and property managers: planned standing-water habitat surveys to
  guide inspections and clearance.
- Farmers and farm managers: target-specific weed or pest survey pilots where
  field size, inspection costs, and survey value justify the service.

AFCD is an intended stakeholder for the Mikania workstream; contractors and
FEHD are intended stakeholders for the Aedes habitat workstream. These are
target users and buyers, not claims of contracts, endorsement, or validated demand.

## Deliverables and business model

The current demonstrator produces classified and abundance rasters, severity
maps, prioritised treatment units, and simulated post-treatment change layers.
Outputs include GeoTIFF, GeoJSON, CSV, JSON reports, and a local browser viewer.
A versioned reference database links the molecular and spectral workstreams.

The broader service model combines baseline surveys, repeat monitoring,
target-specific verification, and licensing of validated reference data or
platform tools. The Aedes workstream would add habitat maps and ranked
inspection lists. Pricing, coverage, and financial figures in the concept deck
are modelling assumptions pending field and customer validation. Figures shown
in the current economics viewer apply to the Mikania demonstrator.

Biomescan’s proposed long-term asset is the curated link between specimens or
ground observations, spectra, location, season, and repeat-survey history.
Surveys support decisions by field teams; a habitat risk layer does not confirm
mosquito presence. Treatment and spraying drones are outside the current scope.

## Quick start

Run from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run_all.sh
.venv/bin/python platform/server.py
```

Open <http://127.0.0.1:8790>. To view the checked-in demonstration outputs,
install the dependencies and start the server; regenerating all stages is optional.

The full pipeline downloads open data on its first run. Useful options:

```bash
./run_all.sh --fast          # skip the contrast sweep
./run_all.sh --no-fetch      # reuse cached data
./run_all.sh --no-molecular  # run the spectral track without the molecular stages
```

Use `BIOMESCAN_PORT` to change the server port. `MIKANIA_PORT` remains supported
for existing setups. The Python package is still named `mikania` so existing
imports, scripts, and saved models continue to work.

## What is implemented

The Mikania demonstrator contains two connected tracks:

| Stages | Work |
|---|---|
| 00 | Genomic desk study and falsifiable spectral predictions |
| 01–02 | Open-data retrieval, spectral library, and sensor/separability comparisons |
| 03–05 | Simulated survey scenes, site-disjoint model validation, and contrast sensitivity |
| 06–07 | Mapping, abundance, severity, work planning, and simulated efficacy re-flights |
| 08 | Independent pipeline benchmark on real Botswana Hyperion imagery |
| 10–14 | Genomic prediction checks, public barcode references, voucher-verification experiments, label-error analysis, and reference database |
| 16 | Experiments testing remedies for limitations identified by the molecular track |
| 15, run last | Export of the browser platform bundle |

The product workspace adds persistent species-profile switching, a map explorer,
a searchable visual reference library, a survey portfolio, a browser-local field
shortlist with CSV exports, and a monitoring view. Planned species profiles are
clearly separated from the Mikania reference results. For a presentation route
and data boundaries, see the [product demo walkthrough](docs/product-demo.md).

The browser presents survey layers, spectra, validation results, work plans,
efficacy, economics, molecular evidence, and provenance. It displays existing
pipeline outputs; its only live scientific calculation is the server’s coverage
economics endpoint.

```text
repository root/
├── README.md
├── config/           Mikania demonstration settings and genomic priors
├── mikania/          existing Python implementation
├── scripts/          spectral and molecular pipeline stages
├── platform/         local server, viewer, and checked-in demonstration bundle
├── data/             source data, reference library, and simulated scenes
├── outputs/          reports, figures, models, and GIS deliverables
└── docs/             scope, implementation, findings, and provenance
```

## Evidence and validation limits

Real inputs include Hong Kong occurrence records from GBIF, measured tropical
leaf spectra from EcoSIS, the Botswana Hyperion benchmark, and public barcode
reference sequences. The Hong Kong survey scenes, species spectral contrasts,
infestation geometry, treatment outcomes, and re-flights are modelled. The
barcode experiments also use simulated read degradation and synthetic voucher
groupings of real sequences.

Accuracy figures from simulated scenes describe the demonstrator under its
assumptions. They are not field accuracy claims for Hong Kong, evidence of Aedes
habitat detection, or results for other species. The Botswana benchmark tests
the analysis machinery on real imagery; it does not validate Mikania detection.

The original work also identified seasonal sensitivity, spatial leakage,
reference-sequence gaps, and limitations in genomic band priors. Those findings
remain available in the [detailed reference results](docs/mikania-reference-pipeline.md)
and [findings against the original proposal](docs/09_findings_vs_proposal.md).

Each new workstream must establish its own ground truth, compare appropriate
cheaper methods, and validate on independent sites and seasons before service
performance is claimed. For Mikania this requires real canopy spectra, verified
labels, and access to suitable VNIR hardware. For Aedes habitat it requires
water/confuser measurements, ground checks, and a SWIR-versus-RGB benchmark.

## Documentation and next steps

- [Platform scope and development gates](docs/platform-scope.md): alignment with
  the updated Biomescan pitch and the boundary between implemented and planned work.
- [Mikania reference findings and provenance](docs/mikania-reference-pipeline.md):
  the detailed results previously in this README.
- [Documentation index](docs/README.md): implementation, field/library workflow,
  barcode procedures, database design, and limitations.
- [Phase 0 runbook](docs/07_phase0_runbook.md): the existing Mikania validation plan.
- [Data provenance manifest](data/raw/PROVENANCE.json) and
  [open-data register](docs/06_open_data_register.md): sources and reuse conditions.

The next development steps are to test the Aedes water/confusion set against
RGB, collect seasonal Mikania ground spectra and verified vouchers, secure VNIR
access, and validate paid pilot demand before expanding operations. Further
species should enter through the same evidence gates, with methods selected for
their biology and survey setting.
