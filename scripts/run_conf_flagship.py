"""
Phase 5 (part 2): for the flagship Stage B fit of each spectrum (the
literature-standard freezing stage; winning method taken from
results/analysis_summary.json's best_succeeded entry), refit and then run
Sherpa's `conf` (profile-likelihood confidence intervals) in addition to
the `covar` (covariance-matrix) errors already stored from Phase 4, so the
two can be compared directly -- see CLAUDE.md Phase 5.

`conf` is far more expensive than `covar` (it re-optimizes the remaining
free parameters at each trial value of each parameter being bounded), which
is why it's only run here for two fits rather than across the whole Phase 4
grid.

Run: python run_conf_flagship.py
"""
import json
import time
from pathlib import Path

from sherpa.astro import ui

from load_data import setup_data
from build_models import (
    build_unpiled_model, build_piled_model, build_piled_naive_model,
)

ROOT = Path(__file__).resolve().parent.parent
from target import (  # noqa: E402
    RESULTS_DIR as RESULTS, TARGET_ID, DEFAULT_ID, flagship_methods,
    flagship_records,
)

# From results/analysis_summary.json's best_per_group -> best_succeeded,
# for Stage B (see Phase 4/5 discussion): unpiled's and piled_naive's best
# formally-converged fit is neldermead... except unpiled's was run (and is
# kept, to avoid re-running piled's 2490s conf) as levmar, its own winner.
# Default ID: historical per-method choice, refit from the canonical start.
# Other IDs: start from the multi-start-checked physical Stage B flagship
# record (target.flagship_records) and re-polish with levmar from there.
if TARGET_ID == DEFAULT_ID:
    FLAGSHIP = flagship_methods()
    FLAGSHIP_RECORDS = {}
else:
    FLAGSHIP_RECORDS = flagship_records()
    FLAGSHIP = {s: "levmar" for s in FLAGSHIP_RECORDS}
STAGE = "B"


def run_flagship(spectrum, method, id_unpiled, id_piled):
    if spectrum == "unpiled":
        absmodel, relmodel = build_unpiled_model(id_unpiled, STAGE)
        pmod = None
        fit_id = id_unpiled
    elif spectrum == "piled":
        absmodel, relmodel, pmod = build_piled_model(id_piled, STAGE)
        fit_id = id_piled
    else:  # piled_naive
        absmodel, relmodel = build_piled_naive_model(id_piled, STAGE)
        pmod = None
        fit_id = id_piled

    rec = FLAGSHIP_RECORDS.get(spectrum)
    if rec is not None:
        byname = {p.fullname: p for m in (absmodel, relmodel, pmod) if m
                  for p in m.pars}
        for n, v in zip(rec["parnames"], rec["parvals"]):
            byname[n].val = v

    ui.set_method(method)
    allpars = list(absmodel.pars) + list(relmodel.pars) + \
        (list(pmod.pars) if pmod else [])
    nfree = sum(1 for p in allpars if not p.frozen)
    maxfev = {"levmar": max(1000, 200 * nfree),
              "neldermead": max(2000, 400 * nfree),
              "moncar": min(12000, max(3000, 700 * nfree))}[method]
    ui.set_method_opt("maxfev", maxfev)

    t0 = time.time()
    ui.fit(fit_id)
    fit_time = time.time() - t0
    fr = ui.get_fit_results()

    t0 = time.time()
    ui.covar(fit_id)
    covar_time = time.time() - t0
    cr = ui.get_covar_results()

    # Sherpa's conf() refuses to run when reduced stat > 3 by default (a
    # built-in sanity guard) -- covar() has no such guard, which is exactly
    # why the unpiled Stage B fit's covar computed fine in Phase 4
    # (rstat~3.13) while conf needs this override here. Raised deliberately,
    # not to paper over a bad fit: Phase 4/5 already establish *why* Stage
    # B doesn't reach rstat~1 (Afe/logxi/refl_frac degeneracies, a real
    # relxill/data tension, not a fitting bug) -- see CLAUDE.md.
    ui.set_conf_opt("max_rstat", 20)
    t0 = time.time()
    ui.conf(fit_id)
    conf_time = time.time() - t0
    kr = ui.get_conf_results()

    return dict(
        spectrum=spectrum, stage=STAGE, method=method,
        start_source=(rec or {}).get("source", "canonical start"),
        statval=fr.statval, dof=fr.dof, rstat=fr.statval / fr.dof,
        fit_time_s=fit_time,
        covar_time_s=covar_time, conf_time_s=conf_time,
        parnames=list(fr.parnames),
        parvals=[float(v) for v in fr.parvals],
        covar_parmins=[None if v is None else float(v) for v in cr.parmins],
        covar_parmaxes=[None if v is None else float(v) for v in cr.parmaxes],
        conf_parnames=list(kr.parnames),
        conf_parmins=[None if v is None else float(v) for v in kr.parmins],
        conf_parmaxes=[None if v is None else float(v) for v in kr.parmaxes],
    )


def main():
    outpath = RESULTS / "conf_flagship.json"
    out = {}
    if outpath.exists():
        with open(outpath) as f:
            out = json.load(f)

    missing = {s: m for s, m in FLAGSHIP.items() if s not in out}
    if not missing:
        print("nothing to do -- all flagship spectra already in "
              f"{outpath}")
        return

    id_unpiled, id_piled = setup_data()
    for spectrum, method in missing.items():
        print(f"running flagship conf for {spectrum} (Stage {STAGE}, "
              f"{method}) ...", flush=True)
        out[spectrum] = run_flagship(spectrum, method, id_unpiled, id_piled)
        print(f"  done: conf_time={out[spectrum]['conf_time_s']:.1f}s "
              f"covar_time={out[spectrum]['covar_time_s']:.1f}s", flush=True)

    with open(outpath, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {outpath}")


if __name__ == "__main__":
    main()
