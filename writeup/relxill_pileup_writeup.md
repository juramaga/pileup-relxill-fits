# Fitting relativistic disk reflection through pileup: a Chandra/relxill case study

*A didactic walkthrough of fitting a MARX-simulated Chandra spectrum with
`relxill` in Sherpa, with and without photon pileup, comparing optimizers
and freezing strategies. Companion documents: `CLAUDE.md` (full decision
log and methodology, Phases 1-5), `results/report.md` (the complete numeric
fit-metrics report), `notebook/relxill_pileup_fitting.ipynb` (a runnable
walkthrough).*

## 1. Why this analysis, and why it's hard

A black hole accretion disk reprocesses ("reflects") the hard X-ray
continuum produced by its corona: photons Compton-scatter and photoionize
the disk surface, producing a reflection spectrum dominated by a broad
iron-K fluorescence line near 6.4 keV and a Compton reflection hump peaking
around 20-30 keV. Close to the black hole, this reflected light is
imprinted with strong gravitational and Doppler effects — gravitational
redshift, light bending, and relativistic Doppler boosting from the fast
orbital motion of the inner disk — which broaden and skew the line profile.
Because the inner edge of the disk (for a disk truncated at the innermost
stable circular orbit, the ISCO) moves closer to the black hole as spin
increases, the *shape* of this broadened line profile is one of the few
direct observational handles on black hole spin. `relxill`
(Garcia et al. 2014, Dauser et al.) is the standard tool for this: it
self-consistently combines a relativistic line-broadening calculation with
an ionized reflection spectrum (`xillver`) computed for a given ionizing
continuum, disk ionization, and iron abundance.

Extracting spin (and the other reflection parameters) from a single CCD
spectrum is already a hard inverse problem — the line shape depends
jointly on spin, inclination, emissivity profile, ionization, abundance,
and the reflection fraction, several of which are strongly correlated. This
project adds a second, purely instrumental complication: **photon pileup**.
On a Chandra ACIS CCD, if a source is bright enough that more than one
photon lands in the same pixel (or adjacent pixels) within a single frame
readout time (~3.2 s for standard timed-exposure mode), those events are
read out as a single event whose energy is roughly the *sum* of the
individual photon energies, or are rejected entirely by onboard grade
filtering. The practical consequences are: (1) the observed count rate is
suppressed relative to the true incident rate, non-linearly, worse at
higher rates; (2) the spectrum is *hardened*, because pairs of soft photons
pile into a single harder-looking event; and (3) this happens
preferentially at the peak of the point-spread function, so the effect is
spatially structured within the extraction region, not just a flat
rescaling. All three of these directly interfere with measuring a
reflection spectrum, whose diagnostic power lives precisely in its detailed
energy-dependent shape.

This project fits the same underlying source — one MARX-simulated
spectrum, both with and without pileup applied — to see how much pileup
degrades the recovered reflection parameters relative to a matched
pileup-free version of the same observation, using known "ground truth"
values (since this is simulated data) to grade the fits honestly.

## 2. Data

The target is spectrum **ID 1000000081** out of a table of 100,000
MARX-simulated Chandra ACIS spectra (`v0017_800ks_cspec_datatable.fits`,
indexed by `v0017_800ks_index.csv`), each simulated at an 800 ks exposure.
For this ID, the simulation's true (input) parameters were:

| Parameter | Value |
|---|---|
| spin (`a`) | 0.4929 |
| inclination (`Incl`) | 30.88 deg |
| photon index (`gamma`) | 1.3305 |
| ionization (`logxi`) | 1.4966 |
| iron abundance (`Afe`) | 2.6309 (super-solar) |
| reflection fraction (`refl_frac`) | 14.315 |
| absorbing column (`nH`) | 0.6497 (x1e22 cm^-2) |

