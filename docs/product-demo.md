# Biomescan product demonstrator

## Open the workspace

From `biomescan/`, run `python3 platform/server.py` and open
<http://127.0.0.1:8790>. The checked-in bundle supports the product demo without
regenerating the pipeline. The web interface has no build step, CDN, online map
tiles, external fonts or JavaScript dependencies. Install the Python requirements
for live coverage economics; without them, that view displays the bundled baseline
and disables live sliders with an explanation.

## Suggested walkthrough

1. **Overview:** introduce the programme, mapped infestation, survey sites and
   reference collection. All cards use the checked-in Mikania pipeline bundle.
2. **Species profiles:** switch between Mikania, the proposed Aedes habitat
   programme and the expansion roadmap. The active profile persists in this
   browser. Planned programmes have their own methods and empty states; they
   never inherit Mikania detections, spectra or validation results.
3. **Map explorer:** select one of five sites on the map or site strip. Switch
   to GBIF occurrence context, zoom and drag the overview, then inspect RGB,
   classification, severity, change and simulation ground-truth layers. Open
   the original pixel spectrum inspector or download georeferenced GIS outputs.
4. **Reference library:** search nine signatures, filter vegetation/background
   materials and select a signature to compare with host canopy. Download the
   121-band library as CSV. Open the barcode and versioned-release evidence.
5. **Survey portfolio:** browse the five scenes and their seasons and hold-out
   status, then open any survey in the map explorer.
6. **Work planner:** filter by site, priority or unit ID. Check units to create
   a field shortlist; selections persist locally. Export the complete work plan
   or selected units as CSV. No crews are assigned or contacted.
7. **Change & monitoring:** choose a site, compare the baseline classification
   with the simulated repeat-survey change layer and review site-level outcomes.
8. **Evidence room:** access the original scientific views, including sensor
   evidence, validation, molecular work, reference releases and provenance.

## Data boundaries

- Mikania scenes, species contrasts, treatment and repeat surveys are simulated.
- GBIF occurrences, measured source leaf spectra and public barcode sequences
  come from the original repository's real open-data inputs. Historical GBIF
  records do not establish current infestation extent.
- The territory overview is an offline schematic, with markers projected from
  repository centroids. Its illustrative coastline is not a geographic basemap.
  Use the existing EPSG:4326 GeoTIFF/GeoJSON downloads for survey geometry.
- Reference species signatures are hybrid/modelled endmembers; they are not
  measured, species-certified Hong Kong canopy spectra. Voucher certification
  belongs to the repository's rehearsal release.
- Aedes is a planned visible-standing-water habitat workflow. It does not detect
  mosquitoes, eggs or larvae. The expansion profile is a roadmap, not an animal
  or universal species detector.
- Profile preference and field shortlist use browser-local storage. They are not
  an account, shared project store or field operations system.

## Interface structure

`platform/ui/index.html` contains the persistent shell; `product.js` provides
product navigation, profile-scoped views and local interactions; `product.css`
provides responsive presentation. `app.js` retains the original research views
and scientific bundle rendering, with `styles.css` as their base layout. Backend
science, source data and pipeline output files are unchanged.
