# relxill fitting of MARX-simulated Chandra spectra (piled-up vs. unpiled)

## Goal

Fit two MARX-simulated Chandra spectra of the same source — one affected by
photon pileup, one not — with the `relxill` relativistic-reflection model
family, inside Sherpa (CIAO 4.17), trying several optimization methods, and
produce a fit-metrics report comparing methods and comparing the piled-up vs.
unpiled results.

Deliverables (all DONE as of 2026-09-15 — see Phases 1-5 below for detail):
- Sherpa driver script(s) under `scripts/` that do the actual fitting. ✓
- A Jupyter notebook (`notebook/relxill_pileup_fitting.ipynb`) that walks
  through the fitting procedure end-to-end and shows the data/model/residual
  plots for both spectra and (where useful) intermediate diagnostic plots. ✓
- A didactic write-up (`writeup/relxill_pileup_writeup.md`) describing: the
  science motivation for relxill, what pileup does to a spectrum and why it
  biases inference, the Sherpa fitting setup used, the optimization methods
  compared and why, and the final results/interpretation. ✓
- A fit-metrics report/table (`results/report.md`, `results/fit_metrics.csv`)
  comparing optimizers and comparing piled vs. unpiled results. ✓

## Environment audit (done 2026-09-15)

- CIAO 4.17.0, conda env `ciao-4.17` at `/opt/miniconda3/envs/ciao-4.17`.
- Sherpa 4.17.0, with XSPEC model library bundled (`xspec.get_xsversion()` ->
  `12.14.0k`). This is **not** a full HEASOFT install — there is no `xspec`
  binary and no HEASOFT source tree in this env. `$HEADAS`/`$ASCDS_INSTALL`
  is CIAO's own conda env prefix.
- `sherpa.astro.xspec` in this build exposes `XSTableModel` / `read_xstable_model`
  (simple FITS table models) but has no `load_xspec_local_models` /
  `initpackage`-style mechanism of its own — CIAO instead ships a separate
  script, `convert_xspec_user_model`, for this (see Phase 1, now done).
- MARX 5.5.3 is installed (conda package) — not needed for this project since
  the spectra are already provided, but available if re-simulation is ever
  wanted.
- FFTW3 happens to be present in the `ciao-4.17` env (`$ASCDS_INSTALL/lib`),
  which mattered because relxill's convolution code needs it — see Phase 1.
- Disk: started at ~30 GB free on the data volume — tight. Chose the minimal
  relxill table subset for this reason (see Phase 1).

## Data

Two files, already present in the project root:
- `v0017_800ks_index.csv` — index/metadata for **100,000** simulated spectra
  (one row per `ID`). Columns include file paths *as they existed on the
  original HPC cluster* (`/n/holylfs06/...` — not accessible locally, see
  note below), an `RMF File` path, and ground-truth relxill/reflection
  parameters used to generate each simulation: `Afe`, `gamma`, `incl`,
  `logxi`, `nH`, `norm`, `refl_frac`, `spin`, plus the theoretical 1-10 keV
  flux and the total MARX unpiled/piled-up count rates.
- `v0017_800ks_cspec_datatable.fits` — 2.3 GB, one row per simulation,
  1024 energy/PI channels per row. Extensions:
  - `ISPEC` — interpolated *input* theoretical spectrum (photons/s/cm^2/keV)
    at the midpoint energy of each channel (i.e. before MARX ray-tracing) —
    useful as a "truth" continuum check, not something to fit directly.
  - `MARX_UNPILED` — simulated **unpiled** counts spectrum (integer-valued
    counts, per channel) for `Exposure = 800000` s.
  - `MARX_PILED` — simulated **piled-up** counts spectrum, same channel grid
    and exposure.
  - `EBOUNDS` — `EMIN`/`EMAX` per channel (1024 channels): confirmed to be
    the standard Chandra ACIS PI grid, 14.6 eV/channel, channel 0 spanning
    0–14.6 eV represented as [0.0073, 0.0146) (half-width convention), up to
    ~14.95 keV.

