"""
Label error propagation — Risk 9, quantified rather than asserted.

    "| 9 | Training labels corrupted by field misidentification | Critical |
     **High if unaddressed** | Barcode certification gates entry to the training
     set (§3.4). **This risk is severe precisely because it is silent — it
     inflates apparent accuracy while degrading real performance** |"
                                                       — proposal §9, Risk 9

That sentence contains a specific, directional, testable claim, and this module
tests it. **The direction does not survive measurement**, and saying so is worth
more than confirming it would have been.

What was expected, and what was measured
----------------------------------------
The proposal's reasoning is that a surveyor primed to find Mikania makes
asymmetric errors (§13.7), the model learns that bias, the test labels carry the
same bias, and so the reported accuracy holds up while real performance rots.

Measured on site-disjoint validation at the modelled rates, the opposite happens:
label error **depresses** the apparent number by 15 pp while true performance
stays near 0.93. The mechanism the proposal describes requires the model's errors
to correlate with the *validation set's* label errors, and under a site-disjoint
split they cannot — the validation catchment's misidentifications are drawn
independently of the training catchments'. A random pixel split was tried too, on
the theory that a corrupted patch straddling the split boundary could be
memorised; it also deflates, because a mislabelled patch of *Bauhinia* is still
spectrally *Bauhinia* and is outvoted by every correctly-labelled *Bauhinia*
patch in training.

So Risk 9 is real, severe, and mis-stated. The harm runs the other way:

**A programme with uncertified labels will fail its own go/no-go test while the
classifier is actually fine.** At the §13.7 rates the apparent Mikania-vs-native
figure lands within a couple of points of the §7.3 kill threshold of 0.75 while
the true figure is above 0.92. The decision error is spurious *abandonment* of a
working method, not spurious confidence in a broken one — and for a company whose
Phase 0 is explicitly structured around a kill criterion, that is the more
expensive mistake of the two.

The residual harm the proposal does correctly identify is the false-positive
rate on native climbers, which is understated by the corrupted labels. A false
positive is a native climber cleared, and §2.1(b) identifies exactly that as the
Government's own stated operational risk:

    "clearing a native climber causes unnecessary disturbance to natural
     vegetation cover **and may itself create a niche for Mikania to invade.**"

Two evaluation frames, and the gap between them
-----------------------------------------------
Every function here reports both:

``apparent``  scored against the same corrupted labels the model trained on.
              This is the number a competitor without molecular verification
              would put in a proposal — not dishonestly, but because it is the
              only number they can compute.
``true``      scored against the certified labels. This is what AFCD actually
              gets, and it is computable only because the barcode workstream
              exists.

The gap is the product. §6.1(6): "Every competitor's accuracy figure rests on
labels somebody assigned by eye. Ours rest on sequence."
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .classify import climber_metrics, full_metrics, make_model
from .config import class_groups, class_ids, class_keys


# ==========================================================================
# Corruption model
# ==========================================================================
# Side of the square block, in pixels, treated as one identified specimen.
# See corrupt_labels() for why the unit of corruption cannot be the pixel.
PATCH_PX = 12


def corrupt_labels(y: np.ndarray, cfg: Dict[str, Any], rate: float,
                   gen: np.random.Generator,
                   sterile_frac: Optional[float] = None,
                   bias: Optional[float] = None,
                   row: Optional[np.ndarray] = None,
                   col: Optional[np.ndarray] = None,
                   site: Optional[np.ndarray] = None,
                   patch_px: int = PATCH_PX) -> Dict[str, np.ndarray]:
    """
    Replace a fraction of labels with what a surveyor would plausibly have
    written instead.

    **The unit of corruption is a specimen, not a pixel.** This is the single
    most important modelling decision in the module, and getting it wrong
    reverses the conclusion. A surveyor does not label pixels; they identify one
    vine and that judgement propagates to every pixel of the training polygon
    drawn around it. So errors arrive as spatially coherent blocks sharing one
    wrong label.

    An earlier version flipped labels independently per pixel and measured the
    *opposite* of Risk 9 — apparent accuracy fell while true accuracy stayed
    flat at 0.93 even under 30% corruption. That result was real for what it
    modelled and irrelevant to the field: independent per-pixel flips are
    zero-mean noise that a random forest trained on hundreds of pixels per class
    simply averages away. It cannot teach a model anything, because there is
    nothing coherent to learn. Block corruption can, which is exactly why
    §5.1 says label error "is systematic".

    When ``row``/``col``/``site`` are supplied the blocks are real spatial
    patches. Without them the function falls back to per-pixel flips and says so
    in the returned dict, so a caller cannot silently get the weaker model.

    Only *climber* labels are corrupted. Nobody mistakes bare rock for a vine;
    the error lives entirely in the discrimination §2.1(b) describes, and
    spreading it across all eight classes would dilute it and understate the risk.

    ``bias`` is the fraction of errors that go *toward* the target species. At
    0.5 the corruption is symmetric; at 1.0 every error is a native climber
    relabelled as Mikania. §13.7 sets 0.65 as a modelled value.
    """
    ids = class_ids(cfg)
    fe = cfg["molecular"]["field_error"]
    bias = float(fe["confusion_bias_toward_target"] if bias is None else bias)
    sterile_frac = float(cfg["molecular"]["voucher_plan"]["sterile_fraction"]
                         if sterile_frac is None else sterile_frac)

    target = ids[cfg["confusable_pair"]["target"]]
    natives = [ids[k] for k in cfg["confusable_pair"]["natives"]]
    climbers = [target] + natives

    y_obs = np.array(y, copy=True)
    eligible = np.isin(y, climbers)

    # A fertile specimen (in flower or fruit) is much easier to identify, so the
    # effective rate is the sterile rate weighted by how many specimens are
    # sterile. Autumn flowering is precisely why §5.1(3) proposes running the
    # baseline survey inside the flowering window.
    eff_rate = float(rate) * sterile_frac + float(rate) * 0.17 * (1.0 - sterile_frac)

    flip = np.zeros(y.size, dtype=bool)
    blockwise = row is not None and col is not None

    if blockwise:
        # One "specimen" = one (site, class, spatial block) cell. The same class in
        # the same block is the same patch of vine as far as a field surveyor is
        # concerned. Site labels are strings, so they are factorised to integers.
        if site is None:
            site_code = np.zeros(y.size, dtype=np.int64)
        else:
            _, site_code = np.unique(np.asarray(site), return_inverse=True)
        keys = np.stack([site_code.astype(np.int64),
                         y.astype(np.int64),
                         np.asarray(row, dtype=np.int64) // patch_px,
                         np.asarray(col, dtype=np.int64) // patch_px], axis=1)
        _, inv = np.unique(keys, axis=0, return_inverse=True)
        inv = np.asarray(inv).ravel()

        n_specimens = int(inv.max()) + 1
        specimen_flip = gen.random(n_specimens) < eff_rate
        # Each specimen also draws its own error destination, so every pixel of a
        # misidentified patch carries the SAME wrong label — which is what makes
        # the error learnable.
        specimen_to_target = gen.random(n_specimens) < bias
        specimen_alt = gen.integers(0, len(climbers), size=n_specimens)

        for s in np.where(specimen_flip)[0]:
            m = (inv == s) & eligible
            if not m.any():
                continue
            true_c = int(y[np.argmax(m)])
            if true_c != target and specimen_to_target[s]:
                new_c = target
            else:
                alts = [c for c in climbers if c != true_c]
                new_c = int(alts[specimen_alt[s] % len(alts)])
            y_obs[m] = new_c
            flip |= m
        n_units, unit = n_specimens, "specimen block"
    else:
        flip = eligible & (gen.random(y.size) < eff_rate)
        for i in np.where(flip)[0]:
            true_c = int(y[i])
            if true_c != target and gen.random() < bias:
                y_obs[i] = target
            else:
                alts = [c for c in climbers if c != true_c]
                y_obs[i] = int(gen.choice(alts))
        n_units, unit = int(y.size), "pixel (FALLBACK — understates the risk)"

    return {
        "y_observed": y_obs,
        # Specimen id per pixel. Exposed so that a REMEDIATION step can certify
        # whole specimens rather than individual pixels — certification, like
        # misidentification, happens one plant at a time.
        "unit_id": inv if blockwise else np.arange(y.size),
        "corrupted_mask": flip,
        "n_corrupted": int(flip.sum()),
        "n_eligible": int(eligible.sum()),
        "effective_rate": float(eff_rate),
        "realised_rate": float(flip.sum() / max(eligible.sum(), 1)),
        "bias": bias,
        "corruption_unit": unit,
        "n_units": n_units,
        "blockwise": bool(blockwise),
    }


# ==========================================================================
# Propagation through the classifier
# ==========================================================================
def propagate_once(data: Dict[str, np.ndarray], cfg: Dict[str, Any], rate: float,
                   gen: np.random.Generator, model_name: str = "rf",
                   bias: Optional[float] = None,
                   holdout_site: Optional[str] = None,
                   split: str = "site") -> Dict[str, Any]:
    """
    Train on corrupted labels; evaluate under both truth frames.

    ``split`` selects the validation regime, and it is not a detail — it decides
    the *sign* of the effect:

    ``"site"``    leave-one-site-out, the only reportable regime under §5.1(6).
                  Corruption is drawn independently for the training catchments
                  and the validation catchment, because the surveyor labelling
                  the validation site makes fresh errors there.
    ``"random"``  a random pixel split — the regime §5.1(6) condemns. Corruption
                  is drawn ONCE over the whole dataset before splitting, so a
                  misidentified patch has pixels on both sides of the boundary.

    That difference is the whole mechanism. Under a site-disjoint split the
    model's errors cannot correlate with the validation site's specific label
    errors, so corruption can only *depress* the measured number. Under a random
    split the model memorises the wrong label of a patch it has already seen and
    is then rewarded for reproducing it — which is how label error comes to
    *inflate* an accuracy figure.
    """
    def _corrupt(y, row, col, site):
        return corrupt_labels(y, cfg, rate, gen, bias=bias,
                              row=row, col=col, site=site)

    if split == "random":
        # Corrupt first, then split: one misidentified patch lands on both sides.
        c_all = _corrupt(data["y"], data.get("row"), data.get("col"), data["groups"])
        idx = gen.permutation(data["y"].size)
        cut = int(0.7 * idx.size)
        tr = np.zeros(data["y"].size, dtype=bool); tr[idx[:cut]] = True
        te = ~tr
        holdout = "random 30% of pixels"
        c_tr = {**c_all, "y_observed": c_all["y_observed"][tr],
                "n_corrupted": int(c_all["corrupted_mask"][tr].sum()),
                "realised_rate": c_all["realised_rate"]}
        c_te = {**c_all, "y_observed": c_all["y_observed"][te]}
    else:
        sites = sorted(set(data["groups"].tolist()))
        holdout = holdout_site or sites[-1]
        te = data["groups"] == holdout
        tr = ~te
        if tr.sum() == 0 or te.sum() == 0:
            raise ValueError(f"hold-out site {holdout!r} leaves an empty split")
        c_tr = _corrupt(data["y"][tr], data["row"][tr], data["col"][tr], data["groups"][tr])
        c_te = _corrupt(data["y"][te], data["row"][te], data["col"][te], data["groups"][te])

    model = make_model(model_name, cfg)
    model.fit(data["X"][tr], c_tr["y_observed"])
    pred = model.predict(data["X"][te])


    apparent = full_metrics(c_te["y_observed"], pred, cfg)   # what you could report
    truth = full_metrics(data["y"][te], pred, cfg)           # what AFCD gets

    ap_c = apparent.get("climber", {})
    tr_c = truth.get("climber", {})

    return {
        "rate": float(rate),
        "bias": c_tr["bias"],
        "split": split,
        "holdout_site": holdout,
        "n_train": int(tr.sum()), "n_test": int(te.sum()),
        "n_corrupted_train": c_tr["n_corrupted"],
        "realised_rate_train": round(c_tr["realised_rate"], 4),
        "corruption_unit": c_tr["corruption_unit"],
        "n_specimen_units_train": c_tr["n_units"],

        "apparent_overall_accuracy": round(apparent["overall_accuracy"], 4),
        "true_overall_accuracy": round(truth["overall_accuracy"], 4),
        "apparent_climber_accuracy": round(ap_c.get("balanced_accuracy", float("nan")), 4),
        "true_climber_accuracy": round(tr_c.get("balanced_accuracy", float("nan")), 4),
        "apparent_false_positive": round(ap_c.get("false_positive_rate", float("nan")), 4),
        "true_false_positive": round(tr_c.get("false_positive_rate", float("nan")), 4),

        # Signed gap between what a programme could report and what it delivers.
        # POSITIVE means the reportable number flatters reality (the direction
        # Risk 9 predicts). NEGATIVE means the programme understates its own
        # classifier and risks abandoning a working method — which is what is
        # actually measured here. Named neutrally so the field cannot smuggle in
        # the conclusion it was originally built to confirm.
        "apparent_minus_true_pp": round(
            100.0 * (ap_c.get("balanced_accuracy", np.nan)
                     - tr_c.get("balanced_accuracy", np.nan)), 2),
        "false_positive_understated_pp": round(
            100.0 * (tr_c.get("false_positive_rate", np.nan)
                     - ap_c.get("false_positive_rate", np.nan)), 2),
    }


def propagate_sweep(data: Dict[str, np.ndarray], cfg: Dict[str, Any],
                    rates: Optional[Sequence[float]] = None,
                    gen: Optional[np.random.Generator] = None,
                    model_name: str = "rf",
                    biases: Sequence[float] = (0.5, 0.65, 0.9),
                    split: str = "site") -> Dict[str, Any]:
    """
    Sweep the misidentification rate at several bias levels.

    ``bias = 0.5`` is the control and the most informative row in the output:
    symmetric noise degrades the apparent number roughly as fast as the true one,
    so the inflation is near zero and the problem is visible from inside. As bias
    rises the two curves separate. If that separation did not appear at 0.9 and
    vanish at 0.5, the model would not be capturing the mechanism §5.1 describes,
    and every conclusion drawn from it would be void.
    """
    gen = gen or np.random.default_rng(cfg["project"]["random_seed"] + 12)
    rates = list(rates or cfg["molecular"]["field_error"]["sweep_rates"])

    curves = []
    for bias in biases:
        pts = [propagate_once(data, cfg, r, gen, model_name, bias=bias, split=split)
               for r in rates]
        curves.append({
            "bias": float(bias),
            "label": ("symmetric noise (control)" if abs(bias - 0.5) < 1e-9
                      else f"biased toward Mikania ({bias:.0%} of errors)"),
            "points": pts,
            "max_apparent_minus_true_pp": round(
                max((p["apparent_minus_true_pp"] for p in pts
                     if np.isfinite(p["apparent_minus_true_pp"])), default=float("nan")), 2),
        })

    nominal = float(cfg["molecular"]["field_error"]["misid_rate_sterile"])
    default_bias = float(cfg["molecular"]["field_error"]["confusion_bias_toward_target"])
    at_nominal = next(
        (p for c in curves if abs(c["bias"] - default_bias) < 1e-9
         for p in c["points"] if abs(p["rate"] - nominal) < 1e-9), None)
    if at_nominal is None:                       # nominal not on the sweep grid
        at_nominal = propagate_once(data, cfg, nominal, gen, model_name,
                                    bias=default_bias, split=split)

    kill = cfg["kill_criteria"]
    return {
        "split": split,
        "rates": rates,
        "curves": curves,
        "nominal_rate": nominal,
        "nominal_bias": default_bias,
        "at_nominal": at_nominal,
        # The two decision errors a §7.3 go/no-go can make when its labels are
        # uncertified. Both are reported; only one turns out to occur.
        "kill_criterion_masked": bool(
            at_nominal["apparent_climber_accuracy"]
            >= kill["mikania_vs_native_min_accuracy"]
            > at_nominal["true_climber_accuracy"]),
        "kill_criterion_spuriously_failed": bool(
            at_nominal["true_climber_accuracy"]
            >= kill["mikania_vs_native_min_accuracy"]
            > at_nominal["apparent_climber_accuracy"]),
        "kill_margin_pp": round(
            100.0 * (at_nominal["apparent_climber_accuracy"]
                     - kill["mikania_vs_native_min_accuracy"]), 2),
        "kill_threshold": kill["mikania_vs_native_min_accuracy"],
        "interpretation": (
            "A programme with uncertified labels evaluates itself against the same "
            "faulty labels it trained on, so its go/no-go verdict is about the labels "
            "as much as the classifier. `kill_criterion_masked` is the failure Risk 9 "
            "predicts (pass the test, fail reality); `kill_criterion_spuriously_failed` "
            "is the one actually measured (abandon a classifier that works)."),
    }


# ==========================================================================
# Concordance — AFCD removal records vs barcode identity  (§5.1 mitigation 2)
# ==========================================================================
def concordance(field_calls: Sequence[str], certified: Sequence[str],
                classes: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """
    Agreement between visual field identification and barcode identity.

    §5.1(2) proposes measuring exactly this and points out that it is saleable in
    its own right:

        "if visual identification is, say, 90% concordant with barcode identity,
         AFCD has learned something material about its own programme that no one
         has previously measured."

    Cohen's kappa is reported alongside raw agreement because raw agreement is
    inflated by class prevalence: in a scene that is mostly Mikania, calling
    everything Mikania scores well and means nothing.

    The asymmetry breakdown is the operationally important half. ``native_called_
    mikania`` counts specimens that a clearance crew acting on the field call
    would have cut down; ``mikania_called_native`` counts infestations that would
    have been left in place. Both are errors; only the first is the one the
    Government guidance in §2.1(b) is worried about, and only the first has a
    conservation cost attached.
    """
    fc = np.asarray(field_calls, dtype=object)
    ct = np.asarray(certified, dtype=object)
    if fc.size != ct.size:
        raise ValueError("field_calls and certified must be the same length")
    if fc.size == 0:
        return {"n": 0}

    labels = sorted(classes or (set(fc.tolist()) | set(ct.tolist())))
    idx = {c: i for i, c in enumerate(labels)}
    cm = np.zeros((len(labels), len(labels)), dtype=int)
    for a, b in zip(ct, fc):                      # rows = truth, cols = field call
        cm[idx[str(a)], idx[str(b)]] += 1

    n = int(cm.sum())
    agree = float(np.trace(cm) / n)
    pe = float((cm.sum(0) * cm.sum(1)).sum() / (n * n))
    kappa = (agree - pe) / (1 - pe) if pe < 1 else 0.0

    per_class = {}
    for c, i in idx.items():
        sup = int(cm[i].sum())
        per_class[c] = {
            "n": sup,
            "correctly_called": int(cm[i, i]),
            "recall": float(cm[i, i] / sup) if sup else None,
            "precision": float(cm[i, i] / cm[:, i].sum()) if cm[:, i].sum() else None,
        }

    target = "mikania"
    n_false_pos = n_false_neg = 0
    if target in idx:
        t = idx[target]
        n_false_pos = int(cm[:, t].sum() - cm[t, t])    # not Mikania, called Mikania
        n_false_neg = int(cm[t, :].sum() - cm[t, t])    # Mikania, called something else

    return {
        "n": n,
        "agreement": round(agree, 4),
        "cohens_kappa": round(float(kappa), 4),
        "labels": labels,
        "confusion_matrix": cm.tolist(),
        "confusion_note": "rows = barcode-certified identity, columns = visual field call",
        "per_class": per_class,
        "native_called_mikania": n_false_pos,
        "native_called_mikania_rate": round(n_false_pos / max(n, 1), 4),
        "mikania_called_native": n_false_neg,
        "mikania_called_native_rate": round(n_false_neg / max(n, 1), 4),
        "asymmetry_ratio": (round(n_false_pos / n_false_neg, 2)
                            if n_false_neg else None),
        "interpretation": (
            f"{agree:.1%} of visual field calls match the barcode-certified identity "
            f"(kappa = {kappa:.2f}). {n_false_pos} native climber(s) were called Mikania "
            f"— specimens a clearance crew acting on the field call would have cut down."),
    }


# ==========================================================================
# What it costs, and what certification is worth
# ==========================================================================
def operational_cost(false_positive_rate: float, cfg: Dict[str, Any],
                     programme_area_ha: float = 3000.0,
                     native_climber_cover_frac: float = 0.12) -> Dict[str, Any]:
    """
    Convert a false-positive rate into hectares of native climber wrongly
    cleared, and into money.

    Two costs, and the second is the one that makes the case:

    * the **direct** cost of clearance crews sent to the wrong polygon —
      recoverable, merely wasteful;
    * the **induced** cost, which is §2.1(b)'s actual warning: clearing a native
      climber "may itself create a niche for Mikania to invade." A wrongly-cleared
      patch is not neutral, it is a seedbed. Modelled as a fraction of wrongly
      cleared area becoming newly invaded and requiring treatment later.

    ``native_climber_cover_frac`` and the induced-invasion fraction are
    ASSUMPTIONS with no Hong Kong measurement behind them. They are stated here,
    reported in the output, and are the first thing an evaluator should challenge.
    """
    eff = cfg["efficacy"]["methods"]["cut_stump_herbicide"]
    cost_per_ha = float(eff["cost_hkd_per_ha"])
    induced_frac = 0.35                     # ASSUMPTION — see docstring

    native_ha = programme_area_ha * native_climber_cover_frac
    wrongly_cleared_ha = native_ha * float(false_positive_rate)
    direct = wrongly_cleared_ha * cost_per_ha
    induced_ha = wrongly_cleared_ha * induced_frac
    induced = induced_ha * cost_per_ha

    return {
        "false_positive_rate": round(float(false_positive_rate), 4),
        "programme_area_ha": programme_area_ha,
        "native_climber_area_ha": round(native_ha, 1),
        "wrongly_cleared_ha": round(wrongly_cleared_ha, 2),
        "direct_cost_hkd": round(direct),
        "induced_invasion_ha": round(induced_ha, 2),
        "induced_cost_hkd": round(induced),
        "total_cost_hkd": round(direct + induced),
        "assumptions": {
            "native_climber_cover_frac": native_climber_cover_frac,
            "induced_invasion_fraction": induced_frac,
            "clearance_cost_hkd_per_ha": cost_per_ha,
            "note": "Both fractions are modelled. No Hong Kong measurement exists "
                    "for either; they are stated so they can be challenged (§B.6).",
        },
    }


def certification_value(sweep: Dict[str, Any], cfg: Dict[str, Any],
                        programme_area_ha: float = 3000.0) -> Dict[str, Any]:
    """
    Cost of barcode certification against the cost of the errors it prevents.

    The comparison §3.4 asserts qualitatively — "it is standard, and it is cheap
    relative to a flying day" — with the arithmetic attached. Certification is
    priced from §13.9 at the §13.6 voucher volume; the avoided cost is the
    difference in wrongly-cleared hectares between the uncertified programme
    (operating at the modelled field error rate) and the certified one
    (operating at rate 0, since the labels are sequence-derived).

    The residual is stated honestly: certification removes *label* error, not
    classifier error. A certified programme still has a nonzero false-positive
    rate, and the benefit claimed here is only the difference.
    """
    m = cfg["molecular"]["costs_hkd"]
    plan = cfg["molecular"]["voucher_plan"]
    n_loci = len(cfg["molecular"]["loci"])

    n_vouchers = sum(plan["species_targets"].values()) * len(plan["seasons"])
    per_voucher = (m["extraction_per_sample"] + n_loci * m["pcr_per_reaction"]
                   + n_loci * 2 * m["sanger_per_reaction"])
    consumables = n_vouchers * per_voucher
    batches = max(1, int(np.ceil(n_vouchers / max(m["nanopore_batch_size"], 1))))
    bioinformatics = batches * m["bioinformatics_hours_per_batch"] * m["analyst_hourly"]
    lab_access = m["lab_access_per_month"] * 6          # six working months in Phase 0
    total_cost = consumables + bioinformatics + lab_access

    at_nom = sweep["at_nominal"]
    uncertified = operational_cost(at_nom["true_false_positive"], cfg, programme_area_ha)

    # The certified programme's false-positive rate is the rate 0 point of the
    # same sweep — same classifier, same sites, clean labels.
    zero_pt = next((p for c in sweep["curves"] if abs(c["bias"] - sweep["nominal_bias"]) < 1e-9
                    for p in c["points"] if p["rate"] == 0.0), None)
    certified = operational_cost(
        zero_pt["true_false_positive"] if zero_pt else at_nom["true_false_positive"],
        cfg, programme_area_ha)

    avoided = uncertified["total_cost_hkd"] - certified["total_cost_hkd"]

    return {
        "n_vouchers": n_vouchers,
        "cost_per_voucher_hkd": round(per_voucher),
        "consumables_hkd": round(consumables),
        "bioinformatics_hkd": round(bioinformatics),
        "lab_access_hkd": round(lab_access),
        "total_certification_cost_hkd": round(total_cost),
        "phase0_budget_line_hkd": m["phase0_budget_line"],
        "within_budget_line": bool(m["phase0_budget_line"][0] <= total_cost <= m["phase0_budget_line"][1]),
        "uncertified_programme": uncertified,
        "certified_programme": certified,
        "avoided_cost_hkd_per_year": round(avoided),
        "benefit_cost_ratio": (round(avoided / total_cost, 2) if total_cost > 0 else None),
        "payback_years": (round(total_cost / avoided, 2) if avoided > 0 else None),
        "caveats": [
            "Certification removes LABEL error only. Residual classifier error is "
            "unaffected and is included in both arms.",
            "All molecular costs are modelled (§13.9); §10.8 obtains real quotations.",
            "Avoided-cost figures inherit the assumptions in operational_cost().",
        ],
    }


__all__ = ["corrupt_labels", "propagate_once", "propagate_sweep", "concordance",
           "operational_cost", "certification_value"]
