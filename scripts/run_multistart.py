"""
Multi-start check of the Stage B fit for every spectrum case.

Why: the Phase 4 grid starts every optimizer from one fixed, generic point
(build_models.RELXILL_START). For ID 1000001838 that was not enough on the
piled data: the jdpileup-corrected Stage C fit (Afe frozen) reached a lower
cstat than *any* Stage B fit, although Stage C's parameter space is a subset
of Stage B's -- proof that all three Stage B searches stopped in local
minima (one of them in relxill's reflection-only refl_frac<0 branch). This
script restarts Stage B from a grid of starting points, plus seeds taken
from the grid's own Stage C/D solutions (with Afe then freed), and records
every outcome.

Never seeded from the ground truth: the starting grid is a coarse,
truth-agnostic lattice, and the Stage C/D seeds come from fits that never
saw the truth (Stage D's fixed inclination aside -- noted in the report).

Writes <RESULTS_DIR>/multistart/<spectrum>_<k>.json per start and
<RESULTS_DIR>/multistart_stageB.json combined.
Run: TARGET_ID=... python run_multistart.py
"""
import itertools
import json
import subprocess
import sys
import time
from pathlib import Path

from target import RESULTS_DIR

SCRIPTS_DIR = Path(__file__).resolve().parent

SPECTRA = ["unpiled", "piled", "piled_naive"]
TIMEOUT_S = 600
MS_DIR = RESULTS_DIR / "multistart"
MS_DIR.mkdir(parents=True, exist_ok=True)

LATTICE = [dict(a=a, logxi=lx, Afe=afe, refl_frac=3.0)
           for a, lx, afe in itertools.product([0.0, 0.5, 0.9],
                                               [1.0, 2.5],
                                               [1.0, 5.0])]


def seeds_from_grid(spectrum):
    """Starting points taken from this spectrum's own Stage C/D grid fits
    (each method's end point), with Afe restarted at 3 since those stages
    had it frozen at 1."""
    with open(RESULTS_DIR / "fits_raw.json") as f:
        recs = json.load(f)["records"]
    out = []
    for r in recs:
        if (r["spectrum"] != spectrum or r["stage"] not in ("C", "D")
                or r.get("parvals") is None):
            continue
        start = {n.split(".")[-1]: v
                 for n, v in zip(r["parnames"], r["parvals"])}
        start["Afe"] = 3.0
        out.append(start)
    return out


def run_one(spectrum, k, start):
    outfile = MS_DIR / f"{spectrum}_{k:02d}.json"
    if outfile.exists():
        return json.load(open(outfile))
    cmd = [sys.executable, "multistart_worker.py", "--spectrum", spectrum,
           "--start", json.dumps(start), "--outfile", str(outfile)]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(SCRIPTS_DIR),
                              capture_output=True, text=True,
                              timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return dict(spectrum=spectrum, start=start, succeeded=False,
                    message="TIMEOUT", wall_time_s=time.time() - t0)
    if proc.returncode != 0 or not outfile.exists():
        return dict(spectrum=spectrum, start=start, succeeded=False,
                    message="CRASHED", returncode=proc.returncode,
                    wall_time_s=time.time() - t0)
    return json.load(open(outfile))


def main():
    out = {}
    for spectrum in SPECTRA:
        starts = LATTICE + seeds_from_grid(spectrum)
        recs = []
        for k, start in enumerate(starts):
            rec = run_one(spectrum, k, start)
            refl = None
            if rec.get("parvals"):
                d = {n.split(".")[-1]: v
                     for n, v in zip(rec["parnames"], rec["parvals"])}
                refl = d.get("refl_frac")
            print(f"{spectrum} start {k:2d}: cstat={rec.get('statval')} "
                  f"refl_frac={refl} [{rec.get('message')}]", flush=True)
            recs.append(rec)
        out[spectrum] = recs
        with open(RESULTS_DIR / "multistart_stageB.json", "w") as f:
            json.dump(out, f, indent=2)
    print(f"wrote {RESULTS_DIR / 'multistart_stageB.json'}")


if __name__ == "__main__":
    main()
