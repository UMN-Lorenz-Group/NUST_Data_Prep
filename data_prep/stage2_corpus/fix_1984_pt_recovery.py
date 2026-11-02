"""Repair two defects in the applied 1984 PT recovery (reextract_1984_pt_recovered.csv):

1. STATE MISSING on the 2,387 PT-IVA/IVB rows sourced from the Green (extract_ptiv_green.py wrote
   State=""). They are every State-null in the 1984 F4U; without State the location canonicalization
   in 10_assemble cannot key (City, State).
2. STRAIN NAMING off-convention: those Green rows kept the report's MG parenthetical and OCR
   variance, so a check variety fragments into several identities --
       Williams 82 (111) / Willams 82 (111) / Willlams 82 (111)   (one strain, 3 names, in ONE test)
       Elgin (II) / Hodgson 78 (I) / Evans (o) ...  vs the F4U's Elgin / Hodgson78 / Evans
   Check varieties anchor the RGG estimators, so fragmenting them is not cosmetic.

Both are fixed against the same authority the UT extractor uses: the PRE-SWAP F4U vocabulary
(normkey-matched) for names, and the Green headers / sibling PDF rows for State.
"""
import sys, shutil
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from extract_1984_ut_green import load_name_oracle, normkey, FILES, load, parse_loc  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

REC = Path(__file__).parent / "reextract_1984_pt_recovered.csv"
# PT-IVA/IVB Green section (file b) -- header carries 'Carbondale, IL' etc.
PTIV_ROWS = [2242, 2578]

apply = "--apply" in sys.argv
r = pd.read_csv(REC)
print(f"PT recovery: {len(r):,} rows, {r.Strain.nunique()} strains, "
      f"State nulls {r.State.isna().sum():,}")

# ---- 1. City -> State map, from the Green headers + the sibling PDF-sourced rows ----
city_state = {}
rows = load(FILES["b"])
for r0 in PTIV_ROWS:
    hdr = rows[r0 + 1]
    for h in hdr[1:]:
        if not h or "Mean" in str(h) or "Tests" in str(h):
            continue
        city, state, _ = parse_loc(h)
        if city and state:
            city_state.setdefault(city, state)
known = r[r.State.notna()].groupby("City").State.agg(lambda s: s.mode().iloc[0]).to_dict()
for c, s in known.items():
    city_state.setdefault(c, s)
print(f"\nCity->State map ({len(city_state)}): " +
      ", ".join(f"{c}={s}" for c, s in sorted(city_state.items())))

miss = r.State.isna()
r.loc[miss, "State"] = r.loc[miss, "City"].map(city_state)
still = r.State.isna().sum()
print(f"\nState backfilled on {int(miss.sum()):,} rows; remaining nulls: {still}")
if still:
    print("  !! cities with no State: ", sorted(r[r.State.isna()].City.unique()))

# ---- 2. strain names -> established 1984 convention ----
oracle = load_name_oracle()
before = r.Strain.copy()
r["Strain"] = r.Strain.map(lambda s: oracle.get(normkey(s), s))
chg = pd.DataFrame({"from": before, "to": r.Strain})
chg = chg[chg["from"] != chg["to"]].groupby(["from", "to"]).size().reset_index(name="n")
print(f"\nstrain renames ({len(chg)} distinct, {int(chg.n.sum()):,} rows):")
for _, x in chg.iterrows():
    print(f"    {x['from']!r:24} -> {x['to']!r:20} ({x.n} rows)")
unresolved = sorted({s for s in r.Strain.unique() if normkey(s) not in oracle})
if unresolved:
    print(f"\n  !! not in oracle (left as-is): {unresolved}")
print(f"\nstrains: {before.nunique()} -> {r.Strain.nunique()} "
      f"(fragmentation removed: {before.nunique() - r.Strain.nunique()})")

dup = r[r.duplicated(["Test", "Strain", "City", "State", "Phenotype"], keep=False)]
print(f"duplicate keys after merge: {len(dup)}")
if len(dup):
    print(dup.sort_values(["Test", "Strain", "City"]).head(10).to_string(index=False))

if apply:
    bak = REC.with_suffix(".csv.bak_pre_namefix")
    if not bak.exists():
        shutil.copy2(REC, bak)
        print(f"\nbacked up -> {bak.name}")
    r.to_csv(REC, index=False)
    print("APPLIED: reextract_1984_pt_recovered.csv rewritten.")
else:
    print("\n(dry run; pass --apply to write)")
