"""Fix 2025 Maturity in the 2025 source phenotypesTable1.csv: convert offset -> DOY.

The 2025 processing (unlike 2024 and earlier, which store DOY directly) left Maturity in the raw report
format: the per-test anchor CHECK stores an actual DATE per location (e.g. LD15-3818 = '9/21') and every
other entry stores a signed OFFSET (days ± the anchor). When 10_assemble does to_numeric, the anchor dates
parse to NaN and only offsets survive -> the corpus 2025 Maturity is offsets ([-15,+13]) while 2015-2024
are DOY ([~234,292]). This reconstructs DOY = anchor_DOY(Test,City) + offset (anchor rows keep their own
DOY). Lossless: the only unconvertible cells have NO maturity data (already NaN). Re-runnable (reads the
pristine .orig_maturity backup). Anchor per test = the dated row (LD15-3818 UT-IV, IA2102 UT-II, ...)."""
import re
import shutil
import datetime as dt
from pathlib import Path
import pandas as pd

PT = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2025/2025_NUST_Processing/Files4Upload/phenotypesTable1.csv")
BAK = PT.with_suffix(".csv.orig_maturity")

def to_doy(v):
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})\s*$", str(v))
    if not m:
        return None
    try:
        return dt.date(2025, int(m.group(1)), int(m.group(2))).timetuple().tm_yday
    except ValueError:
        return None

def main():
    if not BAK.exists():
        shutil.copy(PT, BAK)
    df = pd.read_csv(BAK, low_memory=False)
    is_mat = df.Phenotype == "Maturity"
    mat = df[is_mat].copy()
    mat["adoy"] = mat.Value.apply(to_doy)                       # dated anchor rows -> DOY
    anchor = mat[mat.adoy.notna()].groupby(["Test", "City"]).adoy.first().to_dict()

    def doy(r):
        if pd.notna(r.adoy):
            return r.adoy                                      # anchor keeps its own DOY
        off = pd.to_numeric(r.Value, errors="coerce")
        a = anchor.get((r.Test, r.City))
        return (a + off) if (pd.notna(off) and a is not None) else None

    mat["doy"] = mat.apply(doy, axis=1)
    df["Value"] = df["Value"].astype(object)                   # str dtype rejects numeric assignment
    df.loc[is_mat, "Value"] = mat["doy"].map(lambda x: str(int(x)) if pd.notna(x) else pd.NA).values
    df.to_csv(PT, index=False)

    v = pd.to_numeric(df.loc[is_mat, "Value"], errors="coerce")
    print(f"2025 Maturity offset->DOY: {is_mat.sum()} rows | converted {v.notna().sum()} to DOY "
          f"(range [{v.min():.0f},{v.max():.0f}], mean {v.mean():.1f}); {v.isna().sum()} stay NaN (no data)")
    anc_var = sorted(set(mat.loc[mat.adoy.notna(), "Strain"].astype(str)))
    print(f"  anchors used: {len(anchor)} (Test,City) cells; anchor varieties = {anc_var[:6]} ...")

if __name__ == "__main__":
    main()