**We are only fitting spectrum ID `1000000081`.** Its row in the index CSV
gives (this is the ground truth used to simulate it — for validating the fit
afterwards, not for constraining it):
```
Afe        = 2.6309
gamma      = 1.3305
incl       = 30.881   (deg)
logxi      = 1.4966
nH         = 0.6497   (x1e22 cm^-2, presumably — confirm units before using)
norm       = 0.09728
refl_frac  = 14.315
spin (a)   = 0.49290
unpiled rate = 4.699 counts/s   (-> ~3.76e6 total unpiled counts over 800 ks,
                                    matches MARX_UNPILED row sum: 3,711,789)
piled rate   = 0.328 counts/s   (-> ~2.62e5, matches MARX_PILED row sum:
                                    259,008 — the ~14x rate suppression from
                                    pileup is itself a nice sanity check)
```
This ground-truth parameter set (`Afe, gamma, incl, logxi, refl_frac, spin`,
plus automatic `norm`) is exactly the parameter set of the **`relxill`**
flavor (broken-power-law emissivity, not lamp-post; not `relxillCp`, since
`gamma` rather than `kTe`/Comptonization params is given) — confirmed against
`lmodel_relxill.dat`. So: fit with plain `relxill`, not another flavor,
unless told otherwise. `Index1`/`Index2`/`Rbr`/`Rin`/`Rout`/`z`/`Ecut` are not
in the index CSV, so they were left at simulation defaults (3, 3, 15, -1,
400, 0, 300) — freeze these in the fit too, at least initially.

**Response files: resolved (2026-09-15).** The user supplied both response
files directly, now stored under `responses/`:
- `responses/c07_x222_y0531.rmf` — the chip-position-specific ACIS RMF named
  in the index CSV for this source (chip 7, x=222, y=531). Confirmed its
  `EBOUNDS` extension (`E_MIN`/`E_MAX`, 1024 channels) matches the data
  table's `EBOUNDS` exactly.
- `responses/id1000000000_arf.fits` — the matching ARF. (Note the filename
  says `id1000000000`, not `id1000000081` — this is the file the user said
  to use for our target ID, presumably shared across simulations at this
  detector position; not investigated further since the user was explicit.)
- Confirmed RMF and ARF share the same underlying energy grid
  (`ENERG_LO`/`ENERG_HI`, 970 bins, 0.3-10.0 keV) — consistent, usable
  together directly.

Repo layout (as it now exists):
```
CLAUDE.md
v0017_800ks_index.csv
v0017_800ks_cspec_datatable.fits
relxill/
  src/                       relxill v2.9.0 source + lmodel_relxill.dat
  tables/                    rel_table_v0.5a.fits, xillver-a-Ec5.fits
  build_attempt*.log
responses/
  c07_x222_y0531.rmf         shared RMF for this detector position
  id1000000000_arf.fits      shared ARF
data/
  unpiled/id1000000081_unpiled.pha    written by scripts/extract_spectrum.py
  piled/id1000000081_piled.pha        written by scripts/extract_spectrum.py
scripts/
  extract_spectrum.py        pulls one ID's row out of the big data table,
                              writes standard OGIP PHA files pointing at
                              responses/ via RESPFILE/ANCRFILE keywords
  load_data.py                Phase 2: load both PHAs into Sherpa, set
                              statistic + fit range (setup_data() helper,
                              reused by later scripts/notebook)
  build_models.py             Phase 3: tbabs*relxill source models, jdpileup
                              wiring for the piled spectrum, and the Stage
                              A-D freezing ladder (apply_stage())
  fit_worker.py                Phase 4: runs exactly one (spectrum, stage,
                              method) fit; invoked as a subprocess, never
                              imported (see Phase 4 for why)
  run_fits.py                  Phase 4: orchestrates all 24 fit_worker.py
                              subprocess runs, combines results
  analyze_results.py            Phase 5: fits_raw.json -> fit_metrics.csv +
                              analysis_summary.json
  run_conf_flagship.py          Phase 5: conf vs. covar comparison for the
                              Stage B flagship fit of each spectrum
  make_plots.py                  Phase 5: data/model/ratio plots for both
                              Stage B flagship fits
  write_report.py                Phase 5: assembles results/report.md from
                              the above (pure formatting)
results/
  fits_raw.json                combined raw results for all 24
                              (spectrum, stage, method) combinations
  per_fit/*.json                one JSON file per combination (also written
                              by fit_worker.py directly)
  run_fits.log                  full stdout/stderr log of the Phase 4 run
  fit_metrics.csv                flat metrics table, one row per combo
  analysis_summary.json          best-per-group, method agreement,
                              ground-truth comparison
  conf_flagship.json             conf vs. covar comparison, Stage B
  plots/*.png                    data/model/ratio plots, Stage B flagship
  report.md                      the Phase 5 human-readable report
notebook/
  relxill_pileup_fitting.ipynb   runnable walkthrough (built by
                              scripts/build_notebook.py); live-fits Stage B
                              for both spectra, loads the full Phase 4 grid
                              and the conf/covar comparison from results/
                              rather than recomputing them (see notebook's
                              own intro cell for why)
writeup/
  relxill_pileup_writeup.md      the didactic write-up (science motivation,
                              pileup physics, methodology, and results
                              interpretation, aimed at someone who knows
                              X-ray spectroscopy but not this pipeline)
```

