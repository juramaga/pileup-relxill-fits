# Fitting relativistic disk reflection through pileup: a Chandra/relxill case study

*A didactic walkthrough of fitting a MARX-simulated Chandra spectrum with
`relxill` in Sherpa, with and without photon pileup, comparing optimizers
and freezing strategies, and — the centerpiece of this update — comparing
what happens when pileup is properly corrected for versus silently
ignored. Companion documents: `CLAUDE.md` (full decision log and
methodology, Phases 1-5), `results/report.md` (the complete numeric
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

Three model/spectrum cases are fit and compared throughout this project:

1. **`unpiled`** — the pileup-free spectrum, fit with `tbabs * relxill`
   (interstellar absorption times the reflection model).
2. **`piled`** — the pileup-affected spectrum, with the same source model
   additionally wrapped in Sherpa's `jdpileup` model (implementing the
   Davis 2001 ACIS pileup algorithm), inserted by Sherpa between the
   source model and the RMF — physically correct, since pileup is a
   focal-plane effect that happens before the detector's energy
   redistribution, not after. Of `jdpileup`'s parameters, `alpha` (the
   probability that a piled event survives Chandra's onboard grade filter
   as a "good" event) and `f` (the fraction of the source's PSF falling
   inside the extraction region, which controls how much of the flux is
   even subject to pileup) were left free to fit; the frame time, exposure
   fraction, and a couple of other parameters were left at Sherpa's
   standard ACIS defaults, since no real event-file header exists for this
   simulation to read them from — a modeling assumption worth remembering
   when judging this fit's absolute accuracy.
3. **`piled_naive`** — the *same* pileup-affected data as `piled`, fit with
   the plain, unpiled-style `tbabs * relxill` model and **no** pileup
   correction at all. This third case represents the mistake an analyst
   makes by not realizing (or not bothering to correct for) pileup, and
   was added specifically to answer a question the first two cases alone
   can't: *how much does correcting for pileup actually change the
   science conclusions, versus just ignoring it?* Section 5.6 has the
   answer, and it is more sobering than one might hope.

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

The complete numeric results for all 36 (spectrum/model-case x stage x
method) combinations are in `results/report.md` and
`results/fit_metrics.csv`; this section pulls out the findings that
actually matter for interpreting the science, and for anyone repeating an
analysis like this one.

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

This is corroborated directly by the third (`piled_naive`) case: fitting
the *same* piled data with `jdpileup` removed, `levmar` no longer gets
stuck (Stage B: cstat~1046, essentially tied with `neldermead`'s ~1006) —
it's specifically the combination of piled data *and* `jdpileup`'s own
nonlinear machinery that trips up the gradient method, not the piled data
on its own.

### 5.3 Stage A is not just poorly constrained for the piled spectrum — it's uncomputable, regardless of whether pileup is even in the model

All three optimizers *crashed* — not converged poorly, actually crashed the
Python process — when given the piled spectrum's full Stage A freedom.
This traces back to the hard-abort behavior described in Section 3: with
`relxill`'s native `Rin` range (equivalent to 1x-100x the ISCO radius) and
`Rout` range (1-1000 gravitational radii) both fully open, all three
optimizers eventually sampled a combination where the sentinel-encoded
inner radius exceeded the outer radius, and the whole process died rather
than the fit merely failing. Tightening those bounds (still leaving both
genuinely free over a physically generous sub-range — nobody fits `Rin`
beyond ~10x the ISCO or `Rout` below ~120 gravitational radii in practice)
was enough to prevent this on the *unpiled* side, but not on the piled
side.

The original version of this analysis (before the `piled_naive` case was
added) attributed this to `jdpileup`'s extra free parameters (`alpha`,
`f`) pushing the fit into a larger, more dangerous parameter space. That
turned out to be an incomplete explanation: `piled_naive` has exactly the
same 13 free parameters as `unpiled` at Stage A (no pileup parameters at
all), and it crashes too, on all three optimizers, on the same piled data.
The correct generalization is that **the piled data's own shape** — not
the pileup *model's* extra parameters — is what sends the same
13-parameter Stage A search into `Rout <= Rin` territory that the unpiled
data never reaches from the same starting point and bounds. The actual,
load-bearing fix was running each fit in its own subprocess, so one
combination's crash doesn't take the rest of the run down with it (see
`CLAUDE.md` Phase 4) — but the crash itself is a genuine, and now better
understood, result: for this fainter, differently-shaped spectrum, "just
let everything float" is not merely bad practice, it's not something these
optimizers can even complete, with or without pileup in the model. That's
about as concrete an argument for the progressive freezing approach as
this project produced — and a caution against assuming a fully-free fit
that worked on one spectrum will work on a different one, even a
nominally similar-looking spectrum of the same source.

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
an 800x difference, for a 10-parameter model. `piled_naive`'s Stage B fit
shows the identical pattern (`covar` all-undefined, `conf` ~1250x slower
than `covar` but usable) and produces a strikingly asymmetric `refl_frac`
interval, [-1.78, +29.5] — a lopsided uncertainty that is itself a symptom
of just how poorly determined that parameter is once pileup goes
uncorrected.

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

Section 5.6 below extends this comparison with the third (`piled_naive`)
case, which is where the more striking findings are.

### 5.6 Does correcting for pileup with jdpileup actually help? A three-way comparison

This is the comparison this project was extended to make, and the
headline numbers are worth putting side by side (all Stage B, each case's
own best formally-converged fit; full table in `results/report.md`):