The data table provides two count spectra for this same underlying source
and exposure: an **unpiled** version (3,711,789 total counts) and a
**piled** version of the same simulation run through MARX's pileup model
(259,008 total counts — roughly a factor of 14 fewer, consistent with how
aggressively pileup suppresses count rate for a source this bright). Both
share the same 1024-channel Chandra ACIS PI grid (14.6 eV/channel). A
matching RMF and ARF (chip position c07, x=222, y=531) were supplied
separately and confirmed to share a common 0.3-10 keV energy grid with each
other and with the data table's channel boundaries — that consistency check
mattered, because getting the response wrong would silently invalidate
every fit downstream.

Both spectra were fit with Sherpa's `cstat` (Cash statistic for Poisson
data), the appropriate choice here since neither has an associated
background spectrum (ruling out `wstat`) and both have far too many counts
per bin for the `chi2`-vs-`cstat` choice to matter in practice, but no
principled reason to prefer the Gaussian approximation over the Poisson
one.

## 3. Getting `relxill` running at all

This is worth a paragraph because it was the single largest source of
unplanned work, and it shapes what's trustworthy about everything
downstream. The environment here is CIAO 4.17's own Sherpa, which bundles
its own compiled XSPEC model library — it is *not* a full HEASOFT
installation, so `relxill`'s own documented build process (which expects
HEASOFT's `initpackage`/`lmod` machinery) does not apply directly. CIAO
instead provides an experimental tool, `convert_xspec_user_model`, that
compiles an XSPEC local model's C/C++/Fortran source directly against
Sherpa's own bundled XSPEC libraries. Two real build problems came up along
the way: `relxill`'s source includes a header (`cfitsio.h`) that doesn't
exist under that name in this environment (only `fitsio.h` does — fixed
with a one-line local stub, no changes to relxill's own source), and
`relxill`'s convolution code depends on FFTW3, which
`convert_xspec_user_model`'s auto-generated build doesn't link by default
(it happened to resolve anyway because FFTW3 was already present in the
environment for unrelated reasons — this is a fragile coincidence worth
flagging for anyone reproducing this on a different machine). The full
account, including the exact commands, is in `CLAUDE.md` Phase 1.

More importantly for interpreting the results below: `relxill`'s C++ code
does not fail gracefully on all invalid parameter combinations. Handed an
unphysical `Rout <= Rin` (outer radius inside the inner radius), it calls a
hard, uncatchable process abort rather than returning an error or a `NaN`.
This turned out to be directly reachable by a stochastic optimizer sampling
freely over `relxill`'s full native parameter ranges — see Section 6.

## 4. Model setup

For each spectrum, the source model is `tbabs * relxill` (interstellar
absorption times the reflection model). The piled spectrum additionally
wraps this in Sherpa's `jdpileup` model (implementing the Davis 2001
ACIS pileup algorithm), inserted by Sherpa between the source model and
the RMF — physically correct, since pileup is a focal-plane effect that
happens before the detector's energy redistribution, not after. Of
`jdpileup`'s parameters, `alpha` (the probability that a piled event
survives Chandra's onboard grade filter as a "good" event) and `f` (the
fraction of the source's PSF falling inside the extraction region, which
controls how much of the flux is even subject to pileup) were left free to
fit; the frame time, exposure fraction, and a couple of other parameters
were left at Sherpa's standard ACIS defaults, since no real event-file
header exists for this simulation to read them from — a modeling
assumption worth remembering when judging the piled fit's absolute
accuracy.

### The parameter-freezing ladder

`relxill` has more free parameters than a single CCD-resolution spectrum
can usefully constrain simultaneously — this is not a limitation specific
to this dataset, it's a standard feature of reflection modeling, and the
literature's response to it is to freeze parameters the data can't
independently determine to sensible fixed values. This project deliberately
explores that tradeoff explicitly rather than jumping straight to a final
configuration, fitting the same two spectra at four progressively more
constrained "stages":

- **Stage A — everything thawed.** Spin, inclination, the (otherwise
  usually-fixed) emissivity profile shape, inner/outer radius, ionization,
  abundance, reflection fraction, and normalization all free. Included
  specifically to show what happens *without* the simplifications below,
  not because it's expected to work well.