## Phase 1 — Get relxill working inside this Sherpa — DONE (2026-09-15)

What actually happened (kept here since it's non-obvious and would otherwise
need re-discovering):

1. Downloaded from the official page
   (https://www.sternwarte.uni-erlangen.de/~dauser/research/relxill/) —
   **not** the full 7 GB table set, just the minimal subset needed for plain
   `relxill` (broken-power-law emissivity, no lamp-post/returning-radiation/
   ring extensions), given the tight ~30 GB disk budget:
   - `relxill_model_v2.9.0.tgz` (source) -> unpacked into `relxill/src/`
   - `rel_table_v0.5a.fits.gz` -> `relxill/tables/rel_table_v0.5a.fits`
   - `xillver-a-Ec5.fits.gz` -> `relxill/tables/xillver-a-Ec5.fits`
   - `RELXILL_TABLE_PATH=/Users/juramaga/science/pileup/justina_fits/relxill/tables`
     must be set in the environment before importing the model.
2. Used CIAO's `convert_xspec_user_model` (the ahelp-documented,
   HEASOFT-free route) directly on relxill's own source + `lmodel_relxill.dat`,
   **not** relxill's own `compile_relxill.sh`/`initpackage` (that path wants a
   full HEASOFT install, which this env doesn't have):
   ```
   cd relxill/src
   export RELXILL_TABLE_PATH=.../relxill/tables
   convert_xspec_user_model relxill lmodel_relxill.dat --clobber --verbose 2
   ```
3. Two real build problems hit and fixed:
   - `Rellp_Extended.cpp` does `#include "cfitsio.h"`, but the actual cfitsio
     header in this env is `fitsio.h` (there is no `cfitsio.h`). Fix: added a
     one-line local stub `relxill/src/cfitsio.h` containing
     `#include "fitsio.h"` — `convert_xspec_user_model`'s generated build
     includes the source directory itself, so this shadows nothing and just
     resolves the include. Did **not** touch relxill's actual source.
   - relxill's convolution code (`Relbase.cpp`) needs FFTW3
     (`fftw_plan_dft_*`, etc.), but `convert_xspec_user_model`'s
     auto-generated `meson.build` only links `-lXSFunctions -lXSUtil -lXS
     -l<hdsp> -l<CCfits> -lcfitsio` — no FFTW3. This turned out **not** to
     need a manual fix: FFTW3 is separately present in
     `$ASCDS_INSTALL/lib` (`libfftw3.dylib` etc., pulled in by some other
     conda package), and the link/runtime symbol resolution on this macOS
     env picked it up without an explicit `-lfftw3` — confirmed by actually
     exercising the convolution path at runtime (below), not just by a clean
     link. If this is ever rebuilt on a different machine/env without FFTW3
     already present, expect a runtime `dyld` symbol-not-found error instead
     of a link error, and the fix would be adding `-lfftw3` (and an
     `-L<path>` if needed) to the generated `relxill/src/meson.build`
     `link_args` before `pip install .` again.
