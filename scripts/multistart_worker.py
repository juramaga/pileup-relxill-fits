"""
Runs one Stage-B fit from an explicit starting point and writes its JSON
result. Invoked as a subprocess by run_multistart.py, never imported (same
crash-isolation reason as fit_worker.py: relxill can hard-abort the process).

The fit is levmar from the given start, then a neldermead polish from
wherever levmar stopped -- a cheap way to give every start both a gradient
descent and a derivative-free escape from shallow stalls.

--start is a JSON object {short_param_name: value}; any thawed parameter
not listed keeps build_models.py's canonical start value.
"""
import argparse
import json
import time
import traceback

from sherpa.astro import ui

from load_data import setup_data
from build_models import (
    build_unpiled_model, build_piled_model, build_piled_naive_model,
)

STAGE = "B"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spectrum", required=True,
                     choices=["unpiled", "piled", "piled_naive"])
    ap.add_argument("--start", required=True)
    ap.add_argument("--outfile", required=True)
    args = ap.parse_args()
    start = json.loads(args.start)

    id_unpiled, id_piled = setup_data()
    if args.spectrum == "unpiled":
        models = list(build_unpiled_model(id_unpiled, STAGE))
        fit_id = id_unpiled
    elif args.spectrum == "piled":
        models = list(build_piled_model(id_piled, STAGE))
        fit_id = id_piled
    else:
        models = list(build_piled_naive_model(id_piled, STAGE))
        fit_id = id_piled

    for m in models:
        for p in m.pars:
            if not p.frozen and p.name in start:
                p.val = start[p.name]

    nfree = sum(1 for m in models for p in m.pars if not p.frozen)
    record = dict(spectrum=args.spectrum, stage=STAGE, start=start,
                  nfree=nfree)
    t0 = time.time()
    try:
        ui.set_method("levmar")
        ui.set_method_opt("maxfev", max(1000, 200 * nfree))
        ui.fit(fit_id)
        r1 = ui.get_fit_results()
        record["levmar_statval"] = r1.statval

        ui.set_method("neldermead")
        ui.set_method_opt("maxfev", max(2000, 400 * nfree))
        ui.fit(fit_id)
        r = ui.get_fit_results()
        record.update(
            method="levmar+neldermead",
            succeeded=bool(r.succeeded), message=r.message,
            statval=r.statval, dof=r.dof,
            rstat=(r.statval / r.dof if r.dof else None),
            nfev=r1.nfev + r.nfev,
            parnames=list(r.parnames),
            parvals=[float(v) for v in r.parvals],
        )
    except Exception:
        record.update(succeeded=False, message="PYTHON_EXCEPTION",
                       error=traceback.format_exc())
    record["wall_time_s"] = time.time() - t0
    with open(args.outfile, "w") as f:
        json.dump(record, f, indent=2)


if __name__ == "__main__":
    main()
