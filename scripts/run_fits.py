"""
Phase 4: fit both spectra, at every Stage A-D, with every optimizer.

Each (spectrum, stage, method) combination is run as its own subprocess
(fit_worker.py) rather than in-process: relxill's C++ code can call a hard,
uncatchable process abort() for certain invalid parameter excursions
(confirmed to happen even after tightening Stage A's bounds -- see
build_models.py / CLAUDE.md Phase 4), which no Python try/except can
survive. Subprocess isolation means a crashed combination is recorded as
CRASHED and the batch continues, instead of losing everything after it.

Combines all per-combination JSON files into results/fits_raw.json.
Run: python run_fits.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from build_models import STAGES, GROUND_TRUTH

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)
PER_FIT_DIR = RESULTS_DIR / "per_fit"
PER_FIT_DIR.mkdir(exist_ok=True)
OUTFILE = RESULTS_DIR / "fits_raw.json"

METHODS = ["levmar", "neldermead", "moncar"]
SPECTRA = ["unpiled", "piled"]
TIMEOUT_S = 600


def run_one(spectrum, stage, method):
    outfile = PER_FIT_DIR / f"{spectrum}_{stage}_{method}.json"
    cmd = [sys.executable, "fit_worker.py",
           "--spectrum", spectrum, "--stage", stage, "--method", method,
           "--outfile", str(outfile)]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT / "scripts"),
                               capture_output=True, text=True,
                               timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return dict(spectrum=spectrum, stage=stage, method=method,
                    succeeded=False, message="TIMEOUT",
                    wall_time_s=time.time() - t0)

    if proc.returncode != 0 or not outfile.exists():
        stderr_tail = "\n".join(proc.stderr.splitlines()[-30:])
        return dict(spectrum=spectrum, stage=stage, method=method,
                    succeeded=False, message="CRASHED",
                    returncode=proc.returncode,
                    stderr_tail=stderr_tail,
                    wall_time_s=time.time() - t0)

    with open(outfile) as f:
        record = json.load(f)
    return record


def main():
    records = []
    combos = [(s, g, m) for s in SPECTRA for g in STAGES for m in METHODS]
    for i, (spectrum, stage, method) in enumerate(combos, 1):
        print(f"[{i}/{len(combos)}] {spectrum} / stage {stage} / {method} ...",
              flush=True)
        rec = run_one(spectrum, stage, method)
        print(f"   -> succeeded={rec.get('succeeded')} "
              f"statval={rec.get('statval')} rstat={rec.get('rstat')} "
              f"nfev={rec.get('nfev')} time={rec.get('wall_time_s'):.1f}s "
              f"{'[' + rec['message'] + ']' if rec.get('message') in ('CRASHED', 'TIMEOUT', 'PYTHON_EXCEPTION') else ''}",
              flush=True)
        records.append(rec)

        with open(OUTFILE, "w") as f:
            json.dump(dict(ground_truth=GROUND_TRUTH, records=records), f,
                       indent=2)

    n_bad = sum(1 for r in records if r.get("message") in
                ("CRASHED", "TIMEOUT", "PYTHON_EXCEPTION"))
    print(f"\nWrote {len(records)} fit records to {OUTFILE} "
          f"({n_bad} crashed/timed out)")


if __name__ == "__main__":
    main()