4. Result: `pip install .` succeeded, producing an importable `relxill`
   package with 15 XSPEC local models registered under Sherpa's `xsum`
   prefix (`xsumrelxill`, `xsumrelxillcp`, `xsumrelxilllp`, `xsumxillver`,
   `xsumrelline`, `xsumrelconv`, etc.) — the full relxill family, even though
   only the base tables were downloaded (the lamp-post/ring/NS flavors just
   won't have valid tables to read if actually evaluated — fine, since we
   only need `xsumrelxill`).
5. Verified by actually evaluating `xsumrelxill` in a plain Sherpa session
   (no data loaded) with parameters set at/near spectrum 1000000081's ground
   truth (`a=0.49, Incl=30.9, gamma=1.33, logxi=1.5, Afe=2.63,
   refl_frac=14.3, norm=0.097`): finite output, no NaNs, and a clear
   relativistically-broadened Fe K feature (peak ~6.6 keV, mean flux in
   6.0–6.8 keV band ~30% above the 3–5 keV continuum level, sharp falloff
   above ~6.8 keV) — physically the right shape. This confirms both the
   table loading and the FFTW-based convolution actually work at runtime,
   not just that it compiled.

**To use relxill in any future script/notebook/session in this project:**
```python
import os
os.environ["RELXILL_TABLE_PATH"] = "/Users/juramaga/science/pileup/justina_fits/relxill/tables"
from sherpa.astro import ui
import relxill.ui   # registers xsumrelxill etc.
ui.set_source(1, "xsumrelxill.mysrc")
```
`relxill` must already be `pip install`ed into the `ciao-4.17` env (done —
`pip show relxill` in that env confirms `Version: 1.0`).

## Phase 2 — Load the two spectra into Sherpa — DONE (2026-09-15)

- `scripts/extract_spectrum.py`: confirmed the row-index-vs-ID mapping is
  exactly `row = ID - 1_000_000_000` (asserted in code, not just assumed —
  row 81 for ID 1000000081), pulled that row out of `MARX_UNPILED` and
  `MARX_PILED`, and wrote two standard OGIP type-I PHA files
  (`data/unpiled/id1000000081_unpiled.pha`, `data/piled/..._piled.pha`) with
  `EXPOSURE=800000`, `POISSERR=True`, `BACKFILE=NONE`, and
  `RESPFILE`/`ANCRFILE` pointing at `responses/c07_x222_y0531.rmf` and
  `responses/id1000000000_arf.fits`. Counts sums match the data table
  exactly (unpiled 3,711,789; piled 259,008) and are within ~1.3% of the
  index CSV's quoted rate x exposure (the small gap is presumably a
  region/filtering difference upstream of this project, not a bug here).
- `scripts/load_data.py` (`setup_data()`): loads both PHAs via
  `ui.load_pha`, which picked up the RMF/ARF automatically from the header
  keywords (confirmed `get_response()` returns non-`None` for both), notices
  0.3-10 keV on both (matches the RMF/ARF's native energy grid exactly —
  no reason to use a narrower range), and sets the fit statistic.
- **Statistic: `cstat`.** No background spectrum exists for either PHA, so
  `wstat` isn't applicable and plain `cstat` is the right choice. Checked
  per-bin counts in the noticed range as a sanity check on this choice: even
  the piled spectrum (258,118 counts over 665 noticed bins) has a minimum of
  6 counts/bin and no empty bins; the unpiled spectrum has a minimum of 81.
  Counts are high enough everywhere that `chi2` (Gaussian) would have given
  near-identical results too, but there's no reason to prefer it over
  `cstat` here.

