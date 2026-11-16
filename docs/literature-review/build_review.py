"""Build the Biomescan literature review (.docx) and its figures.

Run from anywhere:
    PYTHONPATH=/tmp/bslibs python3 docs/literature-review/build_review.py

Inputs: outputs/reports/separability.json, validation.json, benchmark_botswana.json,
barcode_reference_coverage.json (demonstrator numbers are read, not retyped).
Outputs: docs/literature-review/Biomescan_literature_review.docx and figures/*.png.

The word count is taken from the built .docx (title, abstract, headings, body,
legends, table text and references; author, affiliation, correspondence and
word-count lines are excluded) and written onto the title page.
"""
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = ROOT / "outputs" / "reports"
FIG_DIR = HERE / "figures"
OUT = HERE / "Biomescan_literature_review.docx"
FONT = "Times New Roman"

# --------------------------------------------------------------------------
# Demonstrator numbers, read from the repository's JSON reports
# --------------------------------------------------------------------------
sep = json.loads((REPORTS / "separability.json").read_text())
val = json.loads((REPORTS / "validation.json").read_text())
bots = json.loads((REPORTS / "benchmark_botswana.json").read_text())
bar = json.loads((REPORTS / "barcode_reference_coverage.json").read_text())

abl = sep["sensor_ablation"]["wet_summer"]          # foliage-only season
TIERS = [("rgb", "RGB camera"), ("multispectral", "5-band\nmultispectral"),
         ("hyperspectral", "VNIR\nhyperspectral")]
acc = {k: 100 * abl[k]["balanced_accuracy_mikania_vs_native"] for k, _ in TIERS}
acc_sd = {k: 100 * abl[k]["balanced_accuracy_mikania_vs_native_sd"] for k, _ in TIERS}
fpr = {k: 100 * abl[k]["false_positive_rate"] for k, _ in TIERS}
autumn_perfect = all(sep["sensor_ablation"]["autumn_flower"][k]["balanced_accuracy_mikania_vs_native"] == 1.0
                     for k, _ in TIERS)

kc = val["kill_criterion"]
loso, loso_lo = 100 * kc["measured_accuracy"], 100 * kc["measured_accuracy_lower_ci"]
loso_hi = 100 * val["models"][val["best_model"]]["climber_balanced_accuracy_ci"][2]

b_rand = 100 * bots["random_split_overall_accuracy"]
b_blk, b_lo, b_hi = (100 * v for v in bots["blocked_overall_accuracy_trainable_classes"])

n_seq = bar["total_sequences"]
mc = bar["matrix"]["Mikania cordata"]


def f1(x):
    return f"{x:.1f}"


# Guard: the prose below quotes these values; stop if the reports change.
EXPECT = {"VNIR acc": (f1(acc["hyperspectral"]), "68.7"), "RGB acc": (f1(acc["rgb"]), "53.1"),
          "VNIR fpr": (f1(fpr["hyperspectral"]), "7.9"), "RGB fpr": (f1(fpr["rgb"]), "13.5"),
          "LOSO": (f1(loso), "80.4"), "LOSO lo": (f1(loso_lo), "50.8"), "LOSO hi": (f1(loso_hi), "98.0"),
          "Botswana random": (f1(b_rand), "93.7"), "Botswana blocked": (f1(b_blk), "58.9"),
          "n_seq": (str(n_seq), "185"), "cordata": ((mc["rbcL"], mc["ITS2"], mc["matK"]), (1, 1, 0))}
for name, (got, want) in EXPECT.items():
    assert got == want, f"{name}: report gives {got}, text says {want}"
assert autumn_perfect

# --------------------------------------------------------------------------
# Figures (greyscale, Times-like serif)
# --------------------------------------------------------------------------
plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix",
                     "font.size": 10, "axes.linewidth": 0.8, "hatch.linewidth": 0.6})


def box(ax, xy, w, h, text, dashed=False, fc="white", fs=9.5):
    x, y = xy
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1.0, edgecolor="black", facecolor=fc,
                                linestyle="--" if dashed else "-"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, linespacing=1.25)


def arrow(ax, p, q, rad=0.0, dashed=False, ms=12):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=ms, linewidth=1.0,
                                 color="black", connectionstyle=f"arc3,rad={rad}",
                                 linestyle="--" if dashed else "-"))


