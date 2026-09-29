## Multi-start check of Stage B (new for this ID)

The grid tables above use one fixed starting point for every fit (the
Phase 4 protocol, identical to ID 1000000081's). For this ID that was not
enough: the jdpileup-corrected **Stage C** fit (Afe frozen at 1, i.e. a
*subset* of Stage B's parameter space) reached cstat 841.2, below *every*
Stage B fit (best 970.3, `levmar`). That's impossible if the Stage B searches had
found Stage B's minimum. Worse, that 970.3 "best" Stage B fit has
`refl_frac = -16.8`, which in relxill selects the **reflection-only** model
branch (no primary continuum), a qualitatively different model.

`scripts/run_multistart.py` therefore reruns Stage B for each case from 18
starting points: a coarse, truth-agnostic lattice (a in {0, 0.5, 0.9} x
logxi in {1, 2.5} x Afe in {1, 5}) plus 6 seeds taken from the grid's own
Stage C/D end points. Each run is `levmar` then a `neldermead` polish, in
its own subprocess. The **flagship** Stage B fit of each case is the
lowest-cstat *physical* (`refl_frac > 0`) solution among all grid and
multi-start fits (`target.flagship_records()`); the headline three-way
table, conf/covar comparison and plots all use these flagship fits.

| Case | Grid best Stage B (fixed start) | Multi-start flagship | Distinct minima seen (cstat) |
|---|---|---|---|
| unpiled | 733.6 (`levmar`) | **702.0** (lattice start 9; start 11 agrees to 0.002) | ~702, ~709, ~731-734, ~875 |
| piled (jdpileup) | 970.3 (`levmar`, refl_frac<0 -- unphysical) | **702.6** (lattice start 7) | ~703-706, ~731-737, ~759-766, ~855, ~1049-1116 |
| piled_naive | 1059.2 (`moncar`, not converged) | **1042.7** (lattice start 8; four other starts within 0.12) | ~1043-1048, ~1075 |

All 54 multi-start fits completed; none crashed. The grid-derived seeds
never beat the lattice. Starting where a *more constrained* stage ended
up is not a substitute for spreading starts across parameter space.

## Interpretation: what changes at moderate pileup?

- **At ~30% count loss, `jdpileup` works.** The corrected piled flagship
  (cstat 702.6, reduced 1.07) is statistically indistinguishable from the
  unpiled flagship (702.0, 1.07). Its parameters track the unpiled ones
  closely: spin 0.49 vs 0.47 (truth 0.42), refl_frac 6.64 vs 6.36
  (truth 6.59), logxi 2.54 vs 2.51 (2.39), incl 28.1 vs 27.6 deg (26.2),
  gamma 1.24 vs 1.25 (1.39), nH 0.59 vs 0.58 (0.65). The residual offsets
  from truth are shared by both fits, so they are not pileup effects. Fitted pileup
  parameters: alpha = 0.115, f = 0.919.
- **Leaving pileup uncorrected is badly biased, and here you can tell from
  the fit.** The naive fit to the *same* piled data is worse by
  Delta-cstat ~ 340 (1042.7 vs 702.6, reduced 1.59 vs 1.07) for only two
  fewer free parameters. Its residuals show structure (around the
  2-2.3 keV mirror edge and a systematic excess above ~7 keV, where piled
  photon pairs land). The parameters it returns are unphysical in
  a telltale way: spin goes *retrograde* (-0.34 vs truth +0.42), logxi and
  Afe run to their lower limits (1e-5 and 0.5), and refl_frac is +130%.
  This is the opposite of ID 1000000081, where the naive fit was
  statistically as good as the corrected one.
- **Afe hits relxill's upper limit (10) in both good fits** (truth 7.3).
  Afe is poorly constrained at this count level and runs to the edge of
  the table. Treat the Afe values as a lower bound, not a measurement.
- **Stage B is again the right place to stop, but Stage C's solar-Afe
  freeze costs even more here.** Unpiled Stage C/D (~1238-1273) is far
  worse than Stage B (702) because the true Afe (~7.3) is further from
  solar than 081's (~2.6).
- **Stage A is less crash-prone than for 081 but still fragile.** 5 of 9
  Stage A runs crashed/timed out in total (unpiled: 1/3; piled: 2/3;
  piled_naive: 2/3), versus 6 of 9 for 081 (all six piled/piled_naive
  runs). Unlike 081, the unpiled Stage A also crashed once (`moncar`),
  so the relxill `Rout<=Rin` abort is not specific to piled data.
- **`levmar` does not get stuck on the jdpileup model here**, unlike 081
  (where it stalled at cstat ~76,000 on every piled stage). At moderate
  pileup the jdpileup likelihood surface is multi-modal, but not
  pathological for a gradient method.

## conf vs. covar (Stage B flagships, tables above)

- Each flagship was re-polished with `levmar` before `covar`/`conf`
  (`run_conf_flagship.py`). For the piled case this nudged cstat from
  702.6 to 700.8 (spin 0.49 → 0.50, refl_frac 6.64 → 6.52), well inside
  the `conf` intervals. The truth-comparison tables use the pre-polish
  multi-start record; the conf table uses the re-polished one.
- **Unpiled**: `covar` and `conf` agree to within ~10-40%, with `conf`
  showing the expected asymmetry (e.g. refl_frac covar ±0.099 vs conf
  [−0.099, +0.145]). `conf` took 79 s vs 0.5 s.
- **Piled (jdpileup)**: unlike ID 1000000081, where `covar` failed
  outright, `covar` returns bounds here. But they are often much *wider* than
  `conf`'s (logxi ±0.29 vs [−0.054, +0.057]; spin ±0.094 vs
  [−0.035, +0.029]; incl ±1.25 vs ±0.5 deg). So the linearized estimate
  is unreliable in *both* directions: overconfident for 081's unpiled fit,
  over-conservative here. `conf` took 308 s vs 1.6 s.
- **piled_naive**: `covar` bounds are undefined exactly for the
  parameters pinned at a limit (gamma, Afe; logxi's lower side). That
  pinning is a symptom of the mis-specified model.
- **Afe = 10 (relxill's upper limit)** in both good fits, so `conf` has no
  upper bound for it.
- **Statistical errors vs. bias**: the formal 1σ errors are small next to
  several truth offsets (e.g. unpiled gamma 1.250 ± 0.01 vs truth 1.395).
  Because the *same* offsets appear in the unpiled and corrected-piled
  fits, they reflect a model/degeneracy tension (plausibly Afe being
  capped at 10 and gamma compensating), not pileup.

## Caveat for the 081-vs-1838 comparison

ID 1000000081's Stage B numbers come from the fixed-start grid only; it
was not multi-started. Since that check changed 1838's answers
substantially, some of 081's biases (e.g. its unpiled logxi −33% and
refl_frac +65%) may also be local-minimum artifacts. Running
`python run_multistart.py` for 081 (default `TARGET_ID`) is the natural
follow-up before leaning on the heavy-vs-moderate contrast quantitatively.
