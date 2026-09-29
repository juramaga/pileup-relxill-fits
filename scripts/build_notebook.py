"""
Builds notebook/relxill_pileup_fitting.ipynb from scratch (nbformat v4).

Design choice: the notebook *live-fits* only the fast, safe pieces (Stage B
for both spectra -- a few seconds for unpiled, ~50s for piled) so that
running it top-to-bottom is quick and reproducible. The full 24-combo grid
(Phase 4) and the conf-vs-covar comparison (Phase 5, ~2490s for the piled
`conf` alone) are loaded from the results/ JSON files already produced by
scripts/run_fits.py and scripts/run_conf_flagship.py rather than
recomputed -- re-running those from the notebook would make "run all cells"
take the better part of an hour and would re-risk the Stage A piled crash
(see CLAUDE.md Phase 4) inside the kernel. The Stage A crash itself is
described in markdown, not reproduced live, for the same reason: it would
kill the notebook kernel.

Not itself a deliverable -- run once to (re)generate the notebook.
"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []


def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))


def code(text):
    cells.append(nbf.v4.new_code_cell(text))


md(r"""# relxill fits of MARX-simulated Chandra spectra: ID 1000000081 (heavy pileup) and ID 1000001838 (moderate pileup)
### piled-up vs. unpiled, Sherpa (CIAO 4.17) + relxill, multiple optimizers

**Part 1** (below) is the original, heavily piled-up target, ID 1000000081
(~93% of incident events lost to pileup; N(unpiled)/N(piled) = 14.3).
**Part 2** (after Part 1's summary) repeats the whole procedure for
ID 1000001838, a *moderately* piled-up simulation (~30% count loss;
N(unpiled)/N(piled) = 1.43) with physics close to 081's, and ends with a
side-by-side comparison of the two.

# Part 1 -- ID 1000000081 (heavy pileup)

This notebook is a runnable walkthrough of the project documented in full
in `../CLAUDE.md` (methodology / decisions / Phases 1-5) and
`../results/report.md` (the complete fit-metrics report). It does not
repeat every decision made along the way -- see those two files for the
full reasoning, including why particular choices were made (statistic,
freezing stages, pileup parameters, etc).

**What this notebook does live**: loads the two spectra, builds three
Stage-B models -- (1) `tbabs*relxill` on the unpiled spectrum, (2) the same
wrapped in `jdpileup` on the piled spectrum (the physically correct
treatment), and (3) the same **piled** spectrum fit with the **plain,
uncorrected** `tbabs*relxill` model (no `jdpileup` at all -- the mistake an
analyst makes by not accounting for pileup) -- fits all three, and plots
the results. The third case was added specifically to answer: *how much
does it actually matter whether you correct for pileup?*

**What it loads from disk instead of recomputing**: the full 36-combination
(3 spectrum/model cases x 4 freezing stages x 3 optimizers) fit grid from
Phase 4, and the `conf`-vs-`covar` comparison from Phase 5 -- the former
because several of those combinations are slow (`moncar` in particular) and
some combinations (Stage A on either piled case) crash the Python process
outright by design of relxill's own error handling (see Phase 4 in
`CLAUDE.md`), and the latter because the piled spectrum's `conf`
calculation alone takes ~40 minutes. Re-running `../scripts/run_fits.py`
and `../scripts/run_conf_flagship.py` reproduces those files if wanted.""")

code(r"""import os
import sys
from pathlib import Path

NB_DIR = Path.cwd()
PROJECT_ROOT = NB_DIR.parent if (NB_DIR / "scripts").exists() is False else NB_DIR
# works whether the notebook is run from notebook/ or the project root
if (NB_DIR / "scripts").exists():
    PROJECT_ROOT = NB_DIR
else:
    PROJECT_ROOT = NB_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
os.environ.setdefault("RELXILL_TABLE_PATH", str(PROJECT_ROOT / "relxill" / "tables"))

%matplotlib inline
import json
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import HTML, display

from sherpa.astro import ui
import relxill.ui  # noqa: F401  registers xsumrelxill etc. with Sherpa

from load_data import setup_data, TARGET_ID
from build_models import (
    build_unpiled_model, build_piled_model, build_piled_naive_model,
    GROUND_TRUTH,
)

RESULTS = PROJECT_ROOT / "results"
print(f"project root: {PROJECT_ROOT}")
print(f"target spectrum ID: {TARGET_ID}")""")

md(r"""## Ground truth (simulation input parameters)

