"""
Runs exactly one (spectrum, stage, method) fit and writes its JSON result to
--outfile. Meant to be invoked as a subprocess by run_fits.py, never
imported: relxill's C++ code calls a hard, uncatchable abort() (not a
Python exception) for certain invalid parameter combinations (confirmed:
Rin>=Rout, reachable even after tightening Stage A's soft bounds -- see
build_models.py and CLAUDE.md Phase 4). No amount of try/except in Python
can survive that; running each fit in its own subprocess is what actually
makes the batch robust to it -- a crashed worker just means one missing
result, not a dead run.
"""
import argparse
import json
import sys
import time
import traceback

from sherpa.astro import ui

from load_data import setup_data
from build_models import (
    build_unpiled_model, build_piled_model, build_piled_naive_model,
)


def count_thawed(*models):
    return sum(sum(1 for p in m.pars if not p.frozen) for m in models)


def maxfev_for(method, nfree):
    if method == "levmar":
        return max(1000, 200 * nfree)
    if method == "neldermead":
        return max(2000, 400 * nfree)
    if method == "moncar":
        return min(12000, max(3000, 700 * nfree))
    raise ValueError(method)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spectrum", required=True,
                     choices=["unpiled", "piled", "piled_naive"])
    ap.add_argument("--stage", required=True, choices=["A", "B", "C", "D"])
    ap.add_argument("--method", required=True,
                     choices=["levmar", "neldermead", "moncar"])
    ap.add_argument("--outfile", required=True)
    args = ap.parse_args()

    id_unpiled, id_piled = setup_data()

    if args.spectrum == "unpiled":
        absmodel, relmodel = build_unpiled_model(id_unpiled, args.stage)
        pmod = None
        fit_id = id_unpiled
    elif args.spectrum == "piled":
        absmodel, relmodel, pmod = build_piled_model(id_piled, args.stage)
        fit_id = id_piled
    else:  # piled_naive: piled *data*, plain (no jdpileup) model
        absmodel, relmodel = build_piled_naive_model(id_piled, args.stage)
        pmod = None
        fit_id = id_piled

    models = [absmodel, relmodel] + ([pmod] if pmod is not None else [])
    nfree = count_thawed(*models)
    maxfev = maxfev_for(args.method, nfree)

    ui.set_method(args.method)
    ui.set_method_opt("maxfev", maxfev)

    record = dict(spectrum=args.spectrum, stage=args.stage,
                  method=args.method, nfree=nfree, maxfev=maxfev)

    t0 = time.time()
    try:
        ui.fit(fit_id)
        r = ui.get_fit_results()
        record.update(
            succeeded=bool(r.succeeded),
            message=r.message,
            statval=r.statval,
            statname=r.statname,
            numpoints=r.numpoints,
            dof=r.dof,
            rstat=(r.statval / r.dof if r.dof else None),
            nfev=r.nfev,
            parnames=list(r.parnames),
            parvals=[float(v) for v in r.parvals],
        )
        try:
            ui.covar(fit_id)
            cr = ui.get_covar_results()
            record["covar_parnames"] = list(cr.parnames)
            record["covar_parmins"] = [
                None if v is None else float(v) for v in cr.parmins
            ]
            record["covar_parmaxes"] = [
                None if v is None else float(v) for v in cr.parmaxes
            ]
        except Exception:
            record["covar_error"] = traceback.format_exc()
    except Exception:
        record.update(succeeded=False, message="PYTHON_EXCEPTION",
                       error=traceback.format_exc())
    record["wall_time_s"] = time.time() - t0

    with open(args.outfile, "w") as f:
        json.dump(record, f, indent=2)


if __name__ == "__main__":
    main()
