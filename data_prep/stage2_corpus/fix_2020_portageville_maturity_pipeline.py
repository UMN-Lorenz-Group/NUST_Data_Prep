"""HISTORICAL / SUPERSEDED (2026-07-10): applied + folders since reorganized — do NOT re-run.

Ported the 2020 UT-IV-TM Portageville-Loam Maturity fix (209-231 -> DOY 270-292, anchor LD06-7620=10/2=DOY
276 + offset, 2020 report p.379) — which another thread had applied to the STALE query-portal folder — into
the folder 10_assemble actually reads. At the time there were two folders (stale `_1993_2020_` vs pipeline
`_1993_2022_`); on 2026-07-10 the stale one was retired (now `..._Deprecated`) and the pipeline folder was
renamed `_1993_2022_` -> `_1993_2020_` with its unused 2021 bucket removed, so BOTH paths below are now
outdated. The fix is baked into the current canonical `NUST_Data_1993_2020_fromQueryportal/2020/`."""
import shutil
from pathlib import Path
import pandas as pd

QP = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
FIXED = QP / "NUST_Data_1993_2020_fromQueryportal" / "2020" / "phenotypesTable1.csv"
PIPE = QP / "NUST_Data_1993_2022_fromQueryportal" / "2020" / "phenotypesTable1.csv"
BAK = PIPE.with_suffix(".csv.orig_precleanup")

def main():
    if not BAK.exists():
        shutil.copy(PIPE, BAK)
    fix = pd.read_csv(FIXED, low_memory=False)
    pipe = pd.read_csv(BAK, low_memory=False)
    m = (fix.Test == "UTIVTM") & (fix.Location == "Portageville-Loam") & fix.Maturity.notna()
    corr = {str(r.Strain): r.Maturity for r in fix[m].itertuples(index=False)}
    tgt = (pipe.Test == "UTIVTM") & (pipe.Location == "Portageville-Loam")
    before = pd.to_numeric(pipe.loc[tgt, "Maturity"], errors="coerce")
    n = 0
    for i in pipe[tgt].index:
        s = str(pipe.at[i, "Strain"])
        if s in corr:
            pipe.at[i, "Maturity"] = corr[s]; n += 1
    pipe.to_csv(PIPE, index=False)
    after = pd.to_numeric(pipe.loc[tgt, "Maturity"], errors="coerce")
    print(f"ported {n} UTIVTM Portageville-Loam maturity values into the pipeline folder")
    print(f"  before: range [{before.min():.0f},{before.max():.0f}] median {before.median():.0f}")
    print(f"  after : range [{after.min():.0f},{after.max():.0f}] median {after.median():.0f}  ({len(corr)} corrected values available)")

if __name__ == "__main__":
    main()
