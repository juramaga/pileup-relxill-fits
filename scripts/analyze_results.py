"""
Phase 5 (part 1): turn results/fits_raw.json into a flat metrics CSV plus a
JSON summary (best fit per spectrum/stage, cross-method agreement, and
ground-truth comparison). Does not do any fitting itself.

Run: python analyze_results.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from target import (  # noqa: E402
    RESULTS_DIR as RESULTS, TARGET_ID, DEFAULT_ID, flagship_records,
)
IS_DEFAULT = TARGET_ID == DEFAULT_ID
RAW = RESULTS / "fits_raw.json"

# nH's units in the index CSV are assumed to be the tbabs-standard
# 1e22 cm^-2 (see CLAUDE.md open question) -- same units abs_*.nH is in, so
# compared directly. `norm` is deliberately excluded from the ground-truth
# comparison: Phase 3 found a large (~50x), uniform-looking mismatch between
# our relxill/flux setup and whatever absolute convention the original
# simulation pipeline used for `norm`, so the raw CSV value and our fitted
# value are not on the same scale and a naive ratio would be misleading.
GT_KEYS = {"a": "spin", "Incl": "incl", "gamma": "gamma", "logxi": "logxi",
           "Afe": "Afe", "refl_frac": "refl_frac"}
GT_ABS_KEYS = {"nH": "nH"}


def short_name(parname):
    return parname.split(".")[-1]


def as_dict(record):
    """{short_param_name: (value, covar_lo, covar_hi)} for one fit record."""
    out = {}
    parnames = record.get("parnames") or []
    parvals = record.get("parvals") or []
    covar_names = record.get("covar_parnames") or []
    covar_lo = record.get("covar_parmins") or []
    covar_hi = record.get("covar_parmaxes") or []
    covar_map = {short_name(n): (lo, hi)
                 for n, lo, hi in zip(covar_names, covar_lo, covar_hi)}
    for n, v in zip(parnames, parvals):
        sn = short_name(n)
        lo, hi = covar_map.get(sn, (None, None))
        out[sn] = (v, lo, hi)
    return out


def write_csv(records, all_short_names):
    path = RESULTS / "fit_metrics.csv"
    fixed_cols = ["spectrum", "stage", "method", "succeeded", "message",
                  "statistic", "statval", "dof", "rstat", "nfev", "maxfev",
                  "wall_time_s"]
    par_cols = []
    for sn in all_short_names:
        par_cols += [sn, f"{sn}_covar_lo", f"{sn}_covar_hi"]

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fixed_cols + par_cols)
        for r in records:
            row = [
                r["spectrum"], r["stage"], r["method"], r.get("succeeded"),
                r.get("message"), r.get("statname"), r.get("statval"),
                r.get("dof"), r.get("rstat"), r.get("nfev"), r.get("maxfev"),
                r.get("wall_time_s"),
            ]
            pd = as_dict(r)
            for sn in all_short_names:
                v, lo, hi = pd.get(sn, (None, None, None))
                row += [v, lo, hi]
            w.writerow(row)
    print(f"wrote {path}")
    return path


def best_per_group(records):
    """Two notions of "best" per (spectrum, stage), because they can
    disagree and that disagreement is itself worth reporting (see e.g.
    piled/Stage C: the only formally-converged fit there, `levmar`, is
    dramatically *worse* than the unconverged `neldermead`/`moncar` runs --
    they just ran out of function-evaluation budget while still
    descending, they didn't get stuck):

    - best_succeeded: lowest statval among methods that formally converged
      (succeeded=True) -- the trustworthy choice for quoting errors, since
      Phase 4 found covar/conf are not reliable on a non-converged fit.
    - best_overall: lowest statval among *any* completed fit, regardless of
      the convergence flag -- the better answer in an absolute sense, but
      its parameter uncertainties should not be trusted at face value.
    """
    groups = {}
    for r in records:
        key = (r["spectrum"], r["stage"])
        groups.setdefault(key, []).append(r)

    best = {}
    for key, rs in groups.items():
        finite = [r for r in rs if r.get("statval") is not None]
        if not finite:
            best[key] = None
            continue
        succeeded = [r for r in finite if r.get("succeeded")]
        b_overall = min(finite, key=lambda r: r["statval"])
        b_succ = min(succeeded, key=lambda r: r["statval"]) if succeeded else None

        def entry(r):
            return dict(method=r["method"], statval=r["statval"],
                        rstat=r.get("rstat"), succeeded=r.get("succeeded"))

        disagree = (b_succ is not None and
                    b_succ["method"] != b_overall["method"] and
                    b_succ["statval"] > 1.5 * b_overall["statval"])

        best[key] = dict(
            method=(b_succ or b_overall)["method"],
            statval=(b_succ or b_overall)["statval"],
            rstat=(b_succ or b_overall).get("rstat"),
            succeeded=bool(b_succ is not None),
            any_succeeded=bool(succeeded),
            best_succeeded=entry(b_succ) if b_succ else None,
            best_overall=entry(b_overall),
            succeeded_is_meaningfully_worse=disagree,
        )
    return best


def method_agreement(records):
    """For each (spectrum, stage), compare succeeded fits' parameter
    vectors pairwise: max relative difference per shared parameter name,
    across all pairs of methods that succeeded in that group.
    """
    groups = {}
    for r in records:
        if not r.get("succeeded"):
            continue
        key = (r["spectrum"], r["stage"])
        groups.setdefault(key, []).append(r)

    out = {}
    for key, rs in groups.items():
        if len(rs) < 2:
            out["/".join(key)] = {"n_succeeded": len(rs), "max_rel_diff": {}}
            continue
        dicts = [as_dict(r) for r in rs]
        methods = [r["method"] for r in rs]
        # ordered by parameter order in the first fit, so reruns are
        # byte-stable (a bare set's iteration order is not)
        shared = [sn for sn in dicts[0] if all(sn in d for d in dicts[1:])]
        max_rel_diff = {}
        for sn in shared:
            vals = [d[sn][0] for d in dicts]
            lo, hi = min(vals), max(vals)
            denom = max(abs(lo), abs(hi), 1e-12)
            max_rel_diff[sn] = abs(hi - lo) / denom
        out["/".join(key)] = dict(n_succeeded=len(rs), methods=methods,
                                    max_rel_diff=max_rel_diff)
    return out


def ground_truth_comparison(records, ground_truth, best):
    out = {}
    for (spectrum, stage), b in best.items():
        if b is None:
            continue
        rec = next(r for r in records
                   if r["spectrum"] == spectrum and r["stage"] == stage
                   and r["method"] == b["method"])
        pd = as_dict(rec)
        comp = {}
        for short, gt_key in {**GT_KEYS, **GT_ABS_KEYS}.items():
            if short not in pd:
                continue
            val, lo, hi = pd[short]
            truth = ground_truth[gt_key]
            sigma = None
            if lo is not None and hi is not None:
                sigma_est = (hi - lo) / 2.0
                if sigma_est > 0:
                    sigma = (val - truth) / sigma_est
            comp[short] = dict(fitted=val, truth=truth,
                               rel_diff_pct=100.0 * (val - truth) /
                               truth if truth else None,
                               n_sigma=sigma)
        out["/".join((spectrum, stage))] = dict(method=b["method"],
                                                  comparison=comp)
    return out


def main():
    with open(RAW) as f:
        d = json.load(f)
    records = d["records"]
    ground_truth = d["ground_truth"]

    all_short_names = []
    for r in records:
        for n in (r.get("parnames") or []):
            sn = short_name(n)
            if sn not in all_short_names:
                all_short_names.append(sn)

    write_csv(records, all_short_names)

    best = best_per_group(records)
    agreement = method_agreement(records)
    gtc = ground_truth_comparison(records, ground_truth, best)

    # Non-default IDs: also compare the multi-start-checked, physical
    # (refl_frac > 0) Stage B flagship of each case against truth -- see
    # run_multistart.py / target.flagship_records() for why the fixed-start
    # grid's own "best" can't be trusted as the Stage B answer there.
    if not IS_DEFAULT:
        for spectrum, rec in flagship_records().items():
            key = (spectrum, "B_flagship")
            pseudo = {key: dict(method=rec["method"])}
            comp = ground_truth_comparison(
                [dict(rec, stage="B_flagship")], ground_truth, pseudo)
            entry = comp["/".join(key)]
            entry.update(source=rec["source"], statval=rec["statval"],
                         rstat=rec.get("rstat"))
            gtc["/".join(key)] = entry

    summary = dict(
        best_per_group={"/".join(k): v for k, v in best.items()},
        method_agreement=agreement,
        ground_truth_comparison=gtc,
        n_crashed=sum(1 for r in records
                       if r.get("message") in ("CRASHED", "TIMEOUT")),
    )
    outpath = RESULTS / "analysis_summary.json"
    with open(outpath, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"wrote {outpath}")


if __name__ == "__main__":
    main()