- **Stage B — the standard literature freeze.** Inner radius tied to the
  ISCO (`relxill`'s own convention: a negative `Rin` value is interpreted as
  a multiple of the ISCO radius, so `Rin=-1` means "exactly at the ISCO" —
  freeing `Rin` independently of spin is a well-known, nearly unbreakable
  degeneracy, since both control where the line profile's blue wing
  cuts off), outer radius fixed far out, a single power-law emissivity
  profile (rather than the broken profile or lamp-post geometry that would
  need spatially-resolved or timing information this spectrum doesn't
  have), and a fixed high-energy cutoff (a 0.3-10 keV CCD spectrum has
  essentially no leverage on where the continuum cuts off in the tens-
  to-hundreds-of-keV range; that needs NuSTAR-band coverage). This
  happens to be exactly the free-parameter set used to generate the
  simulation in the first place, which makes it a natural, principled
  point of comparison.
- **Stage C — Stage B plus solar iron abundance.** Freezing `Afe=1` is a
  common simplification in the literature when the data can't
  simultaneously constrain abundance and ionization/spin. It's included
  here specifically because this particular simulated source has a
  *super-solar* true abundance (`Afe~2.6`) — so this stage is a deliberate
  test of what happens when a "standard, reasonable" simplifying assumption
  happens to be wrong.
- **Stage D — Stage C plus a fixed inclination.** Sometimes a source's
  inclination is known independently (e.g. from binary dynamics or an
  eclipse), and it's standard to fix it in that case. This is a controlled
  experiment using the simulation's true inclination, not a general
  recommendation — real analyses should only do this with an actual
  independent measurement.

Redshift is fixed at zero at every stage, including "Stage A". This is
deliberate, not an oversight: the source is Galactic/local, so letting `z`
float isn't "more freedom", it's unphysical, and every real `relxill`
application for a source like this fixes it.

### Optimizers compared

Three Sherpa optimizers were run at every (spectrum, stage) combination,
each starting from the same fixed, `relxill`-default parameter values (not
chained from a previous method's result, so each method's own behavior is
what's actually being measured):

- **`levmar`** (Levenberg-Marquardt): a fast, gradient-based local
  optimizer — Sherpa's default, and usually the right first choice, but
  only as good as the local minimum it happens to fall into.
- **`neldermead`** (downhill simplex): derivative-free, generally more
  robust to a noisy or non-smooth likelihood surface than a gradient
  method, at the cost of needing many more function evaluations.
- **`moncar`** (a Monte Carlo / differential-evolution-style global
  search): intended to be less prone to getting stuck in a poor local
  minimum than either of the above, at a further cost in function
  evaluations.

## 5. Results

The complete numeric results for all 24 (spectrum x stage x method)
combinations are in `results/report.md` and `results/fit_metrics.csv`;
this section pulls out the findings that actually matter for interpreting
the science, and for anyone repeating an analysis like this one.

### 5.1 The freezing ladder doesn't just reduce parameters — it can help or hurt

For the unpiled spectrum, Stage B (`cstat~2054`, reduced stat~3.13) fits
*substantially* better than Stage C (`cstat~6017`, reduced stat~9.14) or
Stage D (`cstat~6139`, reduced stat~9.32), despite Stages C and D having
strictly fewer free parameters. The reason is directly traceable: Stage C
freezes iron abundance to the "standard, literature-typical" solar value,
which is simply wrong for this particular source (true `Afe~2.6`). Forcing
a wrong value onto a real physical parameter degrades the fit more than
the reduced dimensionality helps it — a concrete illustration that "freeze
what the literature usually freezes" is a heuristic with real failure
modes, not a free lunch. Stage D's additional fixed inclination (correctly
fixed at the true value here) makes essentially no further difference once
`Afe` is already wrong — the damage is already done by that point.

### 5.2 Optimizer choice matters differently for the two spectra

On the unpiled spectrum, `levmar` matches or beats the other two optimizers
at every stage, and does it in a fraction of the function evaluations (at
Stage B: 239 evaluations for `levmar` vs. 5600 for `moncar`, reaching
statistically indistinguishable minima). The unpiled likelihood surface
seems to be well-behaved enough that the fast local method just wins.

