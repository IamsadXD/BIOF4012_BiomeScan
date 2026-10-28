#!/usr/bin/env bash
# =============================================================================
# Biomescan — run the whole pipeline, stage 00 to 15.
#
#   ./run_all.sh              full run (downloads ~85 MB of open data once)
#   ./run_all.sh --fast       skip the contrast sweep (stage 05), the slow one
#   ./run_all.sh --no-fetch   reuse cached downloads
#   ./run_all.sh --no-molecular   spectral stages only (v1.0 scope)
#
# Two tracks, run in dependency order:
#
#   00        the genomic desk study — proposal Next Action 0. Needs no data,
#             no capital and no counterparty, which is exactly why it is first.
#   01-08     the spectral track (v1.0).
#   10-14,16  the molecular track (v2.0): predictions tested against the library,
#             real barcode references, voucher certification, label-error
#             propagation, the reference database, and stage 16, which tests the
#             FIXES for the three proposal claims stages 10-13 falsify.
#   15        assembles the browser bundle from everything above, so it is
#             always last by construction rather than by numbering.
#
# Each stage is idempotent, so a failed run can be resumed by invoking the
# remaining scripts directly.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

FAST=0; NO_FETCH=0; NO_MOL=0
for a in "$@"; do
  case "$a" in
    --fast) FAST=1 ;;
    --no-fetch) NO_FETCH=1 ;;
    --no-molecular) NO_MOL=1 ;;
    *) echo "unknown flag: $a"; exit 2 ;;
  esac
done

step () {
  echo ""
  echo "═══════════════════════════════════════════════════════════════════════"
  echo "  $1"
  echo "═══════════════════════════════════════════════════════════════════════"
}

START=$(date +%s)

step "00  Genomic desk study — ranked, falsifiable spectral predictions"
$PY scripts/00_genomic_desk_study.py

if [ "$NO_FETCH" -eq 0 ]; then
  step "01  Fetch open data — GBIF, EcoSIS, EO-1 Hyperion"
  $PY scripts/01_fetch_open_data.py
fi

step "02  Spectral library and pre-flight separability audit"
$PY scripts/02_build_spectral_library.py

step "03  Simulate Tier-2 survey scenes"
$PY scripts/03_simulate_scenes.py

step "04  Train and validate (leave-one-site-out)"
$PY scripts/04_train_validate.py

if [ "$FAST" -eq 0 ]; then
  step "05  Accuracy vs species separability (contrast sweep)"
  $PY scripts/05_contrast_sweep.py
else
  echo ""
  echo "── 05  contrast sweep SKIPPED (--fast)"
fi

step "06  Classify, unmix, score severity, build the work plan"
$PY scripts/06_map_and_prioritise.py

step "07  Post-treatment efficacy re-flight"
$PY scripts/07_efficacy_reflight.py

step "08  Real hyperspectral benchmark (Botswana)"
$PY scripts/08_benchmark_real_hsi.py

if [ "$NO_MOL" -eq 0 ]; then
  step "10  Falsify the genomic predictions against the spectral library"
  $PY scripts/10_test_genomic_predictions.py

  step "11  Fetch real barcode references (NCBI, BOLD)"
  if [ "$NO_FETCH" -eq 1 ]; then
    $PY scripts/11_fetch_barcode_references.py --offline
  else
    $PY scripts/11_fetch_barcode_references.py
  fi

  step "12  Barcode verification against a known answer key"
  $PY scripts/12_barcode_verify_vouchers.py

  step "13  Label-error propagation and the value of certification"
  $PY scripts/13_label_error_propagation.py

  step "14  Reference database — build, version, value"
  $PY scripts/14_reference_database.py

  step "16  Remediation — test the fixes for what stages 10-13 found"
  $PY scripts/16_remediation.py
else
  echo ""
  echo "── 10-14  molecular track SKIPPED (--no-molecular)"
fi

step "15  Assemble the platform bundle"
$PY scripts/15_export_platform.py

ELAPSED=$(( $(date +%s) - START ))
echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "  Pipeline complete in ${ELAPSED}s"
echo ""
echo "  Reports      outputs/reports/*.json"
echo "  Figures      outputs/figures/*.png"
echo "  Deliverables outputs/deliverables/   (GeoTIFF, GeoJSON, CSV)"
echo "  Reference DB data/processed/reference_db.sqlite"
echo ""
echo "  Launch the platform:"
echo "      $PY platform/server.py      ->  http://127.0.0.1:8790"
echo "═══════════════════════════════════════════════════════════════════════"