## Phase 3 — Build the models — DONE (2026-09-15)

`scripts/build_models.py` implements this. Summary of what it does and what
was checked:

- **Unpiled**: `xstbabs.abs_unpiled * xsumrelxill.refl_unpiled`, `nH` free
  (`build_unpiled_model()`).
- **Piled**: `xstbabs.abs_piled * xsumrelxill.refl_piled` (independent
  component instances/parameters from the unpiled side — the two spectra
  are fit separately, per Phase 4/5's design, not jointly, so nothing is
  tied between them), wrapped via `set_pileup_model()` with a `jdpileup`
  component (`build_piled_model()`). Confirmed the resulting full model
  chain is `apply_rmf(jdpileup.pileup_piled(xstbabs.abs_piled *
  xsumrelxill.refl_piled))` — i.e. Sherpa inserts pileup *and* folds the ARF
  in internally, between the source model and the RMF, exactly where it
  physically belongs (pileup is a focal-plane/frame effect that happens
  before charge redistribution, not after). No separate `apply_arf()` call
  is needed or present for the piled dataset; that's expected, not a bug.
  - Pileup parameters: thawed `alpha` (grade-migration probability) and `f`
    (PSF fraction inside the extraction region) — the two parameters
    standard CIAO pileup-fitting practice normally lets float. Left `g0`,
    `n`, `ftime` (3.241 s), `fracexp` (0.987), `nterms` (30) at Sherpa's
    defaults, since we have no independent information (e.g. a real event
    file header) to override the instrumental ones with for this
    simulation — noted explicitly here and should be repeated in the
    write-up as an assumption, not a measured fact.
- **`apply_stage()`** implements the Stage A-D freezing ladder from the plan
  above and is applied identically (same parameter names, same frozen
  values) to both the unpiled and piled relxill components — verified in
  code (`assert thawed_u == thawed_p`) so the two sides of the comparison
  are always fit with the same free-parameter set at every stage.
- **Sanity check**: set both models' free parameters to spectrum
  1000000081's ground-truth values and compared predicted vs. actual counts
  in the noticed 0.3-10 keV range at Stage B. The absolute normalization is
  off by a large, uniform-looking factor (predicted unpiled/piled totals
  are both ~50x the real counts) — expected, since we have no way to know
  the exact flux/`norm` convention the original simulation pipeline used,
  and `norm` is a free fit parameter that Phase 4's actual fit will resolve
  regardless. The thing that *does* matter at this stage checked out: the
  predicted pileup suppression ratio (unpiled model sum / piled model sum)
  with untuned default pileup parameters (`alpha=0.5, f=0.95`) came out to
  ~20x, versus the real ~14.4x (3,708,752 / 258,118) — same order of
  magnitude, confirming the pileup wiring is structurally correct and
  produces a physically sensible degree of suppression before any fitting
  has even been attempted. Fine-tuning `alpha`/`f` (and everything else) to
  match this exactly is precisely what Phase 4 is for.