This is simulated data, so the true parameters used to generate spectrum
1000000081 are known (from `v0017_800ks_index.csv`) -- used here only to
*check* the fit afterwards, never fed into it as a starting value or
constraint (Stage D is a deliberate, explicitly-flagged exception -- see
`CLAUDE.md` Phase 3).""")

code(r"""for k, v in GROUND_TRUTH.items():
    print(f"{k:10s} = {v}")""")

md(r"""## Load the two spectra (Phase 2)

`setup_data()` loads the unpiled and piled PHA files (written by
`../scripts/extract_spectrum.py` from the big MARX data table), attaches
their shared RMF/ARF, notices the 0.3-10 keV range (matches the response's
native energy grid), and sets the fit statistic to `cstat` (no background
spectrum exists for either PHA -- see `CLAUDE.md` Phase 2 for why `cstat`
over `wstat`/`chi2`).""")

code(r"""id_unpiled, id_piled = setup_data()

for idname in (id_unpiled, id_piled):
    d = ui.get_data(idname)
    print(f"{idname:8s}  exposure={d.exposure:.0f}s  "
          f"counts(noticed)={d.get_dep(filter=True).sum():.0f}  "
          f"nbins(noticed)={d.get_dep(filter=True).size}")
print("statistic:", ui.get_stat_name())""")

md(r"""## Build the models (Phase 3)

- **Unpiled**: `xstbabs * xsumrelxill`
- **Piled**: same source model, wrapped with a `jdpileup` component via
  `set_pileup_model()` -- Sherpa inserts pileup (and folds the ARF in
  internally) between the source model and the RMF, which is where it
  physically belongs.
