"""
Which simulated spectrum the pipeline is working on, and where its outputs
go. Every other script imports TARGET_ID / RESULTS_DIR / GROUND_TRUTH from
here instead of hardcoding them.

Select the spectrum with the TARGET_ID environment variable (inherited by
the fit_worker.py subprocesses run_fits.py launches), e.g.

    TARGET_ID=1000001838 python run_fits.py

Default is 1000000081, the original (heavily piled-up) target, whose
outputs stay directly under results/ for backward compatibility; any other
ID writes under results/id<ID>/.
"""
import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_CSV = ROOT / "v0017_800ks_index.csv"

DEFAULT_ID = 1000000081
TARGET_ID = int(os.environ.get("TARGET_ID", DEFAULT_ID))

RESULTS_DIR = (ROOT / "results" if TARGET_ID == DEFAULT_ID
               else ROOT / "results" / f"id{TARGET_ID}")

# Ground truth for the default ID, kept inline so the original pipeline
# still runs without the (gitignored, large) index CSV present.
_GT_DEFAULT = dict(
    Afe=2.630883212688745,
    gamma=1.3305378369181775,
    incl=30.880998978376304,
    logxi=1.4965562318307917,
    nH=0.6496974978433812,
    norm=0.0972774295459766,
    refl_frac=14.314656850285886,
    spin=0.4929042376344323,
)


def load_ground_truth(target_id=TARGET_ID):
    """Simulation input parameters for `target_id`, from the index CSV."""
    if target_id == DEFAULT_ID and not INDEX_CSV.exists():
        return dict(_GT_DEFAULT)
    with open(INDEX_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if int(row["ID"]) == target_id:
                return {k[len("(Parameter) "):]: float(v)
                        for k, v in row.items()
                        if k.startswith("(Parameter) ")}
    raise ValueError(f"ID {target_id} not found in {INDEX_CSV}")


GROUND_TRUTH = load_ground_truth()


# Stage B flagship method per spectrum case. For the default ID these are
# the historical choices (see run_conf_flagship.py for why unpiled uses
# levmar); for any other ID, pick analysis_summary.json's best formally
# converged Stage B fit (falling back to best overall if none converged).
_FLAGSHIP_DEFAULT = {"unpiled": "levmar", "piled": "neldermead",
                      "piled_naive": "neldermead"}


def flagship_methods(stage="B"):
    if TARGET_ID == DEFAULT_ID:
        return dict(_FLAGSHIP_DEFAULT)
    import json
    with open(RESULTS_DIR / "analysis_summary.json") as f:
        best = json.load(f)["best_per_group"]
    out = {}
    for spectrum in ("unpiled", "piled", "piled_naive"):
        b = best.get(f"{spectrum}/{stage}")
        if b is None:
            continue
        out[spectrum] = (b["best_succeeded"] or b["best_overall"])["method"]
    return out


def _refl_frac(rec):
    for n, v in zip(rec.get("parnames") or [], rec.get("parvals") or []):
        if n.split(".")[-1] == "refl_frac":
            return v
    return None


def flagship_records(stage="B", results_dir=None):
    """Non-default IDs only: per spectrum case, the lowest-cstat *physical*
    (refl_frac > 0; negative refl_frac is relxill's reflection-only mode)
    Stage-B solution among the Phase 4 grid fits and the multi-start fits
    in multistart_stageB.json (see run_multistart.py). Each returned record
    carries a "source" field ("grid:<method>" or "multistart:<k>").
    """
    import json
    results_dir = Path(results_dir) if results_dir else RESULTS_DIR
    with open(results_dir / "fits_raw.json") as f:
        grid = json.load(f)["records"]
    ms_path = results_dir / "multistart_stageB.json"
    ms = json.load(open(ms_path)) if ms_path.exists() else {}
    out = {}
    for spectrum in ("unpiled", "piled", "piled_naive"):
        cands = []
        for r in grid:
            if r["spectrum"] == spectrum and r["stage"] == stage:
                cands.append(dict(r, source=f"grid:{r['method']}"))
        for k, r in enumerate(ms.get(spectrum, [])):
            cands.append(dict(r, source=f"multistart:{k}"))
        cands = [c for c in cands if c.get("statval") is not None
                 and (_refl_frac(c) or 0) > 0]
        if cands:
            out[spectrum] = min(cands, key=lambda c: c["statval"])
    return out