On the *piled* spectrum, the picture inverts: `levmar` gets stuck in a
clearly worse local minimum at every single stage (reduced stat
~116-117), while `neldermead` and `moncar` both consistently find a much
better fit (reduced stat ~1.5-2.0) from the same generic starting point.
This isn't a flaw in the pileup model itself — it clearly *can* fit the
data well, just not via `levmar`'s local gradient descent from these
starting values. It's a genuinely useful practical lesson: pileup's
non-linear, iterative internal calculation (`jdpileup` effectively
convolves the source spectrum against itself to build up the piled-event
distribution) appears to produce a rougher likelihood surface than the
unpiled case, and a purely local gradient method is measurably less
reliable on it. A pileup analysis that only tries `levmar` and reports
convergence is not, on this evidence, safe to trust without a
cross-check from a derivative-free or global method.

### 5.3 Stage A is not just poorly constrained for the piled spectrum — it's uncomputable

All three optimizers *crashed* — not converged poorly, actually crashed the
Python process — when given the piled spectrum's full 15-parameter Stage A
freedom (13 `relxill` parameters plus pileup's `alpha` and `f`). This
traces back to the hard-abort behavior described in Section 3: with
`relxill`'s native `Rin` range (equivalent to 1x-100x the ISCO radius) and
`Rout` range (1-1000 gravitational radii) both fully open, and pileup
adding yet more freedom to the fit, all three optimizers eventually sampled
a combination where the sentinel-encoded inner radius exceeded the outer
radius, and the whole process died rather than the fit merely failing.
Tightening those bounds (still leaving both genuinely free over a
physically generous sub-range — nobody fits `Rin` beyond ~10x the ISCO or
`Rout` below ~120 gravitational radii in practice) was enough to prevent
this on the *unpiled* side, but not once pileup's extra dimensions were
added on top. The actual, load-bearing fix was running each fit in its own
subprocess, so one combination's crash doesn't take the rest of the run
down with it (see `CLAUDE.md` Phase 4) — but the crash itself is a genuine
result: for this pileup-affected spectrum, "just let everything float" is
not merely bad practice, it's not something these optimizers can even
complete. That's about as concrete an argument for the progressive
freezing approach as this project produced.

### 5.4 Formal parameter uncertainties are not a substitute for checking against truth

Sherpa's `covar` (a fast, Hessian/covariance-based error estimate) and
`conf` (a much slower profile-likelihood search that re-optimizes the
remaining free parameters at each trial value) were compared directly on
the Stage B fit of each spectrum. They disagree substantially. For the
unpiled fit, `conf`'s intervals are 2-6x wider than `covar`'s and
noticeably asymmetric (e.g. reflection fraction: `covar` gives +/-0.20,
`conf` gives [-0.69, +0.19]) — `covar`'s local, linearized approximation is
measurably overconfident for a model this non-linear. For the piled fit,
`covar` failed outright: every single parameter came back with an
undefined bound, because the numerical Hessian estimate hit a parameter
boundary or was otherwise singular, even though the fit itself had
converged to a good, physically reasonable answer. `conf` still worked
there, but at real cost — about 2490 seconds versus 3 for `covar`, roughly
an 800x difference, for a 10-parameter model.

There's a second, easy-to-miss trap hiding in the ground-truth comparison
table (`results/report.md`): several formally well-converged fits report
`covar`-based uncertainties equivalent to *hundreds* of standard
deviations away from the true simulated value (e.g. Stage A's `gamma`
comes out roughly 400-sigma from truth). That number is not evidence of a
bug — it's what happens when you have millions of counts: `cstat`'s local
curvature shrinks the *formal statistical* uncertainty far faster than any
real systematic mismatch between the model and the data goes away, so a
fit can be extremely "confident" in a formal sense while still being
substantially biased by model misspecification (the wrong frozen
parameter, an unresolved degeneracy, or the pileup model's own
simplifying assumptions). The practical takeaway, worth internalizing for
any high-count-rate X-ray spectral analysis, not just this one: with this
many counts, statistical error bars stop being the limiting factor almost
immediately, and systematic/modeling uncertainty dominates — quoting a
formal `covar` (or even `conf`) uncertainty without also checking the fit
against an independent constraint (here, ground truth; in a real analysis,
a second instrument, a different energy band, or physical priors) can be
seriously misleading.

### 5.5 How well were the true parameters actually recovered?

At Stage B — the literature-standard, best-fitting configuration for both
spectra — spin, inclination, and iron abundance are recovered within
roughly 10% of their true values for the unpiled spectrum (spin: fitted
0.477 vs. true 0.493; inclination: 32.05 deg vs. 30.88 deg; `Afe`: 2.40 vs.
2.63). Ionization (`logxi`) and reflection fraction are the two parameters
that stay biased by tens of percent in every stage, on both spectra —
`logxi` low by about a third, `refl_frac` high by 30-65%. Since this bias
appears on the *unpiled* spectrum too, where the input model closely
matches the fitting model, it's more likely tied to a genuine
`relxill`/statistics degeneracy (ionization, reflection fraction, and the
overall normalization all trade off against each other in `relxill`'s flux
definition) than to any pileup-specific effect, and is compounded here by
an unresolved ~50x absolute flux-normalization mismatch between this
project's response/model setup and whatever convention the original
simulation pipeline used for `norm` (documented but not fully diagnosed —
see `CLAUDE.md` Phase 3). `refl_frac`'s definition in `relxill` is itself
tied to that same normalization, so its bias should be read with that
caveat attached, not taken as a clean measurement of a real degeneracy.

Comparing piled and unpiled recovered values directly against each other
(not just each against truth) is instructive: spin, inclination, and the
absorbing column come out close to each other between the two spectra
(within a few percent), suggesting `jdpileup` is doing a reasonable job of
undoing pileup's effect on those. Photon index, ionization, and iron
abundance diverge more between the piled and unpiled fits than either does
from the truth on its own — the more plausible interpretation is that this
reflects a genuine, only partially corrected pileup-driven spectral
hardening (piled events preferentially harden the observed continuum
shape, and the fit compensates by shifting continuum/ionization
parameters) rather than pure statistical scatter, given both fits have
enormous count numbers. Full numbers: `results/report.md`, section "Pileup
bias: unpiled vs. piled, Stage B".

## 6. Visual check

Both Stage B fits are visually good across most of the 0.3-10 keV band —
data/model ratios within a few percent through the bulk of the spectrum,
widening toward the low-count edges of the band — despite reduced
statistics well above 1 in both cases, for exactly the reason discussed in
Section 5.4: with millions of counts, `cstat` is sensitive enough to flag
even a few-percent systematic mismatch as statistically significant. See
`results/plots/unpiled_stageB_fit.png` and
`results/plots/piled_stageB_fit.png` (also reproduced live in the
notebook), including a visible instrumental dip near ~2.3 keV that both
fits track reasonably well.

## 7. Takeaways for reproducing or extending this analysis

- Getting `relxill` running inside CIAO's Sherpa (rather than full
  HEASOFT/PyXspec) is possible but genuinely fragile — expect to hit and
  fix source-level build issues, and treat the FFTW3 linking as a
  known weak point if moving to a different machine (see Section 3 and
  `CLAUDE.md` Phase 1).
- Never fit `relxill` with a stochastic/global optimizer over its full
  native parameter ranges without bounding `Rin`/`Rout` to something that
  structurally forbids `Rout <= Rin` — this is not a hypothetical failure
  mode, it reliably crashes the process, not just the fit.
- Run more than one optimizer, especially on pileup-affected data — this
  project found a case (piled spectrum, every stage) where the default
  gradient method was reliably wrong and a derivative-free/global method
  was reliably right.
- Treat `covar` as a cheap sanity check, not a final answer, on a model
  this non-linear — and don't be reassured by a tiny formal error bar on
  a high-count-rate fit; check it against an independent constraint if one
  exists.
- The progressive-freezing approach used here (fit everything, then
  freeze down to the literature-standard set, then test further
  simplifications one at a time) surfaces failure modes — a wrong "typical"
  assumption, a numerically intractable fully-free fit — that jumping
  straight to a final, fully-constrained model would have hidden.
