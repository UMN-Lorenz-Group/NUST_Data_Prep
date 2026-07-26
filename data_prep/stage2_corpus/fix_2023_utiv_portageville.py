"""Fix the 2023 UT-IV Portageville Clay/Loam collapse in the 2023 source phenotypesTable1.csv.

The 2023 processing merged the two distinct Portageville MO plots (Clay soil / Loam soil) into one
'Portageville-Loam' label -> duplicate (Strain,Test,Phenotype) keys. The authoritative UTPT Report XLSX
has them as separate Clay/Loam columns. This splits them back, per the report + the established pattern
(2021/2022 and the report agree):
  - 7 agronomic traits (Yield/YieldRank/Maturity/Lodging/Height/SeedSize/SeedQuality): genuinely distinct
    two plots -> relabel one row to Portageville-Clay (matched to the report Clay value).
  - Protein/Oil: measured at Loam only (Clay blank in report + 0 Clay strains in 2021/2022) -> keep one
    Loam row, drop the spurious identical duplicate.
  - 9 fatty-acid/sugar traits: TRAITED has distinct Clay/Loam in the report 'Seed Traits' sheet -> set the
    two rows to the report Clay/Loam values. CONVENTIONAL has no per-plot fatty-acid source (no Seed Traits
    sheet) -> Loam-only, drop the duplicate.

Re-runnable: reads the pristine .orig_preclay backup if present. Report reference =
portageville_2023_utiv_clay_loam.csv (built by scratchpad/extract_2023_utiv_portageville.py)."""
import re
import shutil
from pathlib import Path
import numpy as np
import pandas as pd

def norm(s):
    """Normalize a strain name for matching: strip ALL trailing ' (X)' suffixes ((SCN) (E), (IV), (L)...)."""
    return re.sub(r"(\s*\([^)]*\))+\s*$", "", str(s)).strip()

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
PT = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/2023/2023_NUST_Processing/phenotypesTable1.csv")
BAK = PT.with_suffix(".csv.orig_preclay")
REF = REPO / "data_prep/stage2_corpus/portageville_2023_utiv_clay_loam.csv"

AGRO = {"YieldBuA", "YieldRank", "Maturity", "Lodging", "Height", "SeedSize", "SeedQuality"}
LOAM_ONLY = {"Protein", "Oil"}
FATTY = {"SeedPalmiticAcid", "SeedStearicAcid", "SeedOleicAcid", "SeedLinoleicAcid", "SeedLinolenicAcid",
         "SeedSucrose", "SeedRaffinose", "SeedStachyose", "SeedSugarTotal"}
CLAY, LOAM = "Portageville-Clay", "Portageville-Loam"