def figure1(path):
    fig, ax = plt.subplots(figsize=(7.0, 3.9), dpi=300)
    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, 5.6)
    ax.axis("off")
    w, h, y = 1.9, 1.15, 3.6
    xs = [0.1, 2.2, 4.3, 6.4, 8.5]
    labels = ["1. UAV survey\nVNIR\nhyperspectral",
              "2. Classification\nspecies map,\nabundance",
              "3. GIS work plan\nseverity-ranked\nwork units",
              "4. Field action\nclearance\nby crews",
              "5. Repeat survey\nregrowth and\nchange layer"]
    for x, t in zip(xs, labels):
        box(ax, (x, y), w, h, t, fc="0.93" if t.startswith("2") else "white", fs=9)
    for a, b in zip(xs[:-1], xs[1:]):
        arrow(ax, (a + w + 0.03, y + h / 2), (b - 0.03, y + h / 2), ms=9)
    # feedback loop from repeat survey to the next survey
    arrow(ax, (xs[4] + w / 2, y + h + 0.04), (xs[0] + w / 2, y + h + 0.04), rad=0.12)
    ax.text(5.3, 5.42, "next survey cycle", ha="center", fontsize=9, style="italic")
    # verified reference library feeding the classifier
    box(ax, (4.0, 1.45), 4.4, 1.3,
        "Verified reference library\nfield spectra linked to voucher specimen,\n"
        "DNA barcode identity, location and season", fc="0.85", fs=9)
    arrow(ax, (4.6, 2.78), (xs[1] + w / 2 + 0.1, y - 0.04))
    ax.text(4.75, 3.17, "training and site-blocked validation", fontsize=8.5,
            va="center", ha="left", style="italic")
    # planned SWIR workstream, directly below the survey step
    box(ax, (0.1, 0.15), 3.4, 1.75,
        "Planned workstream (not built)\nSWIR survey: visible standing\n"
        "water map and inspection list;\nno mosquito, larva or egg\ndetection", dashed=True, fs=8.5)
    arrow(ax, (xs[0] + w / 2, y - 0.04), (xs[0] + w / 2, 1.94), dashed=True)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figure2(path):
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 3.4), dpi=300,
                               gridspec_kw={"width_ratios": [1.6, 1]})
    import numpy as np
    x = np.arange(3)
    wbar = 0.38
    ba = [acc[k] for k, _ in TIERS]
    sd = [acc_sd[k] for k, _ in TIERS]
    fp = [fpr[k] for k, _ in TIERS]
    r1 = a.bar(x - wbar / 2, ba, wbar, yerr=sd, capsize=3, color="0.45", edgecolor="black",
               linewidth=0.8, label="Balanced accuracy", error_kw={"linewidth": 0.8})
    r2 = a.bar(x + wbar / 2, fp, wbar, color="white", edgecolor="black", hatch="////",
               linewidth=0.8, label="False-positive rate")
    for rect, v, s in zip(r1, ba, sd):
        a.text(rect.get_x() + rect.get_width() / 2, v + s + 1.5, f"{v:.1f}", ha="center", fontsize=8.5)
    for rect, v in zip(r2, fp):
        a.text(rect.get_x() + rect.get_width() / 2, v + 1.5, f"{v:.1f}", ha="center", fontsize=8.5)
    a.axhline(50, color="black", linestyle=":", linewidth=0.8)
    a.text(2.62, 51.5, "chance", fontsize=8, ha="right")
    a.set_xticks(x, [l for _, l in TIERS])
    a.set_ylim(0, 100)
    a.set_ylabel("Percent")
    a.set_title("A  Sensor tier, foliage only (simulated)", loc="left", fontsize=10)
    a.legend(frameon=False, fontsize=8.5, loc="upper left")
    for s in ("top", "right"):
        a.spines[s].set_visible(False)

    vals = [b_rand, b_blk]
    rb = b.bar([0, 1], vals, 0.55, color=["0.45", "white"], edgecolor="black", linewidth=0.8)
    rb[1].set_hatch("\\\\\\\\")
    b.errorbar([1], [b_blk], yerr=[[b_blk - b_lo], [b_hi - b_blk]], fmt="none", ecolor="black",
               capsize=3, linewidth=0.8)
    b.text(0, b_rand + 2, f"{b_rand:.1f}", ha="center", fontsize=8.5)
    b.text(1, b_hi + 2, f"{b_blk:.1f}", ha="center", fontsize=8.5)
    b.set_xticks([0, 1], ["Random\npixel split", "Spatially\nblocked"])
    b.set_ylim(0, 100)
    b.set_ylabel("Overall accuracy (%)")
    b.set_title("B  Real Hyperion imagery", loc="left", fontsize=10)
    for s in ("top", "right"):
        b.spines[s].set_visible(False)
    fig.tight_layout(w_pad=2.0)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


FIG_DIR.mkdir(parents=True, exist_ok=True)
FIG1 = FIG_DIR / "fig1_workflow.png"
FIG2 = FIG_DIR / "fig2_sensor_and_validation.png"
figure1(FIG1)
figure2(FIG2)

# --------------------------------------------------------------------------
# Text. *asterisks* mark italics, **double** marks bold.
# --------------------------------------------------------------------------
TITLE = "Mapping invasive species from drones: the science and market for Biomescan in Hong Kong"

