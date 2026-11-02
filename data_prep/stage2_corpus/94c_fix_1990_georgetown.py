"""
94c_fix_1990_georgetown.py
==========================
Re-extract & patch the one 1990 anomaly the offset-fix couldn't catch: UTIII
Georgetown_DE maturity was mis-extracted by the original 1990 PDF pilot -- the
WHOLE column is wrong (corpus DOY 157-180 = June, impossible for MG III; offsets
also wrong). Because the values looked like DOY (>=150) they slipped past the
offset re-anchor.

True values are on PDF p157 (UNIFORM TEST III, 1990; MATURITY block 1) where the
Georgetown DE column is identified BY ITS HEADER (not position -- the Mean column
aliases the anchor as a date). Anchor Resnik = 09/21 (DOY 264); each entry =
264 + its Georgetown offset. Local pdfplumber (zero-API), matched to corpus by strain.

Non-destructive: writes *.georgetownfixed.csv; --replace swaps in place
(backup .pre_georgetownfix.bak).

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/94c_fix_1990_georgetown.py [--replace]
"""
import argparse
import csv
import datetime
import re
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

sys.stdout.reconfigure(encoding="utf-8")

WIDE = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/analysis/data/_shared/NUST_1941_2025_data_wide.csv")
PDF  = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep/input_files/1990.pdf")
PAGE = 156   # 0-indexed p157 (UTIII maturity block 1, Georgetown = first location)
DATE_RE = re.compile(r"^\s*\d{1,2}/\d{1,2}\s*$")


def nm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def to_doy(s):
    a, b = str(s).split("/")[:2]
    return datetime.date(1990, int(a), int(b)).timetuple().tm_yday


def build_grid(page):
    words = [w for w in page.extract_words(x_tolerance=1.5, y_tolerance=1.5)
             if not (float(w["x0"]) < 15 and len(w["text"]) <= 2)]
    mi = next(w for w in words if w["text"].upper().startswith("MATURITY"))
    y0 = float(mi["top"])
    # window ends at the 'Date Planted' footer (or generously if not found)
    dp = next((float(w["top"]) for w in words
               if float(w["top"]) > y0 and w["text"].strip().lower().startswith("date")), y0 + 560)
    sec = [w for w in words if y0 <= float(w["top"]) <= dp]
    xs = sorted(set(round((float(w["x0"]) + float(w["x1"])) / 2) for w in sec))
    cols = []
    for x in xs:
        if cols and x - cols[-1][-1] <= 14:
            cols[-1].append(x)
        else:
            cols.append([x])
    centers = [sum(c) / len(c) for c in cols]
    rows = defaultdict(lambda: [""] * len(centers))
    for w in sec:
        rk = round(float(w["top"]) / 7) * 7
        c = min(range(len(centers)), key=lambda i: abs(centers[i] - (float(w["x0"]) + float(w["x1"])) / 2))
        rows[rk][c] = (rows[rk][c] + " " + w["text"]).strip()
    return [rows[k] for k in sorted(rows)]


def extract_georgetown(grid):
    # state row = the row whose col0 == 'Strain'
    si = next(i for i, r in enumerate(grid) if r and r[0].strip().lower() == "strain")
    frag, name, state = grid[si - 2], grid[si - 1], grid[si]
    width = max(len(frag), len(name), len(state))

    def cell(r, c):
        return r[c].strip() if c < len(r) else ""

    geo_col = None
    for c in range(1, width):
        nmc = cell(name, c).replace("\xad", "").strip()
        fr = cell(frag, c).replace("\xad", "-")
        city = (fr[:-1] + nmc) if fr.endswith("-") else (fr + " " + nmc if fr else nmc)
        if nm(city) == "georgetown":
            geo_col = c; break
    if geo_col is None:
        raise SystemExit("Georgetown column not found in header")

    data = [r for r in grid[si + 1:] if r and r[0] and r[0].strip().lower()
            not in ("date", "days") and not r[0].upper().startswith(("UNIFORM", "PRELIM"))]
    # anchor row = the data row whose Georgetown cell is a date
    arow = next(r for r in data if DATE_RE.match(cell(r, geo_col)))
    anchor_doy = to_doy(cell(arow, geo_col))

    out = {}
    for r in data:
        # strain spans col0 + col1 (suffix col: '(II)', '87 (dt)', '(Edison)', or empty)
        strain = (r[0] + " " + (r[1] if len(r) > 1 else "")).strip()
        s = nm(strain)
        v = cell(r, geo_col)
        if not s or v == "":
            continue
        if DATE_RE.match(v):
            out[s] = to_doy(v)
        else:
            try:
                out[s] = int(round(anchor_doy + float(v)))
            except ValueError:
                pass
    return out, anchor_doy, geo_col


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()

    with pdfplumber.open(PDF) as pdf:
        grid = build_grid(pdf.pages[PAGE])
    geo_map, anchor_doy, geo_col = extract_georgetown(grid)
    print(f"p{PAGE+1}: Georgetown=col{geo_col} anchorDOY={anchor_doy} "
          f"({len(geo_map)} strain maturities, range "
          f"{min(geo_map.values())}-{max(geo_map.values())})")

    out = WIDE.with_suffix(".georgetownfixed.csv")
    n = patched = miss = 0
    misses = []
    with open(WIDE, newline="", encoding="utf-8", errors="replace") as fi, \
         open(out, "w", newline="", encoding="utf-8") as fo:
        r = csv.DictReader(fi); cols = r.fieldnames
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader()
        for x in r:
            n += 1
            if (x.get("Year") == "1990" and x.get("Experiment", "").upper() == "UTIII"
                    and x.get("Location", "").split("_")[0].lower() == "georgetown"
                    and (x.get("Maturity") or "").strip() not in ("", "NA")):
                d = geo_map.get(nm(x.get("Strain")))
                if d is not None:
                    x["Maturity"] = str(int(d)); patched += 1
                else:
                    x["Maturity"] = ""; miss += 1; misses.append(x.get("Strain"))
            w.writerow(x)
    print(f"rows={n:,}  Georgetown patched={patched}  unmatched(NULLed)={miss}  {misses}")
    print(f"  wrote {out.name}")

    if args.replace:
        import shutil
        bak = WIDE.with_suffix(".pre_georgetownfix.bak")
        if not bak.exists():
            shutil.copy2(WIDE, bak)
        shutil.move(str(out), str(WIDE))
        print(f"  replaced {WIDE.name}  (backup {bak.name})")


if __name__ == "__main__":
    main()
