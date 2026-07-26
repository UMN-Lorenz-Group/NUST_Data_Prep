"""Swap the scrambled 1984 Preliminary-test rows in the 1984 F4U phenotypesTable1.csv with the clean
PDF re-extraction (reextract_1984_pt_recovered.csv). Backs up first; --apply to write."""
import sys, shutil
from pathlib import Path
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")

F4U = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
           "NUST_Historical_Data_1941_1988/1984_Processing/Files4Upload/phenotypesTable1.csv")
REC = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/data_prep/stage2_corpus/reextract_1984_pt_recovered.csv")
PT_LABELS = {"PT-I", "PT-IIA", "PT-IIB", "PT-IIIA", "PT-IIIB", "PT-IVA", "PT-IVB"}
UNIT_MAP = {"DOY": "date", "in": "inches", "score": "score", "g/100": "g/100", "%": "%", "bu/a": "bu/a"}

def fmt(v):
    return str(int(v)) if float(v) == int(v) else f"{v:g}"

apply = "--apply" in sys.argv
f = pd.read_csv(F4U, low_memory=False)
print(f"F4U rows before: {len(f)}")
mask = (f.Year == 1984) & (f.Test.isin(PT_LABELS))
print(f"scrambled 1984 PT rows to REMOVE: {mask.sum()}  (tests: {sorted(f[mask].Test.unique())})")
kept = f[~mask].copy()

rec = pd.read_csv(REC)
new = pd.DataFrame({
    "Strain": rec.Strain, "Year": rec.Year, "Test": rec.Test, "City": rec.City,
    "State": rec.State, "Phenotype": rec.Phenotype,
    "Value": rec.Value_num.map(fmt), "Units": rec.Units.map(lambda u: UNIT_MAP.get(u, u)),
})
print(f"clean recovered rows to ADD: {len(new)}  (tests: {sorted(new.Test.unique())}, "
      f"phenos: {sorted(new.Phenotype.unique())})")
out = pd.concat([kept, new[f.columns]], ignore_index=True)
print(f"F4U rows after: {len(out)}  (delta {len(out)-len(f)})")

# sanity: no fake Group-III/IV locs remain in the new PT rows
fake = {"Manhattan","Stuart","Belleville","Eldorado","Girard","Greenfield","Ottumwa","Queenstown","Sullivan","Topeka","Columbia","Carbondale","Lexington"}
npt = out[(out.Year==1984) & (out.Test.isin(PT_LABELS))]
badloc = sorted(set(npt.City) & fake)
print(f"fake locs in new PT block: {badloc if badloc else 'NONE'}")
print(f"new PT block: {npt.Test.nunique()} tests, {npt.Strain.nunique()} strains, {len(npt)} rows")

if apply:
    bak = F4U.with_suffix(".csv.bak_pre_1984pt_swap")
    if not bak.exists():
        shutil.copy2(F4U, bak); print(f"backed up -> {bak.name}")
    out.to_csv(F4U, index=False)
    print("APPLIED: phenotypesTable1.csv rewritten.")
else:
    print("(dry run; pass --apply to write)")