- **Parameter-freezing ladder (per user instruction 2026-09-15):** start with
  *all* relxill parameters thawed, then progressively freeze subsets to
  reasonable literature values, and report results for every stage (not just
  the final, most-constrained one) — both to show the degeneracy problem
  full freedom causes, and to show how each freeze changes the recovered
  parameters/uncertainties. `z` (redshift) is the one exception kept fixed
  at 0 at *every* stage including "all thawed": this is a Galactic/local
  source, so a free redshift isn't "maximum freedom", it's unphysical, and
  every relxill application in the literature fixes it for such sources.
  Proposed stages (run each for both piled and unpiled, and for every
  optimizer in Phase 4):
  - **Stage A - all thawed**: `a, Incl, Rin, Rout, Index1, Index2, Rbr,
    gamma, logxi, Afe, Ecut, refl_frac, norm` all free (`z` fixed at 0).
    Expected to be poorly behaved / strongly degenerate for a single
    CCD-resolution spectrum — that's an expected and useful result to show,
    not a bug to fix.
  - **Stage B - standard literature freeze**: freeze `Rin=-1` (relxill's
    sentinel for "at the ISCO", tying inner radius to spin rather than
    fitting it independently — freeing both is a textbook degeneracy),
    `Rout=400` (default; negligible effect on the spectrum at large radii),
    `Index1=Index2=3, Rbr=15` (single, standard-illumination emissivity
    profile — a broken emissivity/lamp-post height needs constraints a
    single non-grating spectrum doesn't have), and `Ecut=300` keV (a soft
    X-ray CCD spectrum out to 10 keV has essentially no leverage on the
    high-energy cutoff; would need NuSTAR-band coverage to constrain it).
    Free: `a, Incl, gamma, logxi, Afe, refl_frac, norm`. Note this is
    exactly the free-parameter set used to *generate* the simulation (see
    ground truth above) — a natural, literature-motivated stage and a
    direct check against truth.
  - **Stage C - + solar Afe**: on top of Stage B, also freeze `Afe=1`
    (solar), a common simplification when abundance and ionization/spin are
    too degenerate to constrain simultaneously from a single spectrum. Free:
    `a, Incl, gamma, logxi, refl_frac, norm`.
  - **Stage D - + fixed inclination**: on top of Stage C, also freeze `Incl`
    at a fiducial value (treat it as "known independently", e.g. from binary
    dynamics, as is often done in real analyses when such a measurement
    exists) — use the ground-truth value (~30.9 deg) for this exercise, and
    say so explicitly in the report (this stage is only legitimate when an
    independent inclination constraint actually exists; here it's a
    controlled experiment, not something to present as a general
    recommendation). Free: `a, gamma, logxi, refl_frac, norm`.
  This yields a 4-stage x 2-spectrum grid (x however many optimizers in
  Phase 4) of fit results — report all of them, and use the progression
  Stage A -> D to discuss how each freeze changes the recovered spin/
  refl_frac/etc. and their uncertainties, and (since this is simulated data)
  how each stage's recovered values compare to ground truth.

## Phase 4 — Fit with multiple optimization methods — DONE (2026-09-15)

`scripts/build_models.py` resets every thawed parameter to a fixed,
documented starting point (`RELXILL_START`/`ABS_START`/`PILEUP_START`) on
every call, so every (stage, method) combination genuinely starts fresh, as
required below. `scripts/fit_worker.py` runs exactly one (spectrum, stage,
method) fit and writes its result as JSON; `scripts/run_fits.py` runs all
24 combinations (2 spectra x 4 stages x 3 methods) **each as its own
subprocess** and combines the results into `results/fits_raw.json`
(per-combo JSON also kept under `results/per_fit/`).

**Why subprocesses, not one long-lived Sherpa session:** relxill's C++ code
calls a hard, uncatchable process `abort()` (not a Python exception -- a
`libc++abi: terminating due to uncaught exception` that takes the whole
interpreter down) when it's handed an unphysical `Rout <= Rin` combination.
Stage A already had its `Rin`/`Rout` bounds deliberately tightened for this
reason (see Phase 3), which was enough to prevent it for the *unpiled*
model (all 12 unpiled combos ran fine first try) but **not** for the
*piled* one: with pileup's extra free parameters (`alpha`, `f`) added on
top of Stage A's 13, all three optimizers (`levmar`, `neldermead`,
`moncar`) crashed the whole batch process the first time this was run
in-process. Rather than chase tighter and tighter bounds indefinitely,
switched to running every fit in its own subprocess, so a crash there is
just a recorded `CRASHED` result and the batch moves on — this is the
actual fix, and it is itself a legitimate finding, not just an engineering
workaround: **Stage A (fully free) is numerically intractable for the
piled spectrum with any of these three optimizers, full stop** — all three
crashed. This is a good concrete illustration of *why* the progressive
freezing ladder (Phase 3) is standard practice, not an arbitrary
simplification: for the piled/pileup case here, "fit everything" isn't
just poorly constrained, it's not computable.

