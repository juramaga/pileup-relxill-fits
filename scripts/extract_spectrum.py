"""
Extract one simulated spectrum (by ID) from the big MARX data table
(v0017_800ks_cspec_datatable.fits, one row per simulation) and write it out
as two standard OGIP type-I PHA files (unpiled, piled), pointing at the
shared RMF/ARF in ../responses/.

Usage: python extract_spectrum.py [ID]   (default ID: 1000000081)
"""
import sys
import csv
from pathlib import Path

import numpy as np
from astropy.io import fits

ROOT = Path(__file__).resolve().parent.parent
DATATABLE = ROOT / "v0017_800ks_cspec_datatable.fits"
INDEX_CSV = ROOT / "v0017_800ks_index.csv"
RMF = ROOT / "responses" / "c07_x222_y0531.rmf"
ARF = ROOT / "responses" / "id1000000000_arf.fits"

TARGET_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1000000081


def find_row(target_id: int) -> tuple[int, dict]:
    with open(INDEX_CSV) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if int(row["ID"]) == target_id:
                return i, row
    raise ValueError(f"ID {target_id} not found in {INDEX_CSV}")


def write_pha(outpath: Path, counts: np.ndarray, exposure: float, desc: str):
    nchan = len(counts)
    channel = np.arange(1, nchan + 1, dtype=np.int32)

    cols = fits.ColDefs([
        fits.Column(name="CHANNEL", format="J", array=channel),
        fits.Column(name="COUNTS", format="J", array=counts.astype(np.int32)),
    ])
    hdu = fits.BinTableHDU.from_columns(cols, name="SPECTRUM")

    hdr = hdu.header
    hdr["EXTNAME"] = "SPECTRUM"
    hdr["TELESCOP"] = "CHANDRA"
    hdr["INSTRUME"] = "ACIS"
    hdr["FILTER"] = "NONE"
    hdr["CHANTYPE"] = "PI"
    hdr["DETCHANS"] = nchan
    hdr["HDUCLASS"] = "OGIP"
    hdr["HDUCLAS1"] = "SPECTRUM"
    hdr["HDUCLAS2"] = "TOTAL"
    hdr["HDUCLAS3"] = "COUNT"
    hdr["HDUVERS"] = "1.2.1"
    hdr["POISSERR"] = True
    hdr["EXPOSURE"] = float(exposure)
    hdr["AREASCAL"] = 1.0
    hdr["BACKSCAL"] = 1.0
    hdr["CORRSCAL"] = 0.0
    hdr["BACKFILE"] = "NONE"
    hdr["CORRFILE"] = "NONE"
    hdr["RESPFILE"] = str(RMF)
    hdr["ANCRFILE"] = str(ARF)
    hdr["SYS_ERR"] = 0.0
    hdr["GROUPING"] = 0
    hdr["QUALITY"] = 0
    hdr["DESC"] = desc

    primary = fits.PrimaryHDU()
    hdul = fits.HDUList([primary, hdu])
    hdul.writeto(outpath, overwrite=True)
    print(f"wrote {outpath}  (counts sum={counts.sum():.0f}, exposure={exposure})")


def main():
    row_idx, row = find_row(TARGET_ID)
    print(f"ID {TARGET_ID} -> row index {row_idx} in data table")
    assert row_idx == TARGET_ID - 1_000_000_000, (
        "row index no longer matches the simple ID offset - check mapping!"
    )

    exposure = float(row["Exposure"])

    with fits.open(DATATABLE) as hdul:
        unpiled = hdul["MARX_UNPILED"].data[row_idx].astype(np.float64)
        piled = hdul["MARX_PILED"].data[row_idx].astype(np.float64)

    # sanity check against the index CSV's reported rates
    exp_unpiled = float(row["Total unpiled count rate from MARX [counts/s]"]) * exposure
    exp_piled = float(row["Total piled-up count rate from MARX [counts/s]"]) * exposure
    print(f"unpiled: sum={unpiled.sum():.0f} vs rate*exposure={exp_unpiled:.0f}")
    print(f"piled:   sum={piled.sum():.0f} vs rate*exposure={exp_piled:.0f}")

    write_pha(
        ROOT / "data" / "unpiled" / f"id{TARGET_ID}_unpiled.pha",
        unpiled, exposure, f"MARX unpiled spectrum, ID={TARGET_ID}",
    )
    write_pha(
        ROOT / "data" / "piled" / f"id{TARGET_ID}_piled.pha",
        piled, exposure, f"MARX piled-up spectrum, ID={TARGET_ID}",
    )

    print("\nGround truth parameters for this ID:")
    for key in ["Afe", "gamma", "incl", "logxi", "nH", "norm", "refl_frac", "spin"]:
        print(f"  {key:10s} = {row['(Parameter) ' + key]}")


if __name__ == "__main__":
    main()