ABSTRACT = (
    "Invasive species impose large and rising costs. Biomescan is a Hong Kong start-up concept that proposes drone "
    "surveys for two targets: the invasive vine *Mikania micrantha*, and visible standing water "
    "that may serve as breeding habitat for the mosquito *Aedes albopictus*. This review assesses "
    "the science and the market. Hyperspectral imaging can separate plant "
    "species through differences in leaf chemistry, and image-based studies of *Mikania* report "
    "88.7–94.5% accuracy, but these figures rest on small or randomly divided test sets, and "
    "validation on spatially separate test areas can remove much of the apparent accuracy. "
    "Public DNA reference sequences are also missing for a native look-alike species. In "
    "Biomescan's research demonstrator, which uses simulated Hong Kong scenes, hyperspectral "
    "features outperformed an ordinary colour camera when the vine was not flowering, but "
    "uncertainty across three test sites remained wide. Bottom-up estimates put the market "
    "Biomescan could realistically win at HK$0.5–1.2 million a year by year 3, against "
    "government drone teams and many licensed drone operators. We conclude that Biomescan's case "
    "rests not on flying drones but on verified reference libraries, honest validation and "
    "outputs that change field decisions, all of which still need field evidence and paying "
    "pilots."
)

# Each entry: ("h1"|"h2", text) or ("p", text) or ("fig", n) or ("table", n)
BODY = [
    ("h1", "Introduction"),
    ("h2", "The cost of finding invaders late"),
    ("p", "Biological invasions cost at least US$1.288 trillion between 1970 and 2017; costs have "
          "risen about threefold per decade (1). *Mikania micrantha* (mile-a-minute weed) shows why. It has "
          "spread widely across southern China since the 1980s, damaging many ecosystems, and no "
          "natural control has been achieved (2). Wind-borne seeds and stem "
          "fragments spread it, and slashing can increase regrowth (3). Its genome study found a whole-genome duplication, "
          "night-time carbon dioxide uptake and efficient stem photosynthesis (4). In Guangdong, "
          "forest land with *Mikania* fell from 803,700 mu in 2021 to 517,500 mu (about 34,500 ha) "
          "in 2024, and the province allocated CNY319 million to "
          "forest-pest control, including *Mikania*, for 2024–25 (5). Hong Kong has no current "
          "official estimate; the latest, about 100 ha, dates from 2002 (Biomescan compilation of "
          "government records)."),
    ("p", "A second target, the dengue vector *Aedes albopictus*, breeds in small pools of "
          "standing water. Since August 2025 the Food and Environmental Hygiene "
          "Department (FEHD) has extended enhanced control to areas where the gravidtrap index, "
          "the percentage of monitoring traps that detect the mosquito, lies between 10% and 20% "
          "(6). Hong Kong populations already resist several common insecticides (7), so removing "
          "breeding water matters more."),
    ("h2", "Biomescan in brief"),
    ("p", "Biomescan proposes repeatable unmanned aerial vehicle (UAV), or drone, surveys that "
          "tell field teams where to work (Fig. 1). For *Mikania*, a visible and near-infrared "
          "(VNIR, 400–1000 nm) hyperspectral camera records reflectance in many narrow wavebands. "
          "A machine-learning classifier, trained on field spectra whose species is confirmed by DNA "
          "barcoding (identifying a specimen from a short standard gene sequence), maps the vine. A geographic information system (GIS) then ranks work units, "
          "and repeat surveys measure regrowth. A planned second workstream would use a "
          "shortwave-infrared (SWIR, 900–1700 nm) camera to map visible standing water for "
          "inspection; it cannot observe mosquitoes, larvae or eggs. Only the *Mikania* workflow "
          "exists, as a demonstrator on simulated Hong Kong scenes; Biomescan has no customers or "
          "contracts."),
    ("fig", 1),
    ("h1", "The technology and the proposed service"),
    ("h2", "Why hyperspectral sensing could separate a vine from its neighbours"),
    ("p", "Leaf reflectance rises steeply between 680 and 750 nm. The position of this rise, the "
          "red edge, shifts with chlorophyll concentration and is suited to early stress "
          "detection (8). Hyperspectral sensors resolve such features and can detect invaders at "
          "species level across many ecosystem types (9). In Hawaii, airborne imaging spectroscopy "
          "fused with LiDAR (laser ranging) mapped three invasive tree species with detection "
          "errors below 6.8% for canopies of about 7 m² but below 18.6% for about 2 m² (10), "
          "consistent with the wider difficulty of detecting small, nascent populations (11). For "
          "*Mikania*, a convolutional neural network (CNN) applied to UAV colour images reached "
          "94.50% accuracy on 400 test samples (12), and hyperspectral images at 450–998 nm "
          "classified by random forest reached 88.71% (13)."),
    ("h2", "Evidence gaps in validation and labels"),
    ("p", "When data are spatially or hierarchically structured, "
          "random cross-validation seriously underestimates prediction error, and blocked "
          "cross-validation is nearly always more appropriate (14). In UAV tree-species mapping, "
          "random hold-outs overestimated CNN performance by up to 28% relative to spatially "
          "blocked hold-outs (15). Neither *Mikania* abstract reports a test on separate sites "
          "(Table 1). Labels are also weak. Public sequence databases identified only about "
          "81% of curated plant specimens to species (16), and label errors occur even in widely "
          "used benchmark datasets (17). The recommended core plant barcode, rbcL plus matK (18), "
          "cannot help where references are missing: Biomescan's search of 185 public sequences "
          "found one rbcL, one ITS2 and no matK record for the native look-alike *Mikania "
          "cordata*."),
    ("table", 1),
    ("h2", "What the demonstrator shows"),
    ("p", "Biomescan's demonstrator applies these lessons (Fig. 2). During simulated "
          "flowering every sensor separated *Mikania* perfectly, so the case for VNIR rests on "
          "foliage. On simulated non-flowering scenes, VNIR separated *Mikania* from "
          "native climbers with 68.7% balanced accuracy and a 7.9% false-positive rate, against "
          "53.1% and 13.5% for a colour camera. Holding out one whole site at a time gave 80.4%, "
          "but the 95% confidence interval of 50.8–98.0% shows that three sites are too few. On "
          "real Botswana satellite hyperspectral imagery, random pixel splitting reported 93.7% "
          "accuracy where spatially blocked validation reported 58.9%. These test the pipeline, "
          "not field performance."),
    ("fig", 2),
    ("h2", "The service in detail"),
    ("p", "Each survey would deliver a species and abundance map, severity-ranked work units in "
          "standard GIS formats and, after resurvey, a regrowth layer. The durable asset is the reference library linking "
          "each spectrum to a specimen, DNA identification, location and season. "
          "For standing water, a UAV deep-learning detector located 97% of potential *Aedes "
          "albopictus* breeding containers in one Chinese community (19); whether SWIR does better on "
          "Hong Kong sites is untested."),
    ("h1", "The market: customers, competitors and size"),
    ("h2", "Customers and demand"),
    ("p", "Demand for the underlying work is established; demand for Biomescan's survey is not. "
          "Hong Kong had 1,602 active construction sites in December 2025, 150 of them large and "
          "111 medium (20). FEHD spent HK$811 million on pest and rodent control services in "
          "2025–26 (6), and the Agriculture, Fisheries and Conservation Department (AFCD) includes "
          "*Mikania* removal in habitat-maintenance contracts (Biomescan review of tender "
          "documents). Likely buyers are construction contractors, pest-control operators, ecology "
          "consultancies, AFCD and conservation groups, none yet interviewed."),
    ("h2", "Competitors and substitutes"),
    ("p", "Flying is not a differentiator. FEHD already deploys its own drones with 3D mapping to "
          "find concealed stagnant water (6), and 164 organisations, including several target "
          "contractors, hold advanced drone-operation permission (Biomescan compilation of Civil "
          "Aviation Department records). Pest-control firms sell inspection programmes, walking "
          "checks are cheap, and the maximum fine for mosquito breeding, HK$25,000, caps what a "
          "site will pay to avoid it. Biomescan must instead supply what these substitutes "
          "lack: verified species identities, accuracy measured on independent sites, and outputs "
          "that change where crews work."),
    ("h2", "Market size"),
    ("p", "Table 2 gives bottom-up estimates from official counts and assumed prices; no "
          "willingness to pay has been tested. The total addressable market (TAM: all eligible "
          "units in Hong Kong and Guangdong) is HK$108–245 million a year. The serviceable "
          "addressable market (SAM: Hong Kong services the current design could deliver) is "
          "HK$8.5–18.0 million, and the serviceable obtainable market (SOM: a realistic share by "
          "year 3) is HK$0.5–1.2 million. Unbuilt standing-water surveys dominate "
          "SAM, and the *Mikania* component is least certain because local area data are 24 years "
          "old."),
    ("table", 2),
    ("h1", "Long-term vision"),
    ("h2", "Goals and milestones for the next three to five years"),
    ("p", "In year 1, Biomescan will measure field spectra of *Mikania* and native climbers across "
          "seasons, build a voucher- and barcode-verified library that adds *M. cordata* "
          "sequences, and compare SWIR with a colour camera on standing water and look-alike "
          "surfaces. It will proceed only if VNIR exceeds 75% species-versus-native accuracy on "
          "held-out sites and SWIR shows a clear advantage. In years 2–3, paid pilots with "
          "contractors and an ecology consultancy, reporting site- and season-blocked accuracy, "
          "would test whether the SOM is reachable. In years 4–5, the library would "
          "extend to Guangdong, where far more forest land carries *Mikania*, and further species "
          "would enter only through the same evidence gates. Its lasting asset, the curated link between specimens, spectra, place and "
          "season, is hard for drone operators to copy."),
]

