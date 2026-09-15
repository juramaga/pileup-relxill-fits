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


md(r"""# relxill fit of MARX-simulated Chandra spectrum ID 1000000081
### piled-up vs. unpiled, Sherpa (CIAO 4.17) + relxill, multiple optimizers

This notebook is a runnable walkthrough of the project documented in full
in `../CLAUDE.md` (methodology / decisions / Phases 1-5) and
`../results/report.md` (the complete fit-metrics report). It does not
repeat every decision made along the way -- see those two files for the
full reasoning, including why particular choices were made (statistic,
freezing stages, pileup parameters, etc).

**What this notebook does live**: loads the two spectra, builds the
`tbabs*relxill` (+ `jdpileup` for the piled case) models, fits the
literature-standard "Stage B" configuration for both spectra, and plots
the results.

**What it loads from disk instead of recomputing**: the full 24-combination
(2 spectra x 4 freezing stages x 3 optimizers) fit grid from Phase 4, and
the `conf`-vs-`covar` comparison from Phase 5 -- the former because several
of those combinations are slow (`moncar` in particular) and one
combination (piled, Stage A) crashes the Python process outright by
design of relxill's own error handling (see Phase 4 in `CLAUDE.md`), and
the latter because the piled spectrum's `conf` calculation alone takes
~40 minutes. Re-running `../scripts/run_fits.py` and
`../scripts/run_conf_flagship.py` reproduces those files if wanted.""")

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
    build_unpiled_model, build_piled_model, GROUND_TRUTH,
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

Both use **Stage B** here: the literature-standard freezing (`Rin=-1`
tied to the ISCO, `Rout=400`, single-power-law emissivity, `Ecut=300` keV
fixed -- a single CCD-resolution spectrum has essentially no leverage on
any of these). Free parameters: `nH, a, Incl, gamma, logxi, Afe,
refl_frac, norm` (+ pileup's `alpha, f` for the piled case). See
`CLAUDE.md` Phase 3 for the full Stage A-D ladder and the reasoning behind
each freeze -- this notebook only reproduces Stage B live; the other three
stages' results are loaded from disk further down.""")

code(r"""STAGE = "B"

abs_u, rel_u = build_unpiled_model(id_unpiled, STAGE)
print("--- unpiled full model ---")
print(ui.get_model(id_unpiled))""")

code(r"""abs_p, rel_p, pmod_p = build_piled_model(id_piled, STAGE)
print("--- piled full model ---")
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

md("## Diagnostic plots: data, model, and ratio")

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


fig, axes = plt.subplots(2, 2, figsize=(12, 6), sharex="col",
                           gridspec_kw=dict(height_ratios=[3, 1], hspace=0.05))
plot_fit(id_unpiled, f"unpiled, Stage B (cstat={fr_u.statval:.1f})",
         axes[0, 0], axes[1, 0])
plot_fit(id_piled, f"piled, Stage B (cstat={fr_p.statval:.1f})",
         axes[0, 1], axes[1, 1])
fig.tight_layout()
plt.show()""")

md(r"""## Full Phase 4 grid (loaded from disk)

All 24 (spectrum x stage x method) combinations -- see `../CLAUDE.md`
Phase 4 for why this is loaded rather than recomputed live (runtime, and
the piled/Stage A crash). Each combination in the original run was
executed as its own subprocess for exactly that crash-safety reason.""")

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

for spectrum in ("unpiled", "piled"):
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

md(r"""Note the three `CRASHED` rows for piled/Stage A: relxill's C++ code
calls a hard, uncatchable process abort on an unphysical `Rout<=Rin`
parameter excursion, which all three optimizers hit when given the full
15-parameter freedom of Stage A on the piled model. This is not
reproduced live in this notebook for the obvious reason that it would
take the kernel down with it -- see `CLAUDE.md` Phase 4 for the full
account, including why this is treated as a genuine finding (Stage A is
numerically intractable for the piled spectrum, not just poorly
constrained) rather than a bug to silently work around.""")

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

for spectrum in ("unpiled", "piled"):
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

for spectrum in ("unpiled", "piled"):
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

- Both spectra fit reasonably well visually (few-percent residuals across
  most of the 0.3-10 keV band) at Stage B, despite reduced stat > 1 in
  both cases -- with millions of counts, `cstat` has enough statistical
  power to detect small systematic mismatches that wouldn't show up in a
  lower-count spectrum.
- `conf` and `covar` genuinely disagree, and `covar` failed outright on
  the piled fit -- don't trust `covar` alone on a highly nonlinear,
  many-parameter model like this.
- The progressive freezing ladder (Stage A -> D) is not just a
  dimensionality-reduction convenience: Stage A is numerically
  intractable for the piled spectrum (hard crash, all three optimizers),
  and Stage C's "standard" solar-abundance assumption actively hurts the
  fit for this particular (super-solar Afe) simulated source.

Full discussion, all four stages, and the pileup-bias comparison:
`../results/report.md`. Full methodology and decision log: `../CLAUDE.md`.
Didactic write-up: `../writeup/`.""")

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