| Parameter | Ground truth | `unpiled` | `piled` (corrected) | `piled_naive` (uncorrected) |
|---|---|---|---|---|
| spin (`a`) | 0.493 | 0.477 (-3.2%) | 0.866 (+75.7%) | 0.876 (+77.7%) |
| Incl (deg) | 30.88 | 32.05 (+3.8%) | 31.60 (+2.3%) | 31.50 (+2.0%) |
| `gamma` | 1.331 | 1.406 (+5.7%) | 1.000 (-24.8%) | 1.227 (-7.8%) |
| `logxi` | 1.497 | 1.007 (-32.7%) | 2.301 (+53.8%) | 1.208 (-19.3%) |
| `Afe` | 2.631 | 2.401 (-8.7%) | 3.233 (+22.9%) | 2.211 (-16.0%) |
| `refl_frac` | 14.315 | 23.64 (+65.1%) | 19.19 (+34.0%) | 33.52 (+134.2%) |
| `nH` | 0.650 | 0.587 (-9.6%) | 0.694 (+6.9%) | 0.691 (+6.4%) |

Four findings jump out, and not all of them are comfortable ones:

**A good fit statistic does not tell you whether pileup was handled
correctly.** `piled_naive`'s best Stage B fit (cstat~1005.9, reduced
stat~1.53) is statistically at least as good as — arguably marginally
better than — the properly `jdpileup`-corrected `piled` fit (cstat~1039.9,
reduced stat~1.59), despite using the structurally wrong model. Figure
comparison in Section 6 shows why: the two fits are visually
indistinguishable. `relxill` has enough free parameters (`refl_frac`
especially) to partially absorb pileup's spectral distortion and produce
an equally clean-looking fit to physically wrong parameter values. If the
only check available is "does the fit look good and is reduced stat
reasonable," this project would have no way to tell that the
`piled_naive` fit is any less trustworthy than the properly-corrected one.

**Correcting for pileup does not rescue the spin measurement, at least not
here.** Spin comes out biased ~76-78% high in *both* piled cases —
corrected and uncorrected alike — while the unpiled fit is within a few
percent of truth. Whatever `jdpileup` is doing to compensate for pileup's
effect on the overall spectral shape, it is not fixing whatever is driving
the spin measurement so far off. This is arguably the most important
result of the whole exercise for anyone using `relxill` on a Chandra
spectrum with any meaningful pileup: don't assume that adding `jdpileup`
to the model is sufficient to trust the recovered spin.

**`refl_frac` is the parameter most sensitive to *whether* pileup was
corrected for, even though it doesn't track spin's failure mode.** It's
biased high in all three cases (entangled with the `norm`
scale-convention issue from Section 5.5/`CLAUDE.md` Phase 3), but far more
extremely so when pileup is left uncorrected (+134% vs. +34% corrected vs.
+65% unpiled) — consistent with the fit inflating reflection fraction to
make up for flux that `jdpileup` would otherwise have properly accounted
for. In a real analysis without ground truth to check against, an
implausibly large `refl_frac` (well above the physically expected ceiling
of ~a few for a simple lamp-post-like geometry) is a plausible warning
sign that pileup hasn't been handled.

**Not every parameter gets worse without correction — `gamma` and
`logxi` are actually closer to the unpiled fit's own bias in the
*uncorrected* fit than in the corrected one.** This is not an argument for
skipping pileup correction (the fit-quality and spin points above say
otherwise, strongly) — it's a reminder that "correcting" an instrumental
effect with an imperfect model doesn't move every downstream parameter
uniformly closer to the truth, and a partial correction can occasionally
overshoot on some parameters while undershooting on others.

## 6. Visual check

All three Stage B fits are visually good across most of the 0.3-10 keV
band — data/model ratios within a few percent through the bulk of the
spectrum, widening toward the low-count edges of the band — despite
reduced statistics well above 1 in every case, for exactly the reason
discussed in Section 5.4: with millions of counts, `cstat` is sensitive
enough to flag even a few-percent systematic mismatch as statistically
significant. See `results/plots/unpiled_stageB_fit.png`,
`results/plots/piled_stageB_fit.png`, and
`results/plots/piled_naive_stageB_fit.png` (all three reproduced live,
side by side, in the notebook), including a visible instrumental dip near
~2.3 keV that all three fits track reasonably well. As Section 5.6
discusses, the `piled` and `piled_naive` panels are essentially
indistinguishable by eye — the whole point of that comparison.

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
- **When feasible, deliberately fit the uncorrected model alongside the
  corrected one.** A good `cstat`/reduced-stat value on a pileup-corrected
  fit is not, by itself, evidence that the correction worked — this
  project's `piled_naive` control fit was statistically indistinguishable
  from the properly-corrected fit while being severely biased in spin and
  reflection fraction. Where an independent constraint (ground truth here;
  in practice, a lower-pileup epoch of the same source, a different
  instrument, or a physically-motivated prior) is available, use it to
  check the corrected fit rather than trusting the correction on faith.
- Watch for state that persists across model rebuilds within a single
  Sherpa session — `set_pileup_model()` attaches to the *dataset*, not the
  source model, and survives a later `set_source()` call. Building an
  uncorrected control model in the same session as a pileup-corrected one
  (exactly the comparison recommended above) will silently produce the
  wrong result unless the old pileup model is explicitly deleted first
  (`delete_pileup_model()`) — this project hit that bug once, while making
  the diagnostic plots, before catching it from an implausible-looking
  ratio plot.