FIGURES = {
    1: (FIG1, "Figure 1. Proposed Biomescan survey workflow.",
        "A drone (unmanned aerial vehicle, UAV) carrying a visible and near-infrared (VNIR) "
        "hyperspectral camera surveys a site (box 1). A classifier, trained and validated on field "
        "spectra verified by voucher specimens and DNA barcoding, maps *Mikania micrantha* (box 2). A "
        "geographic information system (GIS) ranks work units for field crews (boxes 3–4), and a "
        "repeat survey measures regrowth (box 5). The dashed box shows "
        "the planned shortwave-infrared (SWIR) standing-water workstream. Only the *Mikania* loop "
        "is implemented, as a research demonstrator on simulated scenes."),
    2: (FIG2, "Figure 2. Sensor choice and validation design change apparent accuracy.",
        "(A) Balanced accuracy for *Mikania micrantha* against native climbers, and "
        "false-positive rate, for three sensors outside the flowering season, from simulated "
        "Hong Kong scenes, validated leave-one-site-out over six virtual sites; error bars "
        "show one standard deviation. RGB, red-green-blue; VNIR, "
        "visible and near-infrared. (B) Overall accuracy of the same random-forest pipeline on "
        "real EO-1 Hyperion satellite imagery of Botswana when test "
        "pixels are drawn at random or held out in spatial blocks; the error bar shows the 95% "
        "bootstrap confidence interval across blocked folds."),
}

