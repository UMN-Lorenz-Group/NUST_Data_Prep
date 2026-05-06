"""
Phase 3 integrity check: patched combined CSV vs Files4Upload phenotypesTable.
Verifies that every patch from patch_phenotypes_1980.py flowed through the
R bridge unchanged.  Reports any mismatches or missing rows.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from pathlib import Path

SRC  = Path("output_1980/validated/combined_1980_phenotypesTable_approved.csv")
DEST = Path("C:/Users/ivanv/Desktop/UMN_Projects/NUST_Projects/NUST_Data/NUST_Historical_Data/1980_Processing/Files4Upload/phenotypesTable1.csv")

PATCHES = [
    ("UT-00","Fargo","Maple Presto","Height",20),
    ("UT-00","Fargo","OT80-1","Height",26),
    ("UT-00","Fargo","OT80-3","Height",25),
    ("UT-00","Fargo","Portage (00)","Height",27),
    ("UT-00","Morden","Clay (0)","Height",26),
    ("UT-00","Morden","M71-148","Height",26),
    ("UT-00","Morden","Maple Arrow","Height",28),
    ("UT-00","Morden","Maple Presto","Height",22),
    ("UT-00","Morden","McCall","Height",27),
    ("UT-00","Morden","OT80-1","Height",24),
    ("UT-00","Morden","OT80-2","Height",23),
    ("UT-00","Morden","OT80-3","Height",24),
    ("UT-00","Morden","Portage (00)","Height",24),
    ("UT-00","Ashland","Maple Presto","SeedQuality",3.5),
    ("UT-00","Rosemount","OT80-1","SeedQuality",2.0),
    ("UT-00","Fargo","Maple Presto","SeedSize",13.3),
    ("PT-II","Urbana","A75D29","YieldBuA",31.9),
    ("PT-II","Urbana","Century","YieldBuA",43.8),
    ("PT-II","Lafayette","Gnome","YieldBuA",51.1),
    ("PT-II","Urbana","Gnome","YieldBuA",49.5),
    ("PT-II","Urbana","Hardin (I)","YieldBuA",41.9),
    ("PT-II","Lafayette","Pella (III)","YieldBuA",57.1),
    ("PT-II","Urbana","Pella (III)","YieldBuA",45.3),
    ("PT-III","Ottumwa","HC76-3863","Oil",22.9),
    ("PT-III","Lafayette","L77-443","Lodging",1.8),
    ("PT-III","Ottumwa","L78-709","Height",33),
    ("PT-III","Lafayette","L78-709","Lodging",2.0),
    ("UT-I","Lafayette","Evans (0)","Height",36),
    ("UT-I","Lafayette","Hardin (I)","Height",37),
    ("UT-I","Lafayette","M72-3","Height",29),
    ("UT-I","Lafayette","Hardin (I)","Lodging",1.2),
    ("UT-I","Lafayette","Hodgson 78 (I)","Lodging",1.9),
    ("UT-I","Lafayette","Corsoy 79 (II)","SeedQuality",2.0),
    ("UT-I","Lafayette","Evans (0)","SeedQuality",3.0),
    ("UT-I","Lafayette","Hodgson 78 (I)","SeedQuality",2.0),
    ("UT-I","Lafayette","M71-80","SeedQuality",1.8),
    ("UT-I","Lafayette","M75-2","SeedQuality",1.6),
    ("UT-I","Lafayette","Hardin (I)","SeedSize",14.9),
    ("UT-III","S. Charleston","A78-227012","Lodging",2.1),
    ("UT-III","S. Charleston","A78-321011","Lodging",1.7),
    ("UT-III","S. Charleston","A78-322024","Lodging",2.7),
    ("UT-III","S. Charleston","A78-324002","Lodging",2.7),
    ("UT-III","S. Charleston","A78-325028","Lodging",3.3),
    ("UT-III","S. Charleston","A78-326032","Lodging",3.1),
    ("UT-III","S. Charleston","BSR 302","Lodging",3.2),
    ("UT-III","S. Charleston","Century (II)","Lodging",1.8),
    ("UT-III","S. Charleston","Cumberland (III)","Lodging",2.0),
    ("UT-III","S. Charleston","HC76-4030","Lodging",1.0),
    ("UT-III","S. Charleston","HW74-3384 Sprite","Lodging",1.1),
    ("UT-III","S. Charleston","HW74-3385","Lodging",1.2),
    ("UT-III","S. Charleston","L24A","Lodging",2.1),
    ("UT-III","S. Charleston","L25A","Lodging",2.5),
    ("UT-III","S. Charleston","L26","Lodging",2.4),
    ("UT-III","S. Charleston","L75-8121","Lodging",2.6),
    ("UT-III","S. Charleston","Pella","Lodging",1.9),
    ("UT-III","S. Charleston","U36276","Lodging",1.4),
    ("UT-III","S. Charleston","Union (IV)","Lodging",2.9),
    ("UT-III","S. Charleston","Williams 79","Lodging",2.5),
    ("UT-IV","Manhattan","Franklin","Lodging",1.0),
    ("UT-IV","Manhattan","K1033","Lodging",1.0),
    ("UT-IV","Manhattan","K1041","Lodging",1.0),
    ("UT-IV","Manhattan","K1044","Lodging",1.0),
    ("UT-IV","Manhattan","K1045","Lodging",1.0),
    ("UT-IV","Manhattan","K1046","Lodging",1.0),
    ("UT-IV","Manhattan","Ky75-146-74","Lodging",1.0),
    ("UT-IV","Manhattan","L73-318","Lodging",1.0),
    ("UT-IV","Manhattan","L74L-125","Lodging",1.0),
    ("UT-IV","Manhattan","L74L-358","Lodging",1.0),
    ("UT-IV","Manhattan","Union (IV)","Lodging",1.0),
    ("UT-IV","Manhattan","Williams79 (III)","Lodging",1.0),
    ("UT-IV","Powhattan","HC76-3840","YieldBuA",16.6),
    ("UT-IV","Powhattan","K1033","YieldBuA",16.4),
    ("UT-IV","Powhattan","K1041","YieldBuA",13.6),
    ("UT-IV","Powhattan","Ky75-146-74","YieldBuA",19.6),
    ("UT-IV","Powhattan","Williams79 (III)","YieldBuA",13.5),
    ("UT-II","Harrow","A77-211021","YieldBuA",55.4),
    ("UT-II","Harrow","A78-122031","YieldBuA",60.4),
    ("UT-II","Harrow","Pella (III)","YieldBuA",51.6),
    ("UT-0","Elora","M72-24","Protein",43.2),
    ("UT-I","Oakes","Evans (0)","SeedQuality",2.5),
    ("UT-I","Ridgetown","Hardin (I)","Protein",41.7),
    ("UT-I","Lamberton","A78-121014","SeedSize",19.6),
    ("UT-I","Dekalb","Evans (0)","YieldRank",9),
    ("UT-I","Dekalb","M75-2","YieldRank",7),
    ("UT-II","Ridgetown","A78-227015","Lodging",1.2),
    ("UT-II","Ridgetown","A78-227016","Lodging",1.8),
    ("UT-II","Ames","A78-122028","Protein",40.9),
    ("UT-II","Waseca","A78-227013","Lodging",1.7),
    ("UT-II","Urbana","Pella (III)","SeedQuality",2.0),
    ("UT-III","Elk Point","U36276","SeedQuality",3.0),
    ("UT-III","Manhattan","HW74-3385","Lodging",1.0),
    ("UT-IV","Portageville Clay","K1033","SeedQuality",2.5),
    ("UT-IV","Queenstown","Franklin","SeedQuality",1.2),
    ("UT-IV","Manhattan","HC76-3840","Protein",42.2),
    ("UT-IV","Manhattan","HC76-3840","Oil",19.1),
    # ISSUE-10 — PT-IV Portageville Loam Maturity
    ("PT-IV","Portageville Loam","HC77-982","Maturity",264),
    ("PT-IV","Portageville Loam","K1033 Douglas","Maturity",276),
    ("PT-IV","Portageville Loam","K1061","Maturity",277),
    ("PT-IV","Portageville Loam","K1062","Maturity",264),
    ("PT-IV","Portageville Loam","K1063","Maturity",278),
    ("PT-IV","Portageville Loam","K1066","Maturity",274),
    ("PT-IV","Portageville Loam","K1067","Maturity",271),
    ("PT-IV","Portageville Loam","Ky78-405","Maturity",277),
    ("PT-IV","Portageville Loam","Ky78-1214","Maturity",277),
    ("PT-IV","Portageville Loam","L77-8209","Maturity",278),
    ("PT-IV","Portageville Loam","LS78-229","Maturity",291),
    ("PT-IV","Portageville Loam","LS78-335","Maturity",290),
    ("PT-IV","Portageville Loam","LS78-344","Maturity",285),
]

import re

def f4u_city(c):
    """Map src city names to Files4Upload city names."""
    return "West Lafayette" if c == "Lafayette" else c

def f4u_strain(s):
    """Map src strain names to Files4Upload strain names.
    R bridge strips spaces and drops parentheticals (MG designators).
    e.g. 'Evans (0)' -> 'Evans', 'BSR 302' -> 'BSR302', 'Pella (III)' -> 'Pella'
    """
    s = re.sub(r'\s*\([^)]*\)\s*', '', s)   # remove (...) blocks
    s = s.replace(' ', '')                    # remove remaining spaces
    s = s.rstrip('*')                         # remove trailing asterisks
    return s


src  = pd.read_csv(SRC)
dest = pd.read_csv(DEST)
dest = dest[dest["Year"] == 1980]            # R bridge may combine years

print(f"Source (approved CSV)  : {len(src):,} rows")
print(f"Dest   (Files4Upload)  : {len(dest):,} rows (1980 only)")

trait_col = "Phenotype" if "Phenotype" in dest.columns else "Trait"

ok = fail = missing = 0
failures = []

for test, city, strain, phenotype, expected in PATCHES:
    # --- check source ---
    sm = (src["Test"]==test) & (src["City"]==city) & (src["Strain"]==strain) & (src["Phenotype"]==phenotype)
    src_val = src.loc[sm, "Value"].values[0] if sm.any() else None

    # --- check dest (apply R bridge name normalizations) ---
    d_city   = f4u_city(city)
    d_strain = f4u_strain(strain)
    dm = (dest["Test"]==test) & (dest["City"]==d_city) & (dest["Strain"]==d_strain) & (dest[trait_col]==phenotype)

    if not dm.any():
        missing += 1
        failures.append(("MISSING", test, city, strain, phenotype, expected, src_val, None,
                          f"looked up as city='{d_city}' strain='{d_strain}'"))
        continue

    dest_val = dest.loc[dm, "Value"].values[0]
    try:
        match = pd.isna(dest_val) and pd.isna(expected) or abs(float(dest_val) - float(expected)) < 0.05
    except (ValueError, TypeError):
        match = str(dest_val) == str(expected)

    if match:
        ok += 1
    else:
        fail += 1
        failures.append(("MISMATCH", test, city, strain, phenotype, expected, src_val, dest_val, ""))

print(f"\n--- Phase 3 Results ---")
print(f"  OK       : {ok}")
print(f"  MISMATCH : {fail}")
print(f"  MISSING  : {missing}")

if failures:
    print("\nDetails:")
    for f in failures:
        tag, test, city, strain, ph, exp, sv, dv, note = f
        print(f"  {tag:8s}  {test:6s} {city:22s} {strain:25s} {ph:14s}  expected={exp}  src={sv}  dest={dv}  {note}")
else:
    print("\nAll patches verified in Files4Upload.")
