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
SPECTRA = ["unpiled", "piled", "piled_naive"]
SPECTRUM_TITLES = {
    "unpiled": "## Unpiled spectrum",
    "piled": "## Piled spectrum (jdpileup-corrected)",
    "piled_naive": "## Piled spectrum, fit WITHOUT correcting for pileup "
                   "(\"piled_naive\")",
}
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


def three_way_table(gtc, ground_truth):
    gt_key_map = {"a": "spin", "Incl": "incl"}
    rows = ["| Parameter | Ground truth | unpiled | piled (corrected) | "
            "piled_naive (uncorrected) |",
            "|---|---|---|---|---|"]
    entries = {s: gtc.get(f"{s}/B", {}).get("comparison", {}) for s in SPECTRA}
    for short, label in GT_LABELS.items():
        truth = ground_truth.get(gt_key_map.get(short, short))
        cells = []
        for s in SPECTRA:
            c = entries[s].get(short)
            cells.append(f"{fmt(c['fitted'])} ({fmt(c['rel_diff_pct'],1)}%)"
                         if c else "--")
        rows.append(f"| {label} | {fmt(truth)} | {cells[0]} | {cells[1]} | "
                     f"{cells[2]} |")
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

    lines.append("## Three spectrum/model cases compared")
    lines.append("")
    lines.append("- **unpiled**: the pileup-free spectrum, fit with "
                  "`tbabs*relxill`.")
    lines.append("- **piled**: the pileup-affected spectrum, fit with "
                  "`tbabs*relxill` wrapped in Sherpa's `jdpileup` model -- "
                  "the physically correct treatment.")
    lines.append("- **piled_naive**: the *same* pileup-affected spectrum, "
                  "fit with plain `tbabs*relxill` and **no** pileup "
                  "correction at all -- the mistake an analyst makes by "
                  "not realizing/correcting for pileup. Added specifically "
                  "to quantify how much parameter bias pileup causes "
                  "*with* vs. *without* correcting for it (see the "
                  "three-way comparison immediately below).")
    lines.append("")

    lines.append("## Headline result: Stage B, all three cases vs. ground truth")
    lines.append("")
    lines.append("This is the comparison of primary interest -- the "
                  "literature-standard freezing stage, for all three "
                  "spectrum/model cases, each using its own best "
                  "formally-converged method.")
    lines.append("")
    lines.append(three_way_table(gtc, ground_truth))
    lines.append("")
    lines.append("**Read this as**: `unpiled` is the baseline (pileup-free, "
                  "closest to a \"clean\" measurement); `piled` shows what "
                  "you get *after* correcting for pileup with `jdpileup`; "
                  "`piled_naive` shows what you'd get if you fit the exact "
                  "same pileup-affected data *without* realizing/correcting "
                  "for pileup. See \"Interpretation\" after the table.")
    lines.append("")

    for spectrum in SPECTRA:
        title = SPECTRUM_TITLES[spectrum]
        lines.append(title)
        lines.append("")
        lines.append(stage_method_table(records, spectrum))
        lines.append("")
        if spectrum in ("piled", "piled_naive"):
            lines.append("Stage A crashed for all three optimizers on this "
                          "spectrum (relxill's C++ code hard-aborts on an "
                          "unphysical Rout<=Rin excursion). This happens "
                          "for *both* piled cases -- with jdpileup's extra "
                          "free parameters (`piled`) and without them "
                          "(`piled_naive`, same 13 free parameters as "
                          "`unpiled`, which never crashes) -- so the crash "
                          "is driven by the piled data's shape itself, not "
                          "merely by pileup's extra parameters. See "
                          "CLAUDE.md Phase 4.")
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
    for spectrum in SPECTRA:
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
                  "`covar` failed the same way on `piled_naive` (again all "
                  "bounds undefined), and `conf` there is even slower "
                  "relative to `covar` (~1252x) and produces a strikingly "
                  "asymmetric `refl_frac` interval ([-1.78, +29.5]) -- a "
                  "large, lopsided uncertainty that is itself a symptom of "
                  "just how poorly determined that parameter is once "
                  "pileup goes uncorrected. Concretely: `covar` is cheap "
                  "and fine as a rough guide on "
                  "a well-converged fit, but should not be trusted as the "
                  "final word on parameter uncertainty for a model this "
                  "nonlinear, and can fail silently-ish (all-`None` bounds) "
                  "exactly when the fit is least well-behaved -- which is "
                  "when you'd want it most.")
    lines.append("")

    lines.append("## Interpretation: does correcting for pileup actually help?")
    lines.append("")
    lines.append("Referring back to the headline three-way table above:")
    lines.append("")
    lines.append("- **Fit quality alone cannot tell you whether pileup was "
                  "handled correctly.** `piled_naive`'s best Stage B fit "
                  "(cstat~1005.9, rstat~1.53) is statistically *at least as "
                  "good as*, if not marginally better than, the "
                  "jdpileup-corrected `piled` fit (cstat~1039.9, "
                  "rstat~1.59) -- despite `piled_naive` using the "
                  "structurally wrong model. `relxill`'s own free "
                  "parameters (`refl_frac` especially -- see below) are "
                  "flexible enough to partially absorb pileup's spectral "
                  "distortion and produce an equally clean-looking fit "
                  "to the wrong physical picture. The diagnostic plots "
                  "below show this directly: the naive fit *looks* just "
                  "as good as the corrected one.")
    lines.append("- **Spin is severely biased high in *both* piled cases, "
                  "corrected or not.** `piled` and `piled_naive` recover "
                  "spin within a few percent of *each other*, but both are "
                  "biased roughly 75-78% high relative to the unpiled fit's "
                  "close-to-truth ~-3%. On this evidence, `jdpileup` "
                  "correction does essentially nothing to rescue the spin "
                  "measurement for this source/pileup level -- a materially "
                  "important caveat for anyone using `relxill` on a "
                  "pileup-corrected Chandra spectrum to measure spin.")
    lines.append("- **`refl_frac` is the clearest single tracer of *whether* "
                  "pileup was corrected for, even though it doesn't track "
                  "spin's bias.** It's biased high in all three cases "
                  "(again likely entangled with the known `norm` "
                  "convention mismatch, Phase 3), but far more extremely in "
                  "the uncorrected `piled_naive` fit (+134%) than in either "
                  "the corrected `piled` fit (+34%) or the `unpiled` fit "
                  "(+65%) -- consistent with the fit inflating reflection "
                  "fraction to compensate for the flux jdpileup would "
                  "otherwise have accounted for.")
    lines.append("- **Inclination and nH are comparatively robust** across "
                  "all three cases (within ~2-9% of truth everywhere) -- "
                  "not everything is equally vulnerable to pileup.")
    lines.append("- **gamma and logxi are, perhaps counterintuitively, "
                  "*closer* to the unpiled fit's bias in the uncorrected "
                  "`piled_naive` fit than in the jdpileup-corrected `piled` "
                  "fit** (see the table). This doesn't mean skipping the "
                  "pileup correction is a good idea -- the fit quality "
                  "argument above and the badly-biased spin and refl_frac "
                  "values say otherwise -- but it's a reminder that "
                  "\"correcting\" for an instrumental effect with an "
                  "imperfect model does not uniformly move every parameter "
                  "closer to the truth.")
    lines.append("")

    lines.append("## Diagnostic plots (Stage B best fit, all three cases)")
    lines.append("")
    lines.append("![unpiled Stage B fit](plots/unpiled_stageB_fit.png)")
    lines.append("")
    lines.append("![piled Stage B fit (jdpileup-corrected)]"
                  "(plots/piled_stageB_fit.png)")
    lines.append("")
    lines.append("![piled_naive Stage B fit (uncorrected)]"
                  "(plots/piled_naive_stageB_fit.png)")
    lines.append("")
    lines.append("Note how visually similar the `piled` and `piled_naive` "
                  "fits are -- this is the same point made above: you "
                  "cannot tell from the fit residuals alone whether pileup "
                  "was actually corrected for.")
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
    lines.append("- `build_piled_naive_model()` explicitly deletes any "
                  "pileup model already attached to the piled dataset "
                  "before setting its plain source model -- Sherpa keeps a "
                  "dataset's pileup model separate from its source model, "
                  "so building the corrected (`piled`) and uncorrected "
                  "(`piled_naive`) models in the same session without this "
                  "would silently leave the old jdpileup wrap active "
                  "underneath the \"uncorrected\" fit. Hit this exactly "
                  "once while making the diagnostic plots (fixed before "
                  "any numbers here were generated -- the fit grid itself "
                  "was never affected, since each combination runs in its "
                  "own fresh subprocess).")
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
