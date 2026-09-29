"""
Phase 3: build the source models for the unpiled and piled spectra, and
implement the Stage A-D parameter-freezing ladder (see CLAUDE.md, Phase 3).

- Unpiled: rsp * (xstbabs.abs_unpiled * xsumrelxill.refl_unpiled)
- Piled:   same source model form (independent parameter instances,
           abs_piled/refl_piled), with a jdpileup model inserted between the
           ARF and RMF via set_pileup_model().

Import build_unpiled_model() / build_piled_model() / apply_stage() from here
rather than duplicating this logic elsewhere.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("RELXILL_TABLE_PATH", str(ROOT / "relxill" / "tables"))

from sherpa.astro import ui
import relxill.ui  # noqa: F401  registers xsumrelxill etc. with Sherpa

from load_data import setup_data

# Ground truth for the target spectrum (see target.py / CLAUDE.md Data
# section). Used only (a) as the Stage D fiducial inclination, and (b) as a
# reference point when reporting results -- never fed in as a fit starting
# value except where a stage explicitly freezes a parameter to it.
from target import GROUND_TRUTH  # noqa: E402

STAGES = ("A", "B", "C", "D")

# relxill's own simulation-default values for the parameters that get
# frozen in stages B/C/D (see lmodel_relxill.dat / CLAUDE.md Data section --
# these are exactly the values ID 1000000081 was simulated with for the
# parameters that were *not* varied).
SIM_DEFAULTS = dict(Rin=-1.0, Rout=400.0, Index1=3.0, Index2=3.0, Rbr=15.0,
                     Ecut=300.0)


# Canonical starting values (relxill/tbabs/jdpileup's own lmodel defaults)
# used to reset every *thawed* parameter before each fit, so that every
# (stage, method) combination starts from the same, reproducible point --
# "a fresh copy of starting parameter values for each optimizer" per
# CLAUDE.md Phase 4. Frozen parameters are left alone (some stages, e.g.
# Stage D's fixed Incl, deliberately freeze a parameter at a non-default
# value, and must not be clobbered back to the generic default here).
RELXILL_START = dict(Index1=3.0, Index2=3.0, Rbr=15.0, a=0.998, Incl=30.0,
                       Rin=-1.0, Rout=400.0, gamma=2.0, logxi=3.1, Afe=1.0,
                       Ecut=300.0, refl_frac=3.0, norm=1.0)
ABS_START = dict(nH=1.0)
PILEUP_START = dict(alpha=0.5, f=0.95)


def reset_thawed_to_start(model, defaults):
    """Set every currently-thawed parameter in `model` back to its entry in
    `defaults` (leaving frozen parameters, and any parameter not in
    `defaults`, untouched).
    """
    for pname, val in defaults.items():
        p = getattr(model, pname, None)
        if p is not None and not p.frozen:
            p.val = val


def build_source_model(suffix):
    """tbabs*relxill for one dataset, with component names suffixed
    ('unpiled'/'piled') so the two datasets carry fully independent
    parameters -- each spectrum is fit on its own (see CLAUDE.md Phase 4/5),
    not jointly, so nothing should be tied between them.
    """
    abs_name = f"abs_{suffix}"
    refl_name = f"refl_{suffix}"
    ui.create_model_component("xstbabs", abs_name)
    ui.create_model_component("xsumrelxill", refl_name)
    absmodel = ui.get_model_component(abs_name)
    relmodel = ui.get_model_component(refl_name)
    return absmodel, relmodel


def apply_stage(relmodel, stage):
    """Apply one of the Stage A-D freezing ladders to a relxill component,
    in place. `z` is always frozen at 0 regardless of stage: this is a
    Galactic/local source, so a free redshift isn't "maximum freedom", it's
    unphysical, and every relxill application in the literature fixes it
    for such sources.
    """
    stage = stage.upper()
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}, expected one of {STAGES}")

    relmodel.z.val = 0.0
    relmodel.z.freeze()

    always_thawed = [relmodel.a, relmodel.Incl, relmodel.gamma,
                      relmodel.logxi, relmodel.Afe, relmodel.refl_frac,
                      relmodel.norm]

    if stage == "A":
        # Stage A: everything free except z.
        for p in always_thawed + [relmodel.Rin, relmodel.Rout,
                                    relmodel.Index1, relmodel.Index2,
                                    relmodel.Rbr, relmodel.Ecut]:
            p.thaw()

        # Safety bound, not a science choice: relxill's C++ code calls a
        # hard, uncatchable abort() (not a Python exception -- it takes the
        # whole interpreter down) if a sampled combination has Rout <= Rin.
        # Rin's native range here is a *sentinel multiplier* of R_ISCO(a)
        # (-1 to -100 means 1x-100x ISCO), which for retrograde spin
        # (a -> -0.998, R_ISCO -> ~9 Rg) can imply a physical radius up to
        # ~900 Rg -- comfortably inside Rout's native 1-1000 range, so a
        # stochastic optimizer (moncar) *will* eventually sample an invalid
        # Rout <= Rin pair and crash the whole fitting run, confirmed
        # empirically. Tighten both ranges enough that this is structurally
        # unreachable (worst case Rin sentinel of 10x ISCO at a=-0.998 is
        # ~90 Rg, safely under Rout's new floor of 120 Rg) while leaving
        # both still genuinely free over a physically generous sub-range --
        # nobody in the literature fits Rin > 10x ISCO or Rout < 120 Rg in
        # practice anyway, so this isn't narrowing Stage A's intent.
        relmodel.Rin.min = -10.0
        relmodel.Rout.min = 120.0
        return

    # Stages B, C, D share this base freeze set (standard literature
    # simplifications for a single CCD-resolution spectrum -- see CLAUDE.md
    # Phase 3 for the reasoning behind each one).
    for pname in ("Rin", "Rout", "Index1", "Index2", "Rbr", "Ecut"):
        p = getattr(relmodel, pname)
        p.val = SIM_DEFAULTS[pname]
        p.freeze()
    for p in always_thawed:
        p.thaw()

    if stage == "B":
        return

    # Stage C: + solar iron abundance.
    relmodel.Afe.val = 1.0
    relmodel.Afe.freeze()

    if stage == "C":
        return

    # Stage D: + fixed inclination (treated as independently known -- a
    # controlled experiment here, using the simulation's ground truth; see
    # the caveat in CLAUDE.md about when this is/isn't a legitimate thing to
    # do in a real analysis).
    relmodel.Incl.val = GROUND_TRUTH["incl"]
    relmodel.Incl.freeze()


def build_unpiled_model(id_unpiled, stage="B"):
    absmodel, relmodel = build_source_model("unpiled")
    apply_stage(relmodel, stage)
    reset_thawed_to_start(absmodel, ABS_START)
    reset_thawed_to_start(relmodel, RELXILL_START)
    ui.set_source(id_unpiled, absmodel * relmodel)
    return absmodel, relmodel


def build_piled_model(id_piled, stage="B"):
    absmodel, relmodel = build_source_model("piled")
    apply_stage(relmodel, stage)
    reset_thawed_to_start(absmodel, ABS_START)
    reset_thawed_to_start(relmodel, RELXILL_START)
    ui.set_source(id_piled, absmodel * relmodel)

    ui.create_model_component("jdpileup", "pileup_piled")
    pmod = ui.get_model_component("pileup_piled")
    # alpha (grade-migration probability) and f (PSF fraction inside the
    # extraction region) are the two parameters normally left free when
    # fitting Chandra ACIS pileup (standard CIAO pileup-thread practice);
    # g0, n, ftime, fracexp, nterms are left at Sherpa's defaults since we
    # have no independent information (real frame time/exposure fraction)
    # to override them with for this simulation.
    pmod.alpha.thaw()
    pmod.f.thaw()
    reset_thawed_to_start(pmod, PILEUP_START)
    ui.set_pileup_model(id_piled, pmod)
    return absmodel, relmodel, pmod


def build_piled_naive_model(id_piled, stage="B"):
    """Fit the *piled* data with the plain (unpiled-style) `tbabs*relxill`
    model -- no `jdpileup` wrap at all. This is the "what if you didn't
    know/correct for pileup" control case: same data as build_piled_model(),
    same model form as build_unpiled_model(), deliberately mismatched. Its
    whole purpose is to quantify, by comparison with build_piled_model()'s
    jdpileup-corrected fit, how much parameter bias pileup introduces when
    it goes unmodeled versus when it's explicitly corrected for -- see
    CLAUDE.md Phase 3/5.
    """
    # Defensive, not redundant: set_source() does NOT clear a pileup model
    # already attached to this dataset id via set_pileup_model() -- it's
    # stored separately from the source model. If build_piled_model() was
    # called on this same id earlier in this session (e.g. scripts that
    # build multiple flagship models in one process, like make_plots.py),
    # skipping this line would silently leave the *old* jdpileup wrap
    # active underneath what's supposed to be the uncorrected model,
    # defeating the entire point of this function. Confirmed by hitting
    # exactly this bug while building results/plots/piled_naive_stageB_fit.png.
    ui.delete_pileup_model(id_piled)

    absmodel, relmodel = build_source_model("piled_naive")
    apply_stage(relmodel, stage)
    reset_thawed_to_start(absmodel, ABS_START)
    reset_thawed_to_start(relmodel, RELXILL_START)
    ui.set_source(id_piled, absmodel * relmodel)
    return absmodel, relmodel


if __name__ == "__main__":
    id_unpiled, id_piled = setup_data()

    for stage in STAGES:
        print(f"\n=== stage {stage} ===")
        abs_u, rel_u = build_unpiled_model(id_unpiled, stage)
        abs_p, rel_p, pmod = build_piled_model(id_piled, stage)

        print("-- unpiled model --")
        print(ui.get_model(id_unpiled))
        print("-- piled model (source) --")
        print(ui.get_source(id_piled))
        print("-- pileup component --")
        print(pmod)

        thawed_u = [p.name for p in rel_u.pars if not p.frozen]
        thawed_p = [p.name for p in rel_p.pars if not p.frozen]
        assert thawed_u == thawed_p, "unpiled/piled relxill freeze state diverged"
        print("thawed relxill params:", thawed_u)