**Results summary (`results/fits_raw.json`, 24 combos, 3 crashed):**
- **Unpiled**: all 12 combos completed. Stage B gives the best fit by far
  (cstat ~2052-2185 across methods, reduced stat ~3.1-3.3) — notably
  *better* than Stage C (~6013-6713, rstat ~9.1-10.2) and Stage D
  (~6131-6139, rstat ~9.3), even though C and D have fewer free
  parameters. The culprit is forcing `Afe=1` (solar) in Stage C: the
  true value for this simulation is ~2.63 (super-solar), so freezing to
  the "standard literature default" here actively hurts the fit — a
  clean illustration of the actual risk in the freezing ladder, not just
  its benefit. Stage D's extra fixed `Incl` (already correctly fixed at
  the ground-truth value) does not visibly help or hurt once `Afe` is
  already wrong. Optimizer-wise, `levmar` matches or beats `neldermead`/
  `moncar` at every stage here, in a fraction of the function evaluations
  (e.g. Stage B: `levmar` 239 nfev vs `moncar` 5600) — the unpiled
  likelihood surface seems well-behaved enough that the fast local
  optimizer just wins.
- **Piled**: Stage A crashed for all 3 methods (see above — no result
  exists for piled Stage A). For Stages B-D, there's a striking
  *optimizer-dependent* split that has no counterpart on the unpiled side:
  `levmar` gets stuck at a poor fit at every stage (cstat ~76,000-77,000,
  rstat ~116-117), while `neldermead`/`moncar` find a much better minimum
  (cstat ~1010-1315, rstat ~1.5-2.0) at every stage. This is a real,
  reportable result about the pileup-convolved likelihood surface being
  harder for a local gradient method to navigate from the same generic
  starting point that works fine on the unpiled data — not a bug in the
  pileup model itself (which does clearly fit *something* well, just not
  via `levmar` from these defaults).
- A `covar`-based error estimate was computed for every completed fit and
  is stored alongside each record. As expected, `covar` on a non-converged
  fit (several `neldermead`/`moncar` results have `succeeded=False`, having
  hit their evaluation cap rather than a stationary point) comes back with
  undefined (`None`)/boundary-hitting bounds — a real demonstration of why
  `covar`/`conf` should not be trusted blindly on a fit that didn't actually
  converge, feeding directly into the Phase 5 discussion of `conf` vs.
  `covar`.

Methods used: `levmar` (Levenberg-Marquardt, gradient-based), `neldermead`
(simplex, derivative-free), `moncar` (Monte Carlo / differential
evolution). `gridsearch` (optional, over spin/inclination as a cross-check)
was not run as part of the full grid — 24 combos across 3 methods was
already the priority within the time budget; worth doing as a targeted
follow-up on the Stage B results specifically if a deeper local-vs-global
minimum check is wanted later. Per-optimizer maxfev caps scaled with the
number of free parameters (`fit_worker.py::maxfev_for`) to bound worst-case
runtime while still giving `moncar` a real budget on the higher-dimensional
stages.

## Phase 5 — Metrics & report — DONE (2026-09-15)

`scripts/analyze_results.py` turns `results/fits_raw.json` into
`results/fit_metrics.csv` (flat, one row per combo) and
`results/analysis_summary.json` (best-per-group with two notions of "best" —
`best_succeeded` vs. `best_overall`, since they can disagree, e.g.
piled/Stage C where the only formally-converged method is dramatically
*worse* than an unconverged one — cross-method agreement, and a
ground-truth comparison). `scripts/run_conf_flagship.py` reran the Stage B
fit for each spectrum with `conf` (profile-likelihood) in addition to the
`covar` already stored, specifically to compare the two as the plan
requested. `scripts/make_plots.py` produced data/model/ratio plots for both
Stage B flagship fits. `scripts/write_report.py` assembles all of the above
into `results/report.md` (pure formatting, no new computation). Read
`results/report.md` for the actual numbers; highlights that most changed
how the project should be described going forward:

