"""
MIKANIA-HSI
===========

Reference implementation of the UAV hyperspectral pipeline described in
``AFCD_Mikania_Hyperspectral_Proposal.md`` — species-level mapping of the
invasive vine *Mikania micrantha* against the native climbers it is confused
with (*Bauhinia glauca*, *Byttneria aspera*).

The package is deliberately organised so that each module corresponds to one
numbered claim in the proposal, and so that anyone auditing the work can find
the code behind a claim without reading the whole tree:

===================  =========================================================
Module               Proposal section it implements
===================  =========================================================
``config``           the whole of ``config/default.yaml`` (all constants)
``io_hsi``           acquisition / delivery formats (ENVI, GeoTIFF, npz)
``preprocess``       §4.1 Huang et al. chain: SG smoothing + derivatives, SNV
``features``         §3.2 red-edge position, pigment ratios, NIR plateau
``spectral_library`` §5.1 mitigation 1 — the ground spectral library
``simulate``         §7.3 the Phase 0 demonstration scene
``unmixing``         §3.2 two-layer blanket-over-canopy mixed-pixel structure
``classify``         §4.1 PLS-DA / RF / SVM, §5.1(6) leave-one-SITE-out CV
``severity``         §3.1 deliverable 2 — severity-ranked prioritisation
``change``           §3.1 deliverable 3 — post-treatment efficacy verification
``economics``        §5.3 coverage economics, §7.2 pricing
``report``           figures, GeoJSON, and the platform data bundle
===================  =========================================================

Added in v2.0, implementing the molecular layer of proposal v2.0:

===================  =========================================================
Module               Proposal section it implements
===================  =========================================================
``genomics``         §3.3 the comparative-genomic basis of separability, and
                     §10 action 0 — the desk study, its evidence chains, and
                     the falsification tests they license
``barcode``          §3.4 the seven-stage DNA barcoding pipeline: QC,
                     similarity search, phylogenetic adjudication, release
``refdb``            §3.1 deliverable 4 / §7.1 — the versioned, checksummed
                     reference database that is the company's actual asset
``labelerror``       §9 Risk 9 — what field misidentification does to a
                     classifier, and what certification is worth
===================  =========================================================

Nothing in this package silently invents a number: every constant lives in the
YAML config with a provenance comment.
"""

__version__ = "2.0.0"
__all__ = [
    "config",
    "io_hsi",
    "preprocess",
    "features",
    "spectral_library",
    "simulate",
    "unmixing",
    "classify",
    "severity",
    "change",
    "economics",
    "report",
    "genomics",
    "barcode",
    "refdb",
    "labelerror",
]