TABLES = {
    1: ("Table 1. Published accuracy of image-based detection relevant to Biomescan.",
        "Performance is as reported in each abstract and is not directly comparable, because "
        "targets, classes and test designs differ. CNN, convolutional neural network; LiDAR, light "
        "detection and ranging; PCA, principal component analysis; RGB, red-green-blue colour "
        "imagery; UAV, unmanned aerial vehicle.",
        ["Study", "Target and sensor", "Method", "Reported performance", "Validation caveat"],
        [["Asner et al. (10)", "Invasive trees, Hawaii; airborne imaging spectrometer and LiDAR",
          "Spectral mixture analysis", "Detection error <6.8% at ~7 m², <18.6% at ~2 m²",
          "Airborne, not UAV; small canopies harder"],
         ["Qiao et al. (12)", "*Mikania micrantha*; UAV RGB", "CNN (MmNet)",
          "94.50% on 400 test samples", "Small test set; site independence not reported"],
         ["Huang et al. (13)", "*Mikania micrantha*; hyperspectral imaging, 450–998 nm",
          "Smoothing, PCA and random forest", "88.71% accuracy; kappa 0.774",
          "Test design not reported in abstract"],
         ["Kattenborn et al. (15)", "Tree species; UAV imagery", "CNN segmentation",
          "Random hold-outs overestimated performance by up to 28%",
          "Spatially blocked hold-outs as benchmark"]]),
    2: ("Table 2. Estimated annual market for Biomescan services.",
        "All values are Biomescan estimates in Hong Kong dollars: official counts (5, 20) "
        "multiplied by assumed prices of HK$3,000–6,000 per standing-water site visit (seven "
        "wet-season visits a year), HK$500–1,200 per hectare of vegetation survey and "
        "HK$30,000–80,000 per consultancy subcontract. No willingness to pay has been validated. "
        "TAM, total addressable market; SAM, serviceable addressable market; SOM, serviceable "
        "obtainable market; AFCD, Agriculture, Fisheries and Conservation Department.",
        ["Market tier", "Scope", "Main components", "HK$ million per year"],
        [["TAM", "Hong Kong and Guangdong, every eligible unit",
          "1,602 construction sites; 44,842 ha of country parks; 34,500 ha of Guangdong forest "
          "land with *Mikania*, three-fold search area", "108–245"],
         ["SAM", "Hong Kong services the current design could deliver",
          "261 large and medium sites; 40 consultancy projects; AFCD habitat sites; 1,000 ha of "
          "*Mikania* hotspots surveyed twice", "8.5–18.0"],
         ["SOM", "Obtainable by year 3",
          "13 construction sites; 4–6 consultancy projects; one habitat-monitoring pilot",
          "0.5–1.2"]]),
}

