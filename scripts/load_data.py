"""
Phase 2: load the unpiled/piled PHA spectra (written by extract_spectrum.py)
into a Sherpa session, with their RMF/ARF, and set up the fit statistic and
energy range common to both.

Import `setup_data()` from this module rather than duplicating this logic in
the notebook / fitting scripts.
"""
from pathlib import Path

from sherpa.astro import ui

ROOT = Path(__file__).resolve().parent.parent

from target import TARGET_ID  # noqa: E402  (env var TARGET_ID, see target.py)
UNPILED_PHA = ROOT / "data" / "unpiled" / f"id{TARGET_ID}_unpiled.pha"
PILED_PHA = ROOT / "data" / "piled" / f"id{TARGET_ID}_piled.pha"

FIT_ELO, FIT_EHI = 0.3, 10.0  # keV - matches the RMF/ARF energy grid exactly
STATISTIC = "cstat"  # Poisson counts, no background spectrum -> cstat (not wstat)


def pha_paths(target_id=TARGET_ID):
    return (ROOT / "data" / "unpiled" / f"id{target_id}_unpiled.pha",
            ROOT / "data" / "piled" / f"id{target_id}_piled.pha")


def setup_data(id_unpiled="unpiled", id_piled="piled", target_id=None):
    """Load both spectra, notice the common fit range, set the statistic.

    `target_id` defaults to TARGET_ID (env var, see target.py); pass it
    explicitly to load a different simulation in the same session (e.g.
    the notebook's second-spectrum section).

    Returns the two Sherpa dataset ids used.
    """
    unpiled_pha, piled_pha = pha_paths(target_id or TARGET_ID)
    ui.load_pha(id_unpiled, str(unpiled_pha))
    ui.load_pha(id_piled, str(piled_pha))

    for idname in (id_unpiled, id_piled):
        ui.notice_id(idname, FIT_ELO, FIT_EHI)

    ui.set_stat(STATISTIC)

    return id_unpiled, id_piled


if __name__ == "__main__":
    ids = setup_data()
    for idname in ids:
        d = ui.get_data(idname)
        print(idname, "exposure", d.exposure, "counts (noticed)",
              d.get_dep(filter=True).sum())
    print("statistic:", ui.get_stat_name())
