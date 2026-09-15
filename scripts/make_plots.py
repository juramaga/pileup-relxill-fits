"""
Phase 5 (part 3): data/model/ratio plots for the flagship Stage B fit of
each spectrum (same fit selected in run_conf_flagship.py). Sets model
parameters directly from the stored Phase 4 best-fit values (no need to
refit) and plots with matplotlib (Agg backend -- no display needed).

Run: python make_plots.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sherpa.astro import ui

from load_data import setup_data
from build_models import build_unpiled_model, build_piled_model

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
PLOTS_DIR = RESULTS / "plots"
PLOTS_DIR.mkdir(exist_ok=True)

STAGE = "B"
FLAGSHIP = {"unpiled": "levmar", "piled": "neldermead"}  # see analysis_summary.json


def set_params_from_record(models, record):
    parname_to_model = {}
    for m in models:
        for p in m.pars:
            parname_to_model[p.fullname] = p
    for name, val in zip(record["parnames"], record["parvals"]):
        parname_to_model[name].val = val


def load_record(spectrum, stage, method):
    with open(RESULTS / "fits_raw.json") as f:
        d = json.load(f)
    for r in d["records"]:
        if (r["spectrum"], r["stage"], r["method"]) == (spectrum, stage, method):
            return r
    raise KeyError((spectrum, stage, method))


def plot_one(spectrum, fit_id, models, record):
    set_params_from_record(models, record)

    dplot = ui.get_data_plot(fit_id)
    mplot = ui.get_model_plot(fit_id)
    rplot = ui.get_ratio_plot(fit_id)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, sharex=True, figsize=(7, 6),
        gridspec_kw=dict(height_ratios=[3, 1], hspace=0.05),
    )

    ax1.errorbar(dplot.x, dplot.y, yerr=dplot.yerr, fmt=".", ms=2,
                 color="black", ecolor="0.7", elinewidth=0.5, label="data")
    ax1.plot(mplot.x, mplot.y, color="crimson", lw=1.2,
             label=f"model ({FLAGSHIP[spectrum]}, Stage {STAGE})")
    ax1.set_yscale("log")
    ax1.set_xscale("log")
    ax1.set_ylabel("counts / s / keV")
    ax1.set_title(f"{spectrum} spectrum (ID 1000000081) -- Stage {STAGE}, "
                   f"{FLAGSHIP[spectrum]}, cstat={record['statval']:.1f}, "
                   f"rstat={record['rstat']:.2f}")
    ax1.legend(fontsize=8, loc="lower left")

    ax2.axhline(1.0, color="0.5", lw=0.8)
    ax2.errorbar(rplot.x, rplot.y, yerr=rplot.yerr, fmt=".", ms=2,
                 color="black", ecolor="0.7", elinewidth=0.5)
    ax2.set_xscale("log")
    ax2.set_ylabel("data / model")
    ax2.set_xlabel("Energy (keV)")

    outpath = PLOTS_DIR / f"{spectrum}_stage{STAGE}_fit.png"
    fig.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {outpath}")


def main():
    id_unpiled, id_piled = setup_data()

    abs_u, rel_u = build_unpiled_model(id_unpiled, STAGE)
    rec_u = load_record("unpiled", STAGE, FLAGSHIP["unpiled"])
    plot_one("unpiled", id_unpiled, [abs_u, rel_u], rec_u)

    abs_p, rel_p, pmod_p = build_piled_model(id_piled, STAGE)
    rec_p = load_record("piled", STAGE, FLAGSHIP["piled"])
    plot_one("piled", id_piled, [abs_p, rel_p, pmod_p], rec_p)


if __name__ == "__main__":
    main()