REFERENCES = [
    "Diagne, C., Leroy, B., Vaissière, A. C., Gozlan, R. E., Roiz, D., Jarić, I., et al. (2021) "
    "High and rising economic costs of biological invasions worldwide. Nature. 592, 571-576",
    "Zhang, L. Y., Ye, W. H., Cao, H. L., and Feng, H. L. (2004) *Mikania micrantha* H. B. K. in "
    "China – an overview. Weed Res. 44, 42-49",
    "Day, M. D., Clements, D. R., Gile, C., Senaratne, W. K. A. D., Shen, S., Weston, L. A., et "
    "al. (2016) Biology and impacts of Pacific Islands invasive species. 13. *Mikania micrantha* "
    "Kunth (Asteraceae). Pac Sci. 70, 257-285",
    "Liu, B., Yan, J., Li, W., Yin, L., Li, P., Yu, H., et al. (2020) *Mikania micrantha* genome "
    "provides insights into the molecular mechanism of rapid growth. Nat Commun. 11, 340",
    "Department of Natural Resources of Guangdong Province (2025) Reply to proposal No. 1012 of "
    "the Third Session of the 14th Guangdong Provincial People's Congress [in Chinese]. "
    "https://nr.gd.gov.cn/gkmlpt/content/4/4742/post_4742701.html",
    "Environment and Ecology Bureau and Food and Environmental Hygiene Department (2026) Pest "
    "control and environmental hygiene enhancement work. LC Paper No. CB(2)479/2026(03). "
    "https://www.legco.gov.hk/yr2026/english/panels/fseh/papers/fseh20260421-cb2-479-3-e.pdf",
    "Han, S., Miot, E. F., Liao, Y., Khan, M. A., Rivot, M., Tang, L. T., et al. (2025) "
    "Insecticide resistance levels, spatial distribution, and kdr mutations in the dengue vector "
    "*Aedes albopictus* of Hong Kong. PLoS Negl Trop Dis. 19, e0013792",
    "Horler, D. N. H., Dockray, M., and Barber, J. (1983) The red edge of plant leaf reflectance. "
    "Int J Remote Sens. 4, 273-288",
    "He, K. S., Rocchini, D., Neteler, M., and Nagendra, H. (2011) Benefits of hyperspectral "
    "remote sensing for tracking plant invasions. Divers Distrib. 17, 381-392",
    "Asner, G. P., Knapp, D. E., Kennedy-Bowdoin, T., Jones, M. O., Martin, R. E., Boardman, J., "
    "et al. (2008) Invasive species detection in Hawaiian rainforests using airborne imaging "
    "spectroscopy and LiDAR. Remote Sens Environ. 112, 1942-1955",
    "Bradley, B. A. (2014) Remote detection of invasive plants: a review of spectral, textural "
    "and phenological approaches. Biol Invasions. 16, 1411-1425",
    "Qiao, X., Li, Y. Z., Su, G. Y., Tian, H. K., Zhang, S., Sun, Z. Y., et al. (2020) MmNet: "
    "identifying *Mikania micrantha* Kunth in the wild via a deep convolutional neural network. "
    "J Integr Agric. 19, 1292-1300",
    "Huang, Y., Li, J., Yang, R., Wang, F., Li, Y., Zhang, S., et al. (2021) Hyperspectral imaging "
    "for identification of an invasive plant *Mikania micrantha* Kunth. Front Plant Sci. 12, "
    "626516",
    "Roberts, D. R., Bahn, V., Ciuti, S., Boyce, M. S., Elith, J., Guillera-Arroita, G., et al. "
    "(2017) Cross-validation strategies for data with temporal, spatial, hierarchical, or "
    "phylogenetic structure. Ecography. 40, 913-929",
    "Kattenborn, T., Schiefer, F., Frey, J., Feilhauer, H., Mahecha, M. D., and Dormann, C. F. "
    "(2022) Spatially autocorrelated training and validation samples inflate performance "
    "assessment of convolutional neural networks. ISPRS Open J Photogramm Remote Sens. 5, 100018",
    "Meiklejohn, K. A., Damaso, N., and Robertson, J. M. (2019) Assessment of BOLD and GenBank – "
    "their accuracy and reliability for the identification of biological materials. PLoS One. "
    "14, e0217084",
    "Northcutt, C., Jiang, L., and Chuang, I. (2021) Confident learning: estimating uncertainty "
    "in dataset labels. J Artif Intell Res. 70, 1373-1411",
    "CBOL Plant Working Group (2009) A DNA barcode for land plants. Proc Natl Acad Sci U S A. "
    "106, 12794-12797",
    "Yu, K., Wu, J., Wang, M., Cai, Y., Zhu, M., Yao, S., et al. (2024) Using UAV images and deep "
    "learning in investigating potential breeding sites of *Aedes albopictus*. Acta Trop. 255, "
    "107234",
    "Census and Statistics Department (2026) Quarterly report of manual workers and vacancies at "
    "construction sites, December 2025. "
    "https://www.censtatd.gov.hk/en/wbr.html?ecode=B10500042025QQ04",
]

# --------------------------------------------------------------------------
# docx helpers
# --------------------------------------------------------------------------
EXCLUDED_STYLE = "Front Matter"   # paragraphs not counted as words
LEGEND_STYLE = "Legend"
REF_STYLE = "Reference"


def set_run_font(run, size=12, bold=None, italic=None):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def style_font(style):
    style.font.name = FONT
    style.font.size = Pt(12)
    style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)
    for theme_attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if fonts.get(qn(theme_attr)) is not None:
            del fonts.attrib[qn(theme_attr)]
    pf = style.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)