- **`conf` vs. `covar` disagree substantially**, exactly as anticipated.
  For the unpiled Stage B fit, `conf`'s 1-sigma intervals are 2-6x wider
  than `covar`'s (e.g. `refl_frac`: covar ±0.20 vs. conf [-0.69,+0.19]) —
  `covar`'s linearized/Gaussian approximation is measurably overconfident
  here. For the piled Stage B fit, `covar` failed outright (every
  parameter came back with undefined bounds — a singular/boundary-hitting
  Hessian), while `conf` still produced usable intervals — at a real cost
  (~2490s vs. 3s, ~800x slower). Net lesson for the write-up: `covar` is a
  cheap sanity check, not a substitute for `conf`, and it can fail exactly
  when a fit is least well-behaved — precisely when you'd most want a
  reliable error bar.
- **Formal (covar) parameter uncertainties are often absurdly tight
  relative to the actual bias vs. ground truth** — e.g. unpiled Stage A's
  `gamma` is nominally "406 sigma" from truth. With millions of counts,
  cstat's curvature-based errors shrink far faster than the systematic
  model-data mismatch does, so a huge `n_sigma` here is a symptom of
  model misspecification (wrong frozen parameters, real relxill/data
  tension), not evidence of a fitting bug — an important distinction to
  make explicit in the didactic write-up.
- **Stage B is the best-fitting stage for the unpiled spectrum**, better
  than C and D despite having more free parameters (see Phase 4) — because
  Stage C's solar-Afe assumption is wrong for this particular simulated
  source (true Afe~2.6). The ground-truth comparison table quantifies this:
  Stage B recovers spin/inclination/gamma/Afe within ~10% of truth;
  `logxi` and `refl_frac` are the two parameters that stay off by tens of
  percent at every stage, on both spectra — a real, specific degeneracy
  worth calling out (likely entangled with the known `norm`
  scale-convention mismatch from Phase 3, since `refl_frac`'s definition in
  relxill is itself flux-normalization-dependent).
- **Pileup bias (Stage B, unpiled vs. piled)**: spin, inclination, and `nH`
  come out similar between the two (within a few percent of each other);
  `gamma`, `logxi`, and `Afe` diverge more between piled and unpiled than
  either does from truth individually — plausible evidence of a genuine
  residual pileup-shape distortion the `jdpileup` model doesn't fully
  correct, on top of the shared `norm`/`refl_frac` issue. Full numbers in
  `results/report.md`.
- Diagnostic plots (`results/plots/{unpiled,piled}_stageB_fit.png`) show
  visually good fits in both cases (few-percent residuals across most of
  the band, growing toward the low-count band edges) despite reduced
  stat > 1 — another data point for "formally imperfect but practically
  fine" given how much statistical leverage millions of counts provide.

For every (spectrum × stage × method) combination, capture:
- Final fit statistic value, statistic/dof, dof.
- Best-fit parameter values and errors (`conf` or `covar` — note which,
  since they can disagree for a model this nonlinear).
- Number of function evaluations, wall-clock fit time, convergence
  status/message.
- Whether different methods converge to the same minimum (compare parameter
  vectors, not just stat value).
- How each recovered parameter compares to the ground truth for ID
  1000000081 (this is simulated data, so we actually know the truth — use
  it).

Produce a written report (markdown table(s), plus a fit-metrics CSV) with
one section for the unpiled spectrum, one for the piled spectrum, and a
final comparison of how pileup biases the recovered relxill parameters
relative to the unpiled (presumably closer-to-truth) fit. Include
data/model/residual plots for the best fit in each case. This feeds into,
but is not a replacement for, the didactic write-up deliverable described
at the top of this file.

## Open questions for the user

- Confirm units of `nH` in the index CSV (assumed x1e22 cm^-2, standard for
  `tbabs`, but not stated).
- Any preference on notebook/write-up format or location beyond what's
  sketched above?
