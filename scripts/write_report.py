"""
Phase 5 (part 4): assemble results/report.md from fits_raw.json,
analysis_summary.json, and conf_flagship.json. Pure formatting -- no
fitting, no new computation. Run after analyze_results.py,
run_conf_flagship.py, and make_plots.py.

Run: python write_report.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

STAGES = ["A", "B", "C", "D"]
METHODS = ["levmar", "neldermead", "moncar"]
STAGE_DESC = {
    "A": "all thawed (except z=0)",
    "B": "standard freeze (Rin=-1 ISCO, Rout=400, single emissivity, "
         "Ecut=300)",
    "C": "Stage B + Afe=1 (solar)",
    "D": "Stage C + Incl fixed at ground truth (~30.9 deg)",
}
GT_LABELS = {"a": "spin (a)", "Incl": "Incl (deg)", "gamma": "gamma",
             "logxi": "logxi", "Afe": "Afe", "refl_frac": "refl_frac",
             "nH": "nH (1e22 cm^-2)"}


def load_json(name):
    with open(RESULTS / name) as f:
        return json.load(f)


def fmt(x, nd=3):
    if x is None:
        return "--"
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, (int,)):
        return str(x)
    try:
        return f"{x:.{nd}f}"
    except (ValueError, TypeError):
        return str(x)


def stage_method_table(records, spectrum):
    rows = []
    rows.append("| Stage | Method | Converged | cstat | dof | reduced stat | "
                 "nfev | wall time (s) |")
    rows.append("|---|---|---|---|---|---|---|---|")
    for stage in STAGES:
        for method in METHODS:
            r = next((r for r in records if r["spectrum"] == spectrum and
                       r["stage"] == stage and r["method"] == method), None)
            if r is None:
                continue
            if r.get("message") in ("CRASHED", "TIMEOUT", "PYTHON_EXCEPTION"):
                rows.append(f"| {stage} | {method} | **{r['message']}** | "
                             f"-- | -- | -- | -- | {fmt(r.get('wall_time_s'), 1)} |")
                continue
            rows.append(
                f"| {stage} | {method} | {r.get('succeeded')} | "
                f"{fmt(r.get('statval'), 1)} | {r.get('dof')} | "
                f"{fmt(r.get('rstat'), 2)} | {r.get('nfev')} | "
                f"{fmt(r.get('wall_time_s'), 1)} |"
            )
    return "\n".join(rows)


def gt_table(gtc, key):
    entry = gtc.get(key)
    if entry is None:
        return "(no data)"
    rows = ["| Parameter | Fitted | Ground truth | Relative diff | "
            "n_sigma (covar) |", "|---|---|---|---|---|"]
    for short, label in GT_LABELS.items():
        c = entry["comparison"].get(short)
        if c is None:
            rows.append(f"| {label} | (frozen / n/a) | -- | -- | -- |")
            continue
        rows.append(
            f"| {label} | {fmt(c['fitted'])} | {fmt(c['truth'])} | "
            f"{fmt(c['rel_diff_pct'], 1)}% | {fmt(c['n_sigma'], 1)} |"
        )
    return "\n".join(rows)


def agreement_table(agreement, key):
    entry = agreement.get(key)
    if entry is None or not entry.get("max_rel_diff"):
        return f"(fewer than 2 converged methods for {key}; no comparison)"
    methods = entry.get("methods", [])
    rows = [f"Converged methods compared: {', '.join(methods)}", "",
            "| Parameter | Max relative spread across methods |",
            "|---|---|"]
    for pname, diff in sorted(entry["max_rel_diff"].items(),
                                key=lambda kv: -kv[1]):
        rows.append(f"| {pname} | {diff * 100:.1f}% |")
    return "\n".join(rows)


def conf_vs_covar_table(flag):
    rows = ["| Parameter | Best fit | covar 1-sigma | conf 1-sigma |",
            "|---|---|---|---|"]
    for name, val, clo, chi, klo, khi in zip(
            flag["parnames"], flag["parvals"],
            flag["covar_parmins"], flag["covar_parmaxes"],
            flag["conf_parmins"], flag["conf_parmaxes"]):
        short = name.split(".")[-1]
        covar_str = ("undefined" if clo is None or chi is None
                      else f"[{clo:+.4g}, {chi:+.4g}]")
        klo_s = "(boundary)" if klo is None else f"{klo:+.4g}"
        khi_s = "(boundary)" if khi is None else f"{khi:+.4g}"
        conf_str = "undefined" if klo is None and khi is None else f"[{klo_s}, {khi_s}]"
        rows.append(f"| {short} | {val:.4g} | {covar_str} | {conf_str} |")
    return "\n".join(rows)


def main():
    raw = load_json("fits_raw.json")
    records = raw["records"]
    ground_truth = raw["ground_truth"]
    summary = load_json("analysis_summary.json")
    conf_flag = load_json("conf_flagship.json")

    best = summary["best_per_group"]
    agreement = summary["method_agreement"]
    gtc = summary["ground_truth_comparison"]

    lines = []
    lines.append("# Fit metrics report -- relxill fit of spectrum ID 1000000081")
    lines.append("")
    lines.append("Generated from `results/fits_raw.json`, "
                  "`results/analysis_summary.json`, and "
                  "`results/conf_flagship.json` by "
                  "`scripts/write_report.py`. See `CLAUDE.md` for the full "
                  "methodology (Phases 1-5); this document reports results "
                  "only.")
    lines.append("")
    lines.append("**Ground truth for this simulation** (from "
                  "`v0017_800ks_index.csv`): "
                  f"spin={ground_truth['spin']:.4f}, "
                  f"incl={ground_truth['incl']:.2f} deg, "
                  f"gamma={ground_truth['gamma']:.4f}, "
                  f"logxi={ground_truth['logxi']:.4f}, "
                  f"Afe={ground_truth['Afe']:.4f}, "
                  f"refl_frac={ground_truth['refl_frac']:.4f}, "
                  f"nH={ground_truth['nH']:.4f}. `norm` (={ground_truth['norm']:.5f}) "
                  "is intentionally excluded from all comparisons below -- "
                  "Phase 3 found a large (~50x), uniform flux-normalization "
                  "mismatch between our relxill/response setup and whatever "
                  "convention the original simulation used, so raw `norm` "
                  "values are not on a comparable scale.")
    lines.append("")

    lines.append("## Stage definitions")
    lines.append("")
    for s in STAGES:
        lines.append(f"- **Stage {s}**: {STAGE_DESC[s]}")
    lines.append("")

    for spectrum, title in [("unpiled", "## Unpiled spectrum"),
                              ("piled", "## Piled (pileup-affected) spectrum")]:
        lines.append(title)
        lines.append("")
        lines.append(stage_method_table(records, spectrum))
        lines.append("")
        if spectrum == "piled":
            lines.append("Stage A crashed for all three optimizers (relxill's "
                          "C++ code hard-aborts on an unphysical Rout<=Rin "
                          "excursion, reachable even after the Stage A bound "
                          "tightening once pileup's extra free parameters are "
                          "added -- see CLAUDE.md Phase 4). No Stage A result "
                          "exists for the piled spectrum.")
            lines.append("")

        lines.append(f"### {spectrum}: recovered parameters vs. ground truth, "
                      "by stage")
        lines.append("")
        lines.append("Each table uses that stage's best formally-converged "
                      "fit (see method column); covar 1-sigma errors turn "
                      "into `n_sigma` below (not a systematic-bias measure -- "
                      "see the conf-vs-covar section for why these can be "
                      "misleadingly tight).")
        lines.append("")
        for stage in STAGES:
            key = f"{spectrum}/{stage}"
            b = best.get(key)
            if b is None:
                lines.append(f"**Stage {stage}**: no fit available (crashed).")
                lines.append("")
                continue
            lines.append(f"**Stage {stage}** (method: {b['method']}, "
                          f"cstat={fmt(b['statval'],1)}, "
                          f"rstat={fmt(b['rstat'],2)}"
                          + (", *note: the only converged method here is "
                             "markedly worse than an unconverged one -- see "
                             "grid table above*"
                             if b.get("succeeded_is_meaningfully_worse")
                             else "") + "):")
            lines.append("")
            lines.append(gt_table(gtc, key))
            lines.append("")

        lines.append(f"### {spectrum}: cross-method agreement, by stage")
        lines.append("")
        lines.append("Where 2+ methods formally converged in the same "
                      "(spectrum, stage) group, the spread between their "
                      "recovered parameter values (as a fraction of the "
                      "largest value) -- a large spread means the methods "
                      "landed in *different* minima, not just different "
                      "precision on the same one.")
        lines.append("")
        for stage in STAGES:
            key = f"{spectrum}/{stage}"
            lines.append(f"**Stage {stage}**:")
            lines.append("")
            lines.append(agreement_table(agreement, key))
            lines.append("")

    lines.append("## conf vs. covar: flagship comparison (Stage B)")
    lines.append("")
    lines.append("Sherpa's `covar` (covariance/Hessian-based, fast) vs. "
                  "`conf` (profile-likelihood, expensive -- re-optimizes "
                  "remaining free parameters at each trial value) 1-sigma "
                  "intervals, for the best-converged Stage B fit of each "
                  "spectrum.")
    lines.append("")
    for spectrum in ("unpiled", "piled"):
        flag = conf_flag[spectrum]
        lines.append(f"### {spectrum} (method: {flag['method']}, "
                      f"cstat={flag['statval']:.1f}, "
                      f"rstat={flag['rstat']:.2f})")
        lines.append("")
        lines.append(f"`covar` wall time: {flag['covar_time_s']:.1f}s -- "
                      f"`conf` wall time: {flag['conf_time_s']:.1f}s "
                      f"({flag['conf_time_s']/max(flag['covar_time_s'],0.01):.0f}x slower)")
        lines.append("")
        lines.append(conf_vs_covar_table(flag))
        lines.append("")
    lines.append("**Takeaways**: for the unpiled fit, `conf`'s intervals are "
                  "noticeably larger (and asymmetric) than `covar`'s -- e.g. "
                  "spin: covar +/-0.00008 vs. conf [-0.0055,+0.0106], "
                  "refl_frac: covar +/-0.20 vs. conf [-0.69,+0.19] -- "
                  "`covar`'s linearized/Gaussian approximation is "
                  "substantially overconfident here. For the piled fit, "
                  "`covar` failed outright (every bound came back undefined "
                  "-- the Hessian was singular/hit a parameter boundary "
                  "during its numerical differencing), while `conf` still "
                  "produced usable (if boundary-limited on `alpha`, `gamma`, "
                  "`logxi`) intervals, at a real cost: ~2490s vs. 3s. "
                  "Concretely: `covar` is cheap and fine as a rough guide on "
                  "a well-converged fit, but should not be trusted as the "
                  "final word on parameter uncertainty for a model this "
                  "nonlinear, and can fail silently-ish (all-`None` bounds) "
                  "exactly when the fit is least well-behaved -- which is "
                  "when you'd want it most.")
    lines.append("")

    lines.append("## Pileup bias: unpiled vs. piled, Stage B")
    lines.append("")
    u = gtc.get("unpiled/B", {}).get("comparison", {})
    p = gtc.get("piled/B", {}).get("comparison", {})
    lines.append("| Parameter | Ground truth | Unpiled fit | Unpiled diff | "
                  "Piled fit | Piled diff |")
    lines.append("|---|---|---|---|---|---|")
    for short, label in GT_LABELS.items():
        cu, cp = u.get(short), p.get(short)
        truth = ground_truth.get({"a": "spin", "Incl": "incl"}.get(short, short))
        fu = fmt(cu["fitted"]) if cu else "--"
        du = f"{fmt(cu['rel_diff_pct'],1)}%" if cu else "--"
        fp = fmt(cp["fitted"]) if cp else "--"
        dp = f"{fmt(cp['rel_diff_pct'],1)}%" if cp else "--"
        lines.append(f"| {label} | {fmt(truth)} | {fu} | {du} | {fp} | {dp} |")
    lines.append("")
    lines.append("See the exact percentages in the table above rather than "
                  "this paragraph for specific numbers. Qualitatively: both "
                  "fits substantially overestimate `refl_frac` relative to "
                  "truth in the same direction -- likely entangled with the "
                  "known `norm` convention mismatch (Phase 3) rather than a "
                  "pileup-specific effect, since it happens on the unpiled "
                  "side too. Where the piled and unpiled deviations differ "
                  "in sign or magnitude for a given parameter (check `Afe` "
                  "and `logxi` above), that is more plausibly a genuine "
                  "pileup effect: pileup distorts the spectral shape "
                  "(hardening it, since low-pulse-height piled events get "
                  "reassigned to higher apparent energies) in a way the "
                  "`jdpileup` model only partially undoes, and that residual "
                  "distortion feeds into the line/ionization parameters.")
    lines.append("")

    lines.append("## Diagnostic plots (Stage B best fit)")
    lines.append("")
    lines.append("![unpiled Stage B fit](plots/unpiled_stageB_fit.png)")
    lines.append("")
    lines.append("![piled Stage B fit](plots/piled_stageB_fit.png)")
    lines.append("")

    lines.append("## Caveats carried through from earlier phases")
    lines.append("")
    lines.append("- `norm` is not directly comparable to the ground-truth CSV "
                  "value (see above) -- a ~50x uniform flux-scale mismatch "
                  "found in Phase 3, cause not fully diagnosed.")
    lines.append("- Pileup's `ftime`/`fracexp`/`g0`/`n`/`nterms` were left at "
                  "Sherpa's instrumental defaults (no real event-file header "
                  "available for this simulation) -- only `alpha` and `f` "
                  "were fit.")
    lines.append("- `nH` units assumed to be the tbabs-standard 1e22 cm^-2 "
                  "(not explicitly stated in the index CSV) -- still an open "
                  "question for the user.")
    lines.append("- Stage A's `Rin`/`Rout` bounds were tightened from "
                  "relxill's native range for numerical-stability reasons "
                  "(see Phase 3/4) -- Stage A results should be read as "
                  "\"free within a still-very-wide but slightly conservative "
                  "range\", not \"free over relxill's full native range\".")
    lines.append("")

    outpath = RESULTS / "report.md"
    with open(outpath, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {outpath}")


if __name__ == "__main__":
    main()