def double(p):
    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    if pf.space_before is None:
        pf.space_before = Pt(0)
    pf.space_after = Pt(0)


TOKEN = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")


def add_marked(p, text, bold=False, italic=False):
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**"):
            set_run_font(p.add_run(part[2:-2]), bold=True, italic=italic)
        elif part.startswith("*"):
            set_run_font(p.add_run(part[1:-1]), bold=bold, italic=not italic)
        else:
            set_run_font(p.add_run(part), bold=bold, italic=italic)


def para(doc, text="", style=None, align=None, bold=False, italic=False, indent=True):
    p = doc.add_paragraph(style=style)
    add_marked(p, text, bold=bold, italic=italic)
    double(p)
    if align is not None:
        p.alignment = align
    return p


def heading(doc, text, level):
    p = doc.add_paragraph(style=f"Heading {level}")
    # Level 1: bold; level 2: bold italic. Both 12 pt, black, Times New Roman.
    add_marked(p, text, bold=True, italic=(level == 2))
    double(p)
    p.paragraph_format.keep_with_next = True
    return p


def build(word_total="[count]", abstract_words="[count]"):
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.PORTRAIT
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(2.54))

    styles = doc.styles
    for name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "Title", "Caption"):
        style_font(styles[name])
    for name in (EXCLUDED_STYLE, LEGEND_STYLE, REF_STYLE):
        st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = styles["Normal"]
        style_font(st)
    styles["Heading 1"].font.bold = True
    styles["Heading 2"].font.bold = True
    styles["Heading 2"].font.italic = True
    ref_pf = styles[REF_STYLE].paragraph_format
    ref_pf.left_indent = Cm(0.9)
    ref_pf.first_line_indent = Cm(-0.9)

    # ---- title page
    p = para(doc, TITLE, align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    p.paragraph_format.space_before = Pt(72)
    para(doc, "[Full name]", style=EXCLUDED_STYLE, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "Biomescan; School of Biomedical Sciences, The University of Hong Kong",
         style=EXCLUDED_STYLE, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "Correspondence: [Email]", style=EXCLUDED_STYLE, align=WD_ALIGN_PARAGRAPH.CENTER)
    p = para(doc, f"Word count: {word_total} (title, abstract, main text, figure and table "
                  f"legends, table text and references)", style=EXCLUDED_STYLE,
             align=WD_ALIGN_PARAGRAPH.CENTER)
    p.paragraph_format.space_before = Pt(260)
    br = p.add_run()
    set_run_font(br)
    br.add_break(WD_BREAK.PAGE)

    # ---- abstract
    heading(doc, "Abstract", 1)
    para(doc, ABSTRACT)
    para(doc, f"Abstract word count: {abstract_words}", style=EXCLUDED_STYLE)
    br = doc.add_paragraph().add_run()
    set_run_font(br)
    br.add_break(WD_BREAK.PAGE)

    # ---- body
    for kind, val_ in BODY:
        if kind == "h1":
            heading(doc, val_, 1)
        elif kind == "h2":
            heading(doc, val_, 2)
        elif kind == "p":
            p = para(doc, val_)
            p.paragraph_format.first_line_indent = Cm(1.0)
        elif kind == "fig":
            path, title, legend = FIGURES[val_]
            p = doc.add_paragraph()
            double(p)
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.DOUBLE
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.keep_with_next = True
            pic = p.add_run()
            set_run_font(pic)
            pic.add_picture(str(path), width=Cm(15.5))
            lp = doc.add_paragraph(style=LEGEND_STYLE)
            add_marked(lp, f"**{title}**")
            set_run_font(lp.add_run(" "))
            add_marked(lp, legend)
            double(lp)
        elif kind == "table":
            title, legend, header, rows = TABLES[val_]
            lp = doc.add_paragraph(style=LEGEND_STYLE)
            add_marked(lp, f"**{title}**")
            set_run_font(lp.add_run(" "))
            add_marked(lp, legend)
            double(lp)
            lp.paragraph_format.keep_with_next = True
            t = doc.add_table(rows=1 + len(rows), cols=len(header))
            t.style = doc.styles["Table Grid"]
            t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(header):
                cell = t.rows[0].cells[j]
                cp = cell.paragraphs[0]
                add_marked(cp, h, bold=True)
                double(cp)
            for i, row in enumerate(rows, start=1):
                for j, txt in enumerate(row):
                    cp = t.rows[i].cells[j].paragraphs[0]
                    add_marked(cp, txt)
                    double(cp)
            doc.add_paragraph()  # spacer after table
            double(doc.paragraphs[-1])

    # ---- references
    heading(doc, "References", 1)
    for i, r in enumerate(REFERENCES, start=1):
        p = para(doc, f"{i}. {r}", style=REF_STYLE)

    # make sure every paragraph (including the empty ones) is double spaced
    for p in doc.paragraphs:
        double(p)
    doc.save(OUT)


# --------------------------------------------------------------------------
# Counting and checks, read back from the saved .docx
# --------------------------------------------------------------------------
WORD = re.compile(r"\S+")


def words(text):
    return [w for w in WORD.findall(text) if re.search(r"[A-Za-z0-9]", w)]


def body_items(doc):
    """Yield ('p', paragraph) and ('t', table) in document order."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "p", Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield "t", Table(child, doc)


def analyse():
    doc = Document(OUT)
    total, abstract, legends = 0, None, {}
    seq_text = []  # (kind, text) in order, for citation checks
    in_abstract = False
    for kind, obj in body_items(doc):
        if kind == "p":
            style = obj.style.name
            text = obj.text
            if style == EXCLUDED_STYLE:
                continue
            n = len(words(text))
            total += n
            if text == "Abstract" and style.startswith("Heading"):
                in_abstract = True
                continue
            if in_abstract and text.strip():
                abstract = n
                in_abstract = False
            if style == LEGEND_STYLE:
                key = text.split(".")[0]
                legends[key] = n
                seq_text.append(("legend", text))
            elif style != REF_STYLE:
                seq_text.append(("text", text))
        else:
            for row in obj.rows:
                for cell in row.cells:
                    total += len(words(cell.text))
                    seq_text.append(("text", cell.text))
    return doc, total, abstract, legends, seq_text


def check(doc, seq_text, legends):
    problems = []
    # title
    if len(TITLE) > 100:
        problems.append(f"title is {len(TITLE)} characters")
    # references
    if len(REFERENCES) > 20:
        problems.append("more than 20 references")
    cited = []
    cite_re = re.compile(r"\((\d+(?:[–-]\d+)?(?:,\s*\d+(?:[–-]\d+)?)*)\)")
    for _, text in seq_text:
        for m in cite_re.finditer(text):
            for part in m.group(1).split(","):
                part = part.strip()
                if re.search(r"[–-]", part):
                    a, b = map(int, re.split(r"[–-]", part))
                    cited.extend(range(a, b + 1))
                else:
                    cited.append(int(part))
    first = []
    for c in cited:
        if c not in first:
            first.append(c)
    if first != list(range(1, len(REFERENCES) + 1)):
        problems.append(f"reference first-appearance order is {first}")
    # figure/table citation order in the running text (legends excluded)
    figs, tabs = [], []
    for kind, text in seq_text:
        if kind != "text":
            continue
        for m in re.finditer(r"\bFig\.\s*(\d+)", text):
            if int(m.group(1)) not in figs:
                figs.append(int(m.group(1)))
        for m in re.finditer(r"\bTable\s+(\d+)", text):
            if int(m.group(1)) not in tabs:
                tabs.append(int(m.group(1)))
    if figs != sorted(FIGURES):
        problems.append(f"figure citation order {figs}")
    if tabs != sorted(TABLES):
        problems.append(f"table citation order {tabs}")
    for k, n in legends.items():
        if n > 150:
            problems.append(f"{k} legend has {n} words")
    # formatting
    sec = doc.sections[0]
    if abs(sec.page_width.mm - 210) > 0.5 or abs(sec.page_height.mm - 297) > 0.5:
        problems.append("page size is not A4")
    all_pars = list(doc.paragraphs)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                all_pars.extend(cell.paragraphs)
    for p in all_pars:
        if p.paragraph_format.line_spacing_rule != WD_LINE_SPACING.DOUBLE:
            problems.append(f"not double spaced: {p.text[:40]!r}")
            break
    for p in all_pars:
        for r in p.runs:
            fonts = r._element.rPr.find(qn("w:rFonts")) if r._element.rPr is not None else None
            ok = (r.font.name == FONT and r.font.size == Pt(12) and fonts is not None
                  and fonts.get(qn("w:eastAsia")) == FONT)
            if not ok:
                problems.append(f"font not Times New Roman 12 pt: {r.text[:40]!r}")
                break
    return problems


if __name__ == "__main__":
    build()
    doc, total, abstract, legends, seq = analyse()
    build(word_total=f"{total:,}", abstract_words=str(abstract))   # writes the true count
    doc, total2, abstract2, legends2, seq2 = analyse()
    assert total2 == total and abstract2 == abstract, "count changed between passes"
    issues = check(doc, seq2, legends2)
    print(f"Total words (counted from .docx): {total2}")
    print(f"Abstract words: {abstract2}")
    for k, n in legends2.items():
        print(f"{k} legend words: {n}")
    print(f"References: {len(REFERENCES)}; title characters: {len(TITLE)}")
    print("Checks:", "all passed" if not issues else issues)
    if total2 > 2500 or abstract2 > 250:
        raise SystemExit("word limit exceeded")