- **Piled, uncorrected ("piled_naive")**: the *same* piled data, fit with
  the plain `xstbabs * xsumrelxill` model -- no `jdpileup` at all. Note:
  `build_piled_naive_model()` explicitly deletes any pileup model already
  attached to the piled dataset first, since Sherpa keeps a dataset's
  pileup model separate from its source model -- otherwise building this
  right after the jdpileup-corrected model above would silently leave the
  old pileup wrap active underneath what's supposed to be the uncorrected
  fit (a real bug hit once while making this project's diagnostic plots).

All three use **Stage B** here: the literature-standard freezing (`Rin=-1`
tied to the ISCO, `Rout=400`, single-power-law emissivity, `Ecut=300` keV
fixed -- a single CCD-resolution spectrum has essentially no leverage on
any of these). Free parameters: `nH, a, Incl, gamma, logxi, Afe,
refl_frac, norm` (+ pileup's `alpha, f` for the jdpileup-corrected piled
case only). See `CLAUDE.md` Phase 3 for the full Stage A-D ladder and the
reasoning behind each freeze -- this notebook only reproduces Stage B
live; the other three stages' results are loaded from disk further down.""")

code(r"""STAGE = "B"

abs_u, rel_u = build_unpiled_model(id_unpiled, STAGE)
print("--- unpiled full model ---")
print(ui.get_model(id_unpiled))""")

code(r"""abs_p, rel_p, pmod_p = build_piled_model(id_piled, STAGE)
print("--- piled full model (jdpileup-corrected) ---")
print(ui.get_model(id_piled))""")

md(r"""## Fit Stage B live (Phase 4)

Using `levmar` for the unpiled spectrum and `neldermead` for the piled
one -- these are the methods that turned out to reach the best
*formally-converged* minimum for each spectrum at Stage B in the full
Phase 4 grid (see `../results/report.md`; `levmar` gets stuck in a poor
local minimum on the piled data at every stage, which is itself one of
the more interesting findings there).""")

code(r"""ui.set_method("levmar")
ui.set_method_opt("maxfev", 1600)
ui.fit(id_unpiled)
fr_u = ui.get_fit_results()
print(fr_u)""")

code(r"""ui.set_method("neldermead")
ui.set_method_opt("maxfev", 4000)
ui.fit(id_piled)  # ~40-60s
fr_p = ui.get_fit_results()
print(fr_p)""")

md(r"""Now the third case -- same piled data, `jdpileup` removed, plain
`tbabs*relxill` fit from scratch. This answers the question this case was
added for: does the fit *look* obviously wrong if you forget to correct
for pileup?""")

code(r"""abs_pn, rel_pn = build_piled_naive_model(id_piled, STAGE)
print("--- piled full model (NOT corrected for pileup) ---")
print(ui.get_model(id_piled))

ui.set_method("neldermead")
ui.set_method_opt("maxfev", 4000)
ui.fit(id_piled)  # ~20s
fr_pn = ui.get_fit_results()
print(fr_pn)""")

md("## Diagnostic plots: data, model, and ratio, all three cases")

code(r"""def plot_fit(fit_id, title, ax_top, ax_bot):
    dplot = ui.get_data_plot(fit_id)
    mplot = ui.get_model_plot(fit_id)
    rplot = ui.get_ratio_plot(fit_id)

    ax_top.errorbar(dplot.x, dplot.y, yerr=dplot.yerr, fmt=".", ms=2,
                     color="black", ecolor="0.7", elinewidth=0.5, label="data")
    ax_top.plot(mplot.x, mplot.y, color="crimson", lw=1.2, label="model")
    ax_top.set_yscale("log"); ax_top.set_xscale("log")
    ax_top.set_ylabel("counts / s / keV")
    ax_top.set_title(title)
    ax_top.legend(fontsize=8, loc="lower left")

    ax_bot.axhline(1.0, color="0.5", lw=0.8)
    ax_bot.errorbar(rplot.x, rplot.y, yerr=rplot.yerr, fmt=".", ms=2,
                     color="black", ecolor="0.7", elinewidth=0.5)
    ax_bot.set_xscale("log")
    ax_bot.set_ylabel("data / model"); ax_bot.set_xlabel("Energy (keV)")


# re-fit unpiled and jdpileup-corrected piled since id_piled's source model
# now points at the uncorrected fit above -- rebuild+refit each in turn so
# every panel below reflects its own case's actual best fit
build_unpiled_model(id_unpiled, STAGE)
ui.set_method("levmar"); ui.set_method_opt("maxfev", 1600)
ui.fit(id_unpiled)
fr_u = ui.get_fit_results()

build_piled_model(id_piled, STAGE)
ui.set_method("neldermead"); ui.set_method_opt("maxfev", 4000)
ui.fit(id_piled)
fr_p = ui.get_fit_results()

fig, axes = plt.subplots(2, 3, figsize=(16, 6), sharex="col",
                           gridspec_kw=dict(height_ratios=[3, 1], hspace=0.05))
plot_fit(id_unpiled, f"unpiled, Stage B (cstat={fr_u.statval:.1f})",
         axes[0, 0], axes[1, 0])
plot_fit(id_piled, f"piled, corrected, Stage B (cstat={fr_p.statval:.1f})",
         axes[0, 1], axes[1, 1])

build_piled_naive_model(id_piled, STAGE)
ui.set_method("neldermead"); ui.set_method_opt("maxfev", 4000)
ui.fit(id_piled)
fr_pn = ui.get_fit_results()
plot_fit(id_piled, f"piled, UNCORRECTED, Stage B (cstat={fr_pn.statval:.1f})",
         axes[0, 2], axes[1, 2])

fig.tight_layout()
plt.show()""")

md(r"""Note how visually similar the "corrected" and "uncorrected" piled
panels are, and how close their `cstat` values are -- this is the
headline point of adding this third case: **you cannot tell from fit
quality alone whether pileup was actually corrected for.**""")

md(r"""## Full Phase 4 grid (loaded from disk)

All 36 (spectrum/model-case x stage x method) combinations -- see
`../CLAUDE.md` Phase 4 for why this is loaded rather than recomputed live
(runtime, and the Stage A crash on either piled case). Each combination in
the original run was executed as its own subprocess for exactly that
crash-safety reason.""")

code(r"""def html_table(headers, rows):
    th = "".join(f"<th style='text-align:left;padding:2px 8px'>{h}</th>" for h in headers)
    trs = []
    for row in rows:
        tds = "".join(f"<td style='padding:2px 8px'>{c}</td>" for c in row)
        trs.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


with open(RESULTS / "fits_raw.json") as f:
    raw = json.load(f)
records = raw["records"]

STAGES = ["A", "B", "C", "D"]
METHODS = ["levmar", "neldermead", "moncar"]

SPECTRA = ["unpiled", "piled", "piled_naive"]

for spectrum in SPECTRA:
    rows = []
    for stage in STAGES:
        for method in METHODS:
            r = next((r for r in records if r["spectrum"] == spectrum
                       and r["stage"] == stage and r["method"] == method), None)
            if r is None:
                continue
            if r.get("message") in ("CRASHED", "TIMEOUT", "PYTHON_EXCEPTION"):
                rows.append([stage, method, f"<b>{r['message']}</b>", "-", "-", "-", "-"])
                continue
            rows.append([stage, method, r.get("succeeded"),
                         f"{r.get('statval'):.1f}" if r.get('statval') is not None else "-",
                         f"{r.get('rstat'):.2f}" if r.get('rstat') is not None else "-",
                         r.get("nfev"), f"{r.get('wall_time_s'):.1f}"])
    display(HTML(f"<h4>{spectrum}</h4>"))
    display(HTML(html_table(
        ["stage", "method", "converged", "cstat", "reduced stat", "nfev", "time (s)"],
        rows)))""")

md(r"""Note the `CRASHED` rows for Stage A on *both* piled cases --
`piled` (jdpileup-corrected, 15 free params) and `piled_naive` (plain
model, 13 free params -- the same count as `unpiled`, which never
crashes). relxill's C++ code calls a hard, uncatchable process abort on an
unphysical `Rout<=Rin` parameter excursion; the fact that it happens for
`piled_naive` too shows this is driven by the *piled data's shape itself*
sending the optimizer somewhere the unpiled data never goes, not merely by
pileup's extra free parameters. This is not reproduced live in this
notebook for the obvious reason that it would take the kernel down with
it -- see `CLAUDE.md` Phase 4 for the full account, including why this is
treated as a genuine finding (Stage A is numerically intractable for the
piled spectrum, corrected or not) rather than a bug to silently work
around.""")

md(r"""## Ground-truth comparison and conf-vs-covar (Phase 5, loaded from disk)

`results/analysis_summary.json` has the best-fit-vs-truth comparison for
every stage; `results/conf_flagship.json` has the profile-likelihood
(`conf`) vs. covariance-matrix (`covar`) comparison for the Stage B
flagship fits shown above. See `../results/report.md` for the full
discussion -- this cell reproduces just the Stage B numbers relevant to
the fit above.""")

code(r"""with open(RESULTS / "analysis_summary.json") as f:
    summary = json.load(f)

gt_labels = {"a": "spin (a)", "Incl": "Incl (deg)", "gamma": "gamma",
             "logxi": "logxi", "Afe": "Afe", "refl_frac": "refl_frac",
             "nH": "nH (1e22 cm^-2)"}
gt_key_map = {"a": "spin", "Incl": "incl"}

# headline: all three cases side by side (the comparison this third case
# was specifically added for)
rows = []
for short, label in gt_labels.items():
    truth = GROUND_TRUTH.get(gt_key_map.get(short, short))
    cells = []
    for spectrum in ("unpiled", "piled", "piled_naive"):
        c = summary["ground_truth_comparison"][f"{spectrum}/B"]["comparison"].get(short)
        cells.append(f"{c['fitted']:.4g} ({c['rel_diff_pct']:+.1f}%)" if c else "-")
    rows.append([label, f"{truth:.4g}"] + cells)
display(HTML("<h4>Headline: Stage B, all three cases vs. ground truth</h4>"))
display(HTML(html_table(
    ["parameter", "truth", "unpiled", "piled (corrected)", "piled_naive (uncorrected)"],
    rows)))""")

md(r"""**Reading this table**: spin is severely biased high in *both*
piled cases (~76-78%) regardless of jdpileup correction -- the correction
does not rescue the spin measurement here. `refl_frac` is the parameter
most sensitive to *whether* pileup was corrected for (+134% uncorrected
vs. +34% corrected vs. +65% for the unpiled fit itself -- the last of
those likely tangled up with the known `norm` convention mismatch from
Phase 3, not a pileup effect). Inclination and `nH` are comparatively
robust in all three cases. Full discussion: `../results/report.md`.""")

code(r"""for spectrum in ("unpiled", "piled", "piled_naive"):
    comp = summary["ground_truth_comparison"][f"{spectrum}/B"]["comparison"]
    rows = []
    for short, label in gt_labels.items():
        c = comp.get(short)
        if c is None:
            continue
        rows.append([label, f"{c['fitted']:.4g}", f"{c['truth']:.4g}",
                     f"{c['rel_diff_pct']:.1f}%"])
    display(HTML(f"<h4>{spectrum}, Stage B vs. ground truth</h4>"))
    display(HTML(html_table(["parameter", "fitted", "truth", "rel. diff"], rows)))""")

code(r"""with open(RESULTS / "conf_flagship.json") as f:
    conf_flag = json.load(f)

for spectrum in ("unpiled", "piled", "piled_naive"):
    flag = conf_flag[spectrum]
    rows = []
    for name, val, clo, chi, klo, khi in zip(
            flag["parnames"], flag["parvals"],
            flag["covar_parmins"], flag["covar_parmaxes"],
            flag["conf_parmins"], flag["conf_parmaxes"]):
        short = name.split(".")[-1]
        covar_s = "undefined" if clo is None or chi is None else f"[{clo:+.4g}, {chi:+.4g}]"
        klo_s = "(boundary)" if klo is None else f"{klo:+.4g}"
        khi_s = "(boundary)" if khi is None else f"{khi:+.4g}"
        conf_s = "undefined" if klo is None and khi is None else f"[{klo_s}, {khi_s}]"
        rows.append([short, f"{val:.4g}", covar_s, conf_s])
    display(HTML(f"<h4>{spectrum}, Stage B: covar vs. conf "
                   f"(covar {flag['covar_time_s']:.1f}s, conf {flag['conf_time_s']:.1f}s)</h4>"))
    display(HTML(html_table(["parameter", "best fit", "covar 1-sigma", "conf 1-sigma"], rows)))""")

md(r"""## Summary

- All three spectra/cases fit reasonably well visually (few-percent
  residuals across most of the 0.3-10 keV band) at Stage B, despite
  reduced stat > 1 in every case -- with millions of counts, `cstat` has
  enough statistical power to detect small systematic mismatches that
  wouldn't show up in a lower-count spectrum.
- **A good fit statistic does not tell you whether pileup was corrected
  for**: the uncorrected `piled_naive` fit is statistically as good as (or
  marginally better than) the jdpileup-corrected `piled` fit, and looks
  just as good in the diagnostic plots above.
- **Correcting for pileup with jdpileup does not rescue the spin
  measurement** for this source/pileup level -- both piled cases are
  biased ~76-78% high relative to the close-to-truth unpiled fit.
  `refl_frac` is the parameter that most clearly tracks whether pileup was
  corrected for, even though it doesn't track spin's bias.
- `conf` and `covar` genuinely disagree, and `covar` failed outright on
  both piled fits (corrected and uncorrected) -- don't trust `covar` alone
  on a highly nonlinear, many-parameter model like this.
- The progressive freezing ladder (Stage A -> D) is not just a
  dimensionality-reduction convenience: Stage A is numerically
  intractable for *either* piled case (hard crash, all three optimizers,
  regardless of whether jdpileup's extra parameters are present), and
  Stage C's "standard" solar-abundance assumption actively hurts the fit
  for this particular (super-solar Afe) simulated source.

Full discussion, all four stages, and the three-way pileup-bias
comparison: `../results/report.md`. Full methodology and decision log:
`../CLAUDE.md`. Didactic write-up: `../writeup/`.""")

# ---------------------------------------------------------------------------
# Part 2: ID 1000001838 (moderate pileup)
# ---------------------------------------------------------------------------

md(r"""# Part 2 -- ID 1000001838 (moderate pileup)

Same procedure, second simulation. Why this one: 081 sits at the extreme
end of the grid's pileup distribution (~15 incident counts per 3.2 s frame,
93% count loss). 1838 was picked from the ~30%-count-loss population as the
case whose simulation inputs are closest to 081's (Gamma~1.39 vs 1.33,
a~0.42 vs 0.49, i~26 deg vs 31, same nH, same detector position/RMF), so
the comparison mostly isolates the *pileup level*. The main physics
differences: 1838 is much fainter (~25x fewer counts), iron-richer
(Afe~7.3 vs 2.6) and more ionized (logxi~2.4 vs 1.5).

Everything below uses the same scripts as Part 1 -- they select the
spectrum via the `TARGET_ID` environment variable (see
`../scripts/target.py`) and write this ID's outputs under
`../results/id1000001838/`:

```
TARGET_ID=1000001838 python extract_spectrum.py 1000001838
TARGET_ID=1000001838 python run_fits.py          # 36-combo grid
TARGET_ID=1000001838 python run_multistart.py    # new: Stage B multi-start
TARGET_ID=1000001838 python analyze_results.py
TARGET_ID=1000001838 python run_conf_flagship.py
TARGET_ID=1000001838 python make_plots.py
TARGET_ID=1000001838 python write_report.py
```

One step is new relative to Part 1 -- a **multi-start check of Stage B**
-- for a reason that shows up in the live fits just below.""")

code(r"""from target import load_ground_truth, flagship_records

ID2 = 1000001838
RESULTS2 = PROJECT_ROOT / "results" / f"id{ID2}"
GT2 = load_ground_truth(ID2)

ui.clean()  # drop Part 1's datasets/models; relxill stays registered
id_unpiled, id_piled = setup_data(target_id=ID2)

n = {}
for idname in (id_unpiled, id_piled):
    d = ui.get_data(idname)
    n[idname] = d.get_dep(filter=True).sum()
    print(f"{idname:8s}  exposure={d.exposure:.0f}s  counts(noticed)={n[idname]:.0f}")
print(f"N(unpiled)/N(piled) in 0.3-10 keV = {n[id_unpiled] / n[id_piled]:.3f}")
print()
for k, v in GT2.items():
    print(f"{k:10s} = {v:.4g}")""")

md(r"""## Stage B live fits from the canonical starting point

Exactly the protocol of Part 1 / Phase 4: every thawed parameter starts
from the same generic values (`build_models.RELXILL_START`: a=0.998,
logxi=3.1, Afe=1, refl_frac=3, ...), then `levmar`.""")

code(r"""def short_pars(models):
    return {p.name: p.val for m in models for p in m.pars if not p.frozen}

def fit_levmar(fit_id):
    ui.set_method("levmar"); ui.set_method_opt("maxfev", 2000)
    ui.fit(fit_id)
    return ui.get_fit_results()

canon = {}
m_u = build_unpiled_model(id_unpiled, STAGE)
canon["unpiled"] = (fit_levmar(id_unpiled).statval, short_pars(m_u))
m_p = build_piled_model(id_piled, STAGE)
canon["piled"] = (fit_levmar(id_piled).statval, short_pars(m_p))
m_pn = build_piled_naive_model(id_piled, STAGE)
canon["piled_naive"] = (fit_levmar(id_piled).statval, short_pars(m_pn))

for case, (stat, pars) in canon.items():
    print(f"{case:12s} cstat={stat:8.1f}  a={pars['a']:+.3f}  "
          f"refl_frac={pars['refl_frac']:+.2f}  logxi={pars['logxi']:.2f}  "
          f"Afe={pars['Afe']:.2f}")""")

md(r"""Look at the jdpileup-corrected `piled` row: `refl_frac` comes out
**negative**. In relxill, `refl_frac < 0` is not "less reflection" -- it
switches the model to *reflection-only* output (the primary power law is
dropped), a qualitatively different spectral model. Worse, in the full grid
(below) the piled **Stage C** fit -- Afe frozen at 1, i.e. a *subset* of
Stage B's parameter space -- reaches a *lower* cstat than any Stage B fit.
That is impossible if the Stage B searches had found Stage B's minimum, so
from the canonical start all three optimizers stop in local minima.

That is why `run_multistart.py` exists: it restarts Stage B from a coarse,
truth-agnostic lattice of starting points (a in {0, 0.5, 0.9} x logxi in
{1, 2.5} x Afe in {1, 5}) plus seeds taken from the grid's own Stage C/D
solutions, each as `levmar` followed by a `neldermead` polish, each in its
own subprocess. The **flagship** Stage B fit of each case is then the
lowest-cstat *physical* (refl_frac > 0) solution among all grid and
multi-start fits (`target.flagship_records()`). The ground truth is never
used as a seed.""")

code(r"""with open(RESULTS2 / "multistart_stageB.json") as f:
    ms = json.load(f)

for case in SPECTRA:
    rows = []
    for k, r in enumerate(ms[case]):
        if r.get("statval") is None:
            rows.append([k, f"<b>{r.get('message')}</b>", "-", "-", "-"])
            continue
        d = {nm.split(".")[-1]: v for nm, v in zip(r["parnames"], r["parvals"])}
        seed = ("lattice" if k < 12 else "grid C/D seed")
        rows.append([k, seed, f"{r['statval']:.1f}", f"{d['a']:+.3f}",
                     f"{d['refl_frac']:+.2f}"])
    rows.sort(key=lambda row: float(row[2]) if row[2] not in ("-",) else 1e99)
    display(HTML(f"<h4>{case}: Stage B multi-start outcomes (sorted by cstat)</h4>"))
    display(HTML(html_table(["start", "seed type", "cstat", "a", "refl_frac"], rows)))

flag2 = flagship_records("B", RESULTS2)
for case, r in flag2.items():
    print(f"flagship {case:12s}: cstat={r['statval']:.1f}  from {r['source']}  "
          f"(canonical-start levmar: {canon[case][0]:.1f})")""")

md("## Diagnostic plots: the three flagship Stage B fits")

code(r"""def set_from_record(models, rec):
    byname = {p.fullname: p for m in models for p in m.pars}
    for nm, v in zip(rec["parnames"], rec["parvals"]):
        byname[nm].val = v

fig, axes = plt.subplots(2, 3, figsize=(16, 6), sharex="col",
                           gridspec_kw=dict(height_ratios=[3, 1], hspace=0.05))

m_u = build_unpiled_model(id_unpiled, STAGE)
set_from_record(m_u, flag2["unpiled"])
plot_fit(id_unpiled, f"1838 unpiled, Stage B (cstat={ui.calc_stat(id_unpiled):.1f})",
         axes[0, 0], axes[1, 0])

m_p = build_piled_model(id_piled, STAGE)
set_from_record(m_p, flag2["piled"])
plot_fit(id_piled, f"1838 piled, corrected (cstat={ui.calc_stat(id_piled):.1f})",
         axes[0, 1], axes[1, 1])

m_pn = build_piled_naive_model(id_piled, STAGE)
set_from_record(m_pn, flag2["piled_naive"])
plot_fit(id_piled, f"1838 piled, UNCORRECTED (cstat={ui.calc_stat(id_piled):.1f})",
         axes[0, 2], axes[1, 2])

fig.tight_layout()
plt.show()""")

md(r"""## Full Phase 4 grid for 1838 (loaded from disk)

Same 36 combinations as Part 1, same fixed starting point for every
combination (so these rows are directly comparable to Part 1's).""")

code(r"""with open(RESULTS2 / "fits_raw.json") as f:
    records2 = json.load(f)["records"]

for spectrum in SPECTRA:
    rows = []
    for stage in STAGES:
        for method in METHODS:
            r = next((r for r in records2 if r["spectrum"] == spectrum
                       and r["stage"] == stage and r["method"] == method), None)
            if r is None:
                continue
            if r.get("message") in ("CRASHED", "TIMEOUT", "PYTHON_EXCEPTION"):
                rows.append([stage, method, f"<b>{r['message']}</b>", "-", "-", "-", "-"])
                continue
            rows.append([stage, method, r.get("succeeded"), f"{r['statval']:.1f}",
                         f"{r['rstat']:.2f}", r.get("nfev"), f"{r['wall_time_s']:.1f}"])
    display(HTML(f"<h4>1838 {spectrum}</h4>"))
    display(HTML(html_table(
        ["stage", "method", "converged", "cstat", "reduced stat", "nfev", "time (s)"],
        rows)))""")

md(r"""## Ground truth, conf vs. covar, and the 081-vs-1838 comparison""")

code(r"""with open(RESULTS2 / "analysis_summary.json") as f:
    summary2 = json.load(f)
gtc2 = summary2["ground_truth_comparison"]

rows = []
for short, label in gt_labels.items():
    truth = GT2.get(gt_key_map.get(short, short))
    cells = []
    for spectrum in SPECTRA:
        c = gtc2[f"{spectrum}/B_flagship"]["comparison"].get(short)
        cells.append(f"{c['fitted']:.4g} ({c['rel_diff_pct']:+.1f}%)" if c else "-")
    rows.append([label, f"{truth:.4g}"] + cells)
display(HTML("<h4>1838 headline: Stage B flagship fits vs. ground truth</h4>"))
display(HTML(html_table(
    ["parameter", "truth", "unpiled", "piled (corrected)", "piled_naive (uncorrected)"],
    rows)))""")

code(r"""with open(RESULTS2 / "conf_flagship.json") as f:
    conf2 = json.load(f)

for spectrum in SPECTRA:
    flag = conf2[spectrum]
    rows = []
    for name, val, clo, chi, klo, khi in zip(
            flag["parnames"], flag["parvals"],
            flag["covar_parmins"], flag["covar_parmaxes"],
            flag["conf_parmins"], flag["conf_parmaxes"]):
        covar_s = "undefined" if clo is None or chi is None else f"[{clo:+.4g}, {chi:+.4g}]"
        klo_s = "(boundary)" if klo is None else f"{klo:+.4g}"
        khi_s = "(boundary)" if khi is None else f"{khi:+.4g}"
        conf_s = "undefined" if klo is None and khi is None else f"[{klo_s}, {khi_s}]"
        rows.append([name.split(".")[-1], f"{val:.4g}", covar_s, conf_s])
    display(HTML(f"<h4>1838 {spectrum}, Stage B: covar vs. conf "
                   f"(covar {flag['covar_time_s']:.1f}s, conf {flag['conf_time_s']:.1f}s)</h4>"))
    display(HTML(html_table(["parameter", "best fit", "covar 1-sigma", "conf 1-sigma"], rows)))""")

code(r"""# 081 vs 1838: Stage B bias relative to each simulation's own truth.
# 081 uses Part 1's grid-best Stage B fits; 1838 uses the multi-start
# flagship fits (see above for why).
rows = []
for short, label in gt_labels.items():
    row = [label]
    for spectrum in SPECTRA:
        c1 = summary["ground_truth_comparison"][f"{spectrum}/B"]["comparison"].get(short)
        c2 = gtc2[f"{spectrum}/B_flagship"]["comparison"].get(short)
        row.append(f"{c1['rel_diff_pct']:+.0f}%" if c1 else "-")
        row.append(f"{c2['rel_diff_pct']:+.0f}%" if c2 else "-")
    rows.append(row)
display(HTML("<h4>Stage B relative bias vs. truth: 081 (heavy pileup) vs 1838 (moderate)</h4>"))
display(HTML(html_table(
    ["parameter", "unpiled 081", "unpiled 1838", "piled 081", "piled 1838",
     "naive 081", "naive 1838"], rows)))""")

md(r"""## Part 2 summary: heavy (081) vs. moderate (1838) pileup

- **A fixed starting point is not enough at this count level.** From the
  canonical start, every piled Stage B search stopped in a local minimum,
  and the "best" of them was relxill's reflection-only (`refl_frac < 0`)
  branch. A coarse, truth-agnostic multi-start moved the physical optimum
  from cstat 970 (unphysical) to 702.6 for the piled case, and from 733.6
  to 702.0 even for the unpiled case. Seeds taken from the more
  constrained Stage C/D fits never beat the lattice.
- **At ~30% count loss, `jdpileup` works.** The corrected piled fit
  matches the unpiled fit in quality (cstat 702.6 vs 702.0, reduced 1.07
  for both) and in parameters (spin +18% vs +13% of truth, refl_frac +1%
  vs −4%, logxi/incl/gamma/nH within a few percent of each other). At
  081's ~93% loss, the corrected spin was still +76% off.
- **Uncorrected pileup is badly biased at both levels. At moderate pileup
  the fit statistic reveals it; at heavy pileup it doesn't.** For 1838 the naive fit is
  worse by Δcstat ≈ 340 on the same data, with structured residuals
  (2–2.3 keV edge, excess above ~7 keV), and its parameters are telltale:
  retrograde spin, logxi and Afe at their lower limits, refl_frac
  +130%. For 081, the naive fit was statistically as good as the
  corrected one.
- **conf vs. covar**: `covar` now returns bounds on the corrected piled
  fit (it failed for 081) but they are often several times *wider* than
  `conf`'s. The linear approximation is unreliable in both directions.
- **Shared, non-pileup offsets** (gamma ~−10%, Afe pinned at relxill's
  limit of 10 vs true 7.3) appear identically in the unpiled and corrected
  fits, so they reflect model degeneracies at this count level, not pileup.
- **Caveat**: 081 was not multi-started. Given how much that changed
  1838's answers, rerunning `run_multistart.py` for 081 is the next step
  before quoting the heavy-vs-moderate contrast quantitatively.

Full numbers: `../results/id1000001838/report.md`.""")

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python",
                    "name": "python3"},
    "language_info": {"name": "python", "version": "3.11"},
}

import pathlib
outpath = pathlib.Path(__file__).resolve().parent.parent / "notebook" / "relxill_pileup_fitting.ipynb"
outpath.parent.mkdir(exist_ok=True)
with open(outpath, "w") as f:
    nbf.write(nb, f)
print(f"wrote {outpath}")
