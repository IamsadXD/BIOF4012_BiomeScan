# Biomescan platform scope

This scope follows the supplied **Biomescan Invasive Species Platform Pitch**
(combined deck v1.0, 18 slides), reviewed on 28 October 2026, and the subsequent
request to include invasive plants, animals, and harmful insects. The source
deck is maintained outside this code repository. It describes a pre-seed concept;
its budgets, pricing, coverage, and performance assumptions are not measured
service results.

## Shared platform and initial workstreams

Biomescan combines sensing hardware, classification models, validated reference
libraries, and survey delivery. Shared work includes calibration, georeferencing,
quality control, GIS packaging, model management, and repeat-survey archives.
The sensing method and evidence requirements remain specific to each target.

| Scope | Pitch reference | Repository status |
|---|---|---|
| Mikania species mapping, severity, and efficacy monitoring | Slides 2, 4, 6–7 | Implemented research demonstrator with simulated catchments. Generic VNIR model, spectral and molecular tracks, and GIS/browser outputs. Field validation remains outstanding. |
| Aedes breeding-habitat surveying | Slides 2, 4, 8–9 | Planned SWIR standing-water workstream. No water detector, depth estimator, persistence model, or Aedes validation dataset is implemented here. |
| Shared reference libraries and licensing | Slides 5, 7, 10–11 | Existing reference-database prototype. Broader seasonal field libraries and commercial licensing remain development/business work. |
| Further invasive plants, animals, and harmful insects | Deck’s extensible-target scope; later scope clarification | Intended expansion. No general animal detector or universal invasive-species classifier is implemented. |

The deck identifies an owned FS62 SWIR sensor (900–1700 nm) and the need for an
FS60-class VNIR sensor (400–1000 nm) for airborne Mikania phenotyping. Ownership
is reported by the deck, not verified by this software. The current VNIR
configuration is a simulation assumption, not evidence of available hardware.

For 白紋伊蚊 (*Aedes albopictus*), the proposed survey observes visible standing
water and potential breeding habitat. It does not observe mosquitoes, eggs, or
larvae, establish vector abundance, or replace field inspection. Concealed
containers are outside the proposed aerial observation claim. Habitat maps do
not establish species presence or infestation.

## Development gates

1. **Define the decision and buyer.** Agree on the target, location, useful map
   unit, inspection action, deliverables, and willingness to pay. Government,
   conservation, contractor, property, and farm audiences have different needs.
2. **Test observability and alternatives.** Use measured ground evidence and the
   appropriate sensor. For Aedes habitat, compare SWIR with RGB on the same
   water/confuser scenes, including depth, surface material, shade, and glint.
   The water-response and persistence ideas in the deck remain hypotheses to test.
3. **Build verified references.** Record location, season, acquisition geometry,
   and reliable identification. Use vouchers and molecular verification where
   appropriate; assess reference gaps rather than assuming certification works.
4. **Validate independently.** Hold out sites and seasons. Report false positives,
   missed detections, uncertainty, and the observations the sensor cannot make.
   Do not transfer Mikania simulation scores to new targets.
5. **Pilot before scale.** Confirm useful outputs with field teams and customers.
   Advance only if the relevant technical and commercial gates are met.

The deck’s Mikania Phase 0 proposes a roughly 75% species-versus-native accuracy
gate using verified labels. The current pipeline also reports uncertainty and
false positives; a passing simulation score does not clear a field gate. The
Aedes gate requires a substantial measured advantage over RGB in clutter and
manageable glint. Future species need their own criteria before development.

## How to interpret the existing repository

- `mikania/` remains the Python package name for compatibility. Its classes,
  genomic priors, barcode loci, severity model, and financial assumptions remain
  those of the Mikania demonstrator.
- The viewer’s scientific results and economics belong to that demonstrator.
  Rebranding does not add new species to the trained model or new survey methods.
- Existing `MIKANIA-REFDB` identifiers are retained as dataset/release provenance.
  Historical proposal section references describe the original Mikania work.
- The broader service includes mapping and surveying. Treatment/spraying drones
  are outside the deck’s current scope (slide 13).

For the original numerical findings and input provenance, see
[Mikania reference pipeline](mikania-reference-pipeline.md). The main
[README](../README.md) describes the current project and how to run it.
