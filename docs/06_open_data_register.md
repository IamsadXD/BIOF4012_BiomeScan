# Open data register — molecular layer

Every external source used by the molecular stages, with what it is, how it is
obtained, and what may be done with it. The v1.0 sources (GBIF, EcoSIS, EO-1
Hyperion) are registered in `data/raw/PROVENANCE.json`.

## 1. NCBI Entrez / GenBank — barcode reference sequences

| | |
|---|---|
| **Endpoint** | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/{esearch,efetch}.fcgi` |
| **Obtained by** | `scripts/11_fetch_barcode_references.py` |
| **Cached at** | `data/raw/barcode_refs/{rbcL,matK,ITS2,trnH-psbA}.fasta` |
| **Volume** | 185 sequences across 7 accepted taxa × 4 loci |
| **Access** | Free, no API key at this volume; documented limit 3 req/s, respected via `request_interval_s` |
| **Rights** | GenBank records are in the public domain. NCBI asks that submitters be credited; every accession is retained in the defline and in the `reference_sequence` table |

**Query form:** `"<taxon>"[Organism] AND <locus query>`, with locus queries in
config §13.1. Records outside 150–4,000 bp are dropped: a 40 kb hit for "matK" is
a plastid genome, which is a legitimate record and a useless barcode reference.

**Robustness note.** NCBI intermittently returns JSON containing raw control
characters, which `json.loads` rejects. Observed on this exact query set. The
fetcher parses non-strictly, retries with backoff, then falls back to scraping
`<Id>` elements from the XML response.

## 2. BOLD Systems — secondary barcode source

| | |
|---|---|
| **Endpoint** | `https://www.boldsystems.org/index.php/API_Public/combined` |
| **Obtained by** | the same stage, unless `--no-bold` |
| **Status** | **Optional by design.** A failure or an API redesign logs a line and the run continues on NCBI alone |
| **Rights** | Public data portal; records carry their own terms. Treated as additive evidence, never as a dependency |

A build that breaks because a third party changed a URL is a build nobody can
reproduce in two years.

## 3. Published genomic literature — the desk study inputs

Encoded as data in `config/genomic_priors.yaml`, each with a DOI or URL. Not
downloaded: these are *claims* extracted from papers by an analyst, which is what
a desk study is. The point of encoding them as YAML rather than prose is that the
inference from finding → trait → spectral prediction becomes machine-checkable
and the confidence propagation becomes auditable.

| id | Source |
|---|---|
| F1, F2, F3, F4 | Liu B. et al. (2020) *Nature Communications* **11**:340 — [doi](https://www.nature.com/articles/s41467-019-13926-4) |
| F4, F5 | Wang et al. (2025) *New Phytologist* — [doi](https://nph.onlinelibrary.wiley.com/doi/10.1111/nph.70448) |
| F6 | *The Crop Journal* (2023), diurnal expression of photosynthetic pathway genes — [link](https://www.sciencedirect.com/science/article/pii/S2095311923000813) |
| F7 | Comparative transcriptome vs native congeners — [PMC5968712](https://pmc.ncbi.nlm.nih.gov/articles/PMC5968712/) |
| F8 | Defensive mechanisms of *M. micrantha* (2025) — [PMC11768483](https://pmc.ncbi.nlm.nih.gov/articles/PMC11768483/) |

Each entry carries an `evidence` tier, and the desk study is forbidden from
reporting a prediction at higher confidence than the weakest link in its chain.
Every chain in the current set terminates in `inferred_optical`: **no
leaf-optical measurement linking these genes to reflectance exists for Hong Kong
material**, which is Appendix B.8's position and is stated in the output.

## 4. What is NOT open data here

Stated so the boundary is unambiguous:

- **Voucher sequences** — none exist. Stage 12's "vouchers" are real GenBank
  records held out of the reference set and degraded into simulated Sanger reads.
- **Read quality** — modelled (primer-proximal dropout, 3' decay, substitution
  rates implied by local Phred).
- **Voucher assembly across loci** — modelled. A real voucher's four loci come
  from one plant; these pair independent accessions of the same species. The
  consequence is stated in stage 12: the pipeline is never tested against a
  specimen whose loci genuinely disagree, which is exactly what quarantine exists
  for. Real vouchers will exercise it.
- **Visual field calls** — modelled at the §13.7 rates.
- **Paired spectra** — from the stage-02 library, whose species contrasts are
  modelled on a real measured leaf base and swept in stage 05.

## 5. Reproducing the fetch

```bash
.venv/bin/python scripts/11_fetch_barcode_references.py --force
```

Coverage counts will drift as GenBank grows. That is the point of
`barcode_reference_coverage.json` carrying `retrieved_utc`, and of the
`reference_sequence` table recording what each certificate was called against —
a call made against a 2026 snapshot cannot be re-derived from a 2029 one.