def main():
    if not BAK.exists():
        shutil.copy(PT, BAK)
    pt = pd.read_csv(BAK, low_memory=False)
    ref = pd.read_csv(REF)
    R = {(r.Variant, norm(r.Strain), r.Phenotype): (r.clay, r.loam) for r in ref.itertuples(index=False)}

    is_tgt = (pt.Year == 2023) & (pt.Test.isin(["UTIV", "UTIVTM"])) & (pt.City == LOAM)
    tgt, rest = pt[is_tgt].copy(), pt[~is_tgt].copy()
    out, stats = [], {"clay_split": 0, "loam_only_drop": 0, "fatty_recovered": 0, "kept_asis": 0}

    def mk(template, city, value):
        r = dict(template); r["City"] = city; r["Value"] = value; return r

    for (test, strain, ph), g in tgt.groupby(["Test", "Strain", "Phenotype"], sort=False):
        variant = "Conventional" if test == "UTIV" else "Traited"
        tmpl = g.iloc[0].to_dict()
        clay, loam = R.get((variant, norm(strain), ph), (np.nan, np.nan))
        vals = sorted(set(round(v, 6) for v in g["Value"].dropna()))   # corpus DISTINCT REAL values (dedup + drop NaN)
        if ph in AGRO:
            # KEEP corpus values (correct, incl. Maturity DOY); use report ONLY to decide which is Clay.
            if len(vals) >= 2:
                clay_smaller = (clay <= loam) if (pd.notna(clay) and pd.notna(loam)) else True
                cval, lval = (vals[0], vals[-1]) if clay_smaller else (vals[-1], vals[0])
                out += [mk(tmpl, CLAY, cval), mk(tmpl, LOAM, lval)]; stats["clay_split"] += 1
            elif len(vals) == 1:
                out.append(mk(tmpl, LOAM, vals[0])); stats["loam_only_drop"] += 1
            # else 0 real -> drop
        elif ph in FATTY and variant == "Traited" and pd.notna(clay) and pd.notna(loam):
            # corpus fatty exists only at Loam-labeled rows; report has the distinct Clay/Loam (same % scale)
            out += [mk(tmpl, CLAY, clay), mk(tmpl, LOAM, loam)]; stats["fatty_recovered"] += 1
        else:                                               # Protein/Oil, Conv fatty, Traited fatty w/o report
            if vals:
                out.append(mk(tmpl, LOAM, vals[-1])); stats["loam_only_drop"] += 1
            else:
                stats["dropped_nan"] = stats.get("dropped_nan", 0) + 1   # all-NaN placeholder -> genuine absence, drop

    fixed = pd.concat([rest, pd.DataFrame(out)], ignore_index=True)
    fixed.to_csv(PT, index=False)
    print(f"2023 UT-IV Portageville fix: {len(pt)} -> {len(fixed)} rows")
    print(f"  agronomic Clay/Loam split: {stats['clay_split']} keys")
    print(f"  Traited fatty Clay/Loam recovered: {stats['fatty_recovered']} keys")
    print(f"  Loam-only (kept 1 real, dropped dup): {stats['loam_only_drop']} keys")
    print(f"  all-NaN placeholder dropped (no data): {stats.get('dropped_nan',0)} keys | kept as-is: {stats['kept_asis']}")
    chk = fixed[(fixed.Year == 2023) & (fixed.Test.isin(["UTIV", "UTIVTM"])) & (fixed.City.str.startswith("Portage", na=False))]
    print("  post-fix Portageville labels:", chk.City.value_counts().to_dict())
    d = chk.groupby(["Test", "Strain", "Phenotype", "City"]).size()
    print("  any remaining duplicate (Test,Strain,Phenotype,City) keys:", int((d > 1).sum()))

def fix_wide():
    """Rebuild the collapsed Portageville rows in phenotypesTable1_wideFmt.csv FROM the already-fixed long
    file (single source of truth -> guaranteed consistent Clay/Loam split)."""
    WPT = PT.parent / "phenotypesTable1_wideFmt.csv"
    WBAK = WPT.with_suffix(".csv.orig_preclay")
    if not WBAK.exists():
        shutil.copy(WPT, WBAK)
    w = pd.read_csv(WBAK, low_memory=False)
    lng = pd.read_csv(PT, low_memory=False)                # the fixed long file
    sub = lng[(lng.Year == 2023) & (lng.Test.isin(["UTIV", "UTIVTM"])) & (lng.City.str.startswith("Portage", na=False))]
    idx = ["Year", "Test", "City", "State", "Strain", "OriginalStrain"]
    wide_new = (sub.pivot_table(index=idx, columns="Phenotype", values="Value", aggfunc="first")
                .reset_index().rename(columns={"City": "Location"}))
    wide_new = wide_new.reindex(columns=w.columns)         # match wide schema/order (missing traits -> NaN)
    is_old = (w.Year == 2023) & (w.Test.isin(["UTIV", "UTIVTM"])) & (w.Location.str.startswith("Portage", na=False))
    out = pd.concat([w[~is_old], wide_new], ignore_index=True)
    out.to_csv(WPT, index=False)
    p = out[(out.Year == 2023) & (out.Test.isin(["UTIV", "UTIVTM"])) & (out.Location.str.startswith("Portage", na=False))]
    print(f"\nphenotypesTable1_wideFmt.csv: {len(w)} -> {len(out)} rows | Portageville labels: {p.Location.value_counts().to_dict()}")
    print("  dup (Test,Strain,Location) keys:", int((p.groupby(['Test','Strain','Location']).size() > 1).sum()))

if __name__ == "__main__":
    main()
    fix_wide()
