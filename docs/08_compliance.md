# Compliance — the surface a biological workstream adds

**Proposal §8.4.** *"Adding a molecular workstream adds a regulatory surface that
v1.0 did not have. It is manageable, but it must be planned rather than
discovered."*

Nothing here is legal advice. Every item marked **[VERIFY]** in the proposal is
still marked **[VERIFY]** here; the implementation makes the *policy* executable,
it does not resolve the legal questions.

## 1. Plant collection in country parks

| | |
|---|---|
| **Instruments** | Country Parks Ordinance (Cap. 208); Forests and Countryside Ordinance (Cap. 96) and subsidiary Forestry Regulations |
| **Status** | **[VERIFY]** the exact permit instrument and application route for scientific collection (§10.9) |
| **In practice** | A non-issue *if AFCD is the client or research partner* — the same access argument as §8.2. A genuine obstacle otherwise |

**Consequence for sequencing of work:** this reinforces §10's ordering — approach
AFCD before spending anything. `07_phase0_runbook.md` puts the permit in months
2–3, ahead of the field campaign, not alongside it.

**Implemented:** `voucher.permit_ref` is a first-class column and is populated on
every insert. A voucher without a permit reference is visible immediately.

## 2. Protected species

Sampling must avoid species on the Forestry Regulations protected-plants
schedule. The target and its look-alikes are common climbers, so the risk is low
but non-zero. **Handled by briefing collectors, not by policy** — a schedule
check in software would give false assurance about a judgement made in the field.

## 3. Access and benefit-sharing (Nagoya)

| | |
|---|---|
| **Instrument** | Nagoya Protocol on Access to Genetic Resources and Benefit-Sharing |
| **Status** | **[VERIFY]** applicability to HKSAR, and to material collected domestically for domestic commercial use (§10.10) |
| **Position** | Flagged as diligence, not as an expected blocker |

Must be confirmed **before** genetic data derived from HK-collected material is
commercialised or deposited. That ordering is why `07_phase0_runbook.md` puts the
deposition-policy decision in months 2–3, before any sequence exists.

## 4. Sequence deposition policy

§8.4's recommended position, implemented in config §13.10 and enforced in stage 14:

| Decision | Rule |
|---|---|
| **Deposit** | barcode sequences for taxa where public coverage is below 5 references for that taxon/locus |
| **Withhold** | paired spectra, precise coordinates, and the voucher↔spectrum linkage — always, at every licence tier |
| **Generalise** | published coordinates to 5 km |

**Rationale, from §8.4:** a barcode sequence alone does not let a competitor build
the product; the sequence-to-spectrum-to-place linkage does. Depositing the
former earns scientific credibility — which supports the §10.7 academic
collaboration and the §7.4 ECF application — at no competitive cost.

**Implemented:** every decision is written to the `deposition` table with its
rationale and the public coverage that drove it, so the policy is demonstrable
rather than merely stated. Current build: 3 sequences to deposit, 19 withheld.

**Note the alignment of interest.** The taxa where deposition is indicated are
exactly the taxa where public coverage is too thin to certify a voucher —
*Mikania cordata* above all. Closing that gap is simultaneously the scientific
contribution, the credibility play, and the thing that makes our own pipeline
work. That is a rare case where the generous option and the commercial option are
the same option.

## 5. Laboratory access

§7.3 assumes benchtop work under a university or commercial arrangement rather
than a built facility. §9 Risk 12 warns that the molecular workstream could
"consume management attention disproportionate to its budget share", with the
mitigation: *"Outsource sequencing; keep only the bioinformatics in-house. Do not
build a wet lab in Phase 0."*

The implementation follows that split exactly: everything in `mikania/barcode.py`
is bioinformatics, and every wet-lab step in `03_barcode_sop.md` is specified as
a procedure to be performed under someone else's accreditation.

**Secure in writing before the §7.3 budget is committed (§10.8).**

## 6. Data protection (PDPO, Cap. 486)

Unchanged from v1.0 for imagery. The molecular layer adds one consideration:
**collector identity** appears in `voucher.collector`. It is personal data, it is
not required by any downstream analysis, and it is excluded from every licence
tier below `internal`.

## 7. What the code enforces vs what it only records

Being precise about this matters, because software that appears to enforce a
legal requirement is worse than software that clearly does not.

| Requirement | Status |
|---|---|
| Coordinate generalisation before publication | **Enforced** — computed at write time, in `add_voucher` |
| Withheld fields per licence tier | **Enforced** — `licence_manifest` drives the export |
| Deposition rule | **Enforced** — computed from measured public coverage |
| Release gate (only certified vouchers train) | **Enforced** — `training_label_set` cannot return others |
| Permit held for a collection | **Recorded only** — a column, not a check |
| Protected-species avoidance | **Not implemented** — collector briefing |
| Nagoya applicability | **Not implemented** — legal determination, [VERIFY] |
