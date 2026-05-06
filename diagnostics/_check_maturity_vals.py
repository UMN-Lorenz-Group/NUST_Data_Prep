import sys, re
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from datetime import date
import calendar

def _try_float(v):
    try:
        return float(str(v).strip().rstrip("*").lstrip("+"))
    except Exception:
        return None

ph = pd.read_csv("output_1980/combined_1980_phenotypesTable.csv")
mat = ph[(ph["Phenotype"] == "Maturity") & (ph["City"] != "Mean")].copy()

print("=== Maturity value formats by Test (per-location rows only) ===")
for test in sorted(mat["Test"].unique()):
    vals = mat[mat["Test"]==test]["Value"].dropna()
    n_doy    = sum(1 for v in vals if _try_float(v) is not None and _try_float(v) > 100)
    n_offset = sum(1 for v in vals if _try_float(v) is not None and -60 <= _try_float(v) <= 60)
    n_date   = sum(1 for v in vals if re.search(r'\d+/\d+', str(v)))
    n_null   = sum(1 for v in vals if str(v).strip() in ("None","nan","","<NA>"))
    print(f"  {test:<10}: doy={n_doy}  offset={n_offset}  M/D={n_date}  null/other={n_null}  total={len(vals)}")
    if n_doy > 0:
        sample = [v for v in vals if _try_float(v) is not None and _try_float(v) > 100][:5]
        print(f"             DOY samples: {sample}")
    if n_date > 0:
        sample = [v for v in vals if re.search(r'\d+/\d+', str(v))][:5]
        print(f"             M/D samples: {sample}")

print()
print("=== Leap year check for 1980 ===")
print(f"  1980 is leap year: {calendar.isleap(1980)}")
print()
print("  Perpetual vs leap DOY for key September/October dates:")
print(f"  {'Date':<10} {'Perpetual':>10} {'Leap(1980)':>12} {'Diff':>6}")
perp = {(9,1):244,(9,5):248,(9,10):253,(9,15):258,(9,19):262,
        (9,25):268,(10,1):274,(10,10):283,(10,15):288}
for (m,d), p_doy in sorted(perp.items()):
    l_doy = date(1980, m, d).timetuple().tm_yday
    print(f"  {m}/{d:<8} {p_doy:>10} {l_doy:>12} {l_doy-p_doy:>6}")

print()
print("=== Anchor DOY cross-check: are stored DOY values perpetual or leap? ===")
anchors = pd.read_csv("output_1980/maturity_anchors_1980.csv")
# Show a sample and infer: if anchor DOY < 245, it's pre-Sep-1 (no difference)
# If anchor >= 245, difference should be 1 if using leap calendar
sep_anchors = anchors[anchors["AnchorDOY"] >= 244].head(15)
print(sep_anchors.to_string(index=False))
print()
print("  For Sep dates: if DOY = perpetual value (e.g. Sep 1=244), data used PERPETUAL calendar")
print("                 if DOY = leap value   (e.g. Sep 1=245), data used LEAP calendar")
