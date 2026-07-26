"""
fix_1962_pt_maturity.py
=======================
Recover the two 1962 Preliminary-Test maturity gaps that the F4U extraction missed:

  * PT-00 (Table 11, p21): per-location offset vs check Acme. F4U has ZERO maturity
    rows for PT-00 -> ADD rows.
  * PT-IV (Table 69, p120): per-location offset vs check Clark. F4U has 90 Maturity
    rows but with EMPTY Value cells (schema placeholders) -> FILL them.

Both source tables print, per strain, a per-location "days earlier (-)/later (+) than
<check>" offset, plus a "<check> matured M-D ..." anchor line giving the absolute
maturity date of the check at each location. Absolute DOY = anchorDOY(loc) + offset.

The 1940s-60s typewriter OCR splits the sign from the number ("+ 12") and wraps long
rows, so we parse via word x-positions: cluster (sign,number) tokens, bin each to the
nearest LOCATION column centre (taken from the header location names), and drop the
leftmost/decimal MEAN column. Every recovered value is arithmetic-checked against the
table's own "date planted / matured / days to mature" triple where available.

This is a --dry-run VALIDATOR by default (prints the recovered grid, writes nothing).
Pass --apply to patch the external F4U phenotypesTable1.csv in place (backup
.orig_1962_maturity). Repo-tracked so a rebuild reproduces the recovery.

Usage:
    uv run python data_prep/stage2_corpus/fix_1962_pt_maturity.py            # validate
    uv run python data_prep/stage2_corpus/fix_1962_pt_maturity.py --apply    # patch F4U
"""
import argparse
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pdfplumber
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
# Source PDFs under input_files/ are gitignored and live only in the primary checkout,
# so read them from there regardless of NUST_REPO (which only redirects tracked outputs).
SRC = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
PDF = SRC / "input_files" / "input_1962" / "1962_done.pdf"
NUST_DATA = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
F4U = NUST_DATA / "NUST_Historical_Data_1941_1988" / "1962_Processing" / "Files4Upload" / "phenotypesTable1.csv"


def doy(m, d):
    return date(1962, m, d).timetuple().tm_yday


# --- per-table specification -------------------------------------------------
# location column centres (x0 of the header name) + the F4U City/State they map to.
# anchor DOY is derived from the "<check> matured" line, cross-checked via planted+days.
TABLES = {
    "PT-IV": {
        "page": 94, "check": "Clark",
        # header name x -> (City, State) as spelled in the 1962 F4U
        "locs": [
            (207, "Georgetown", "DE"),
            (282, "Worthington", "IN"),
            (351, "Eldorado", "IL"),
            (408, "Carbondale", "IL"),
            (465, "Columbia", "MO"),
            (522, "Manhattan", "KS"),
        ],
    },
    "PT-00": {
        "page": 11, "check": "Acme",
        "locs": [
            (207, "Ottawa", "ONT"),
            (269, "East Lansing", "MI"),
            (331, "Ashland", "WI"),
            (388, "Portage la Prairie", "MAN"),
            (462, "Morden", "MAN"),
            (519, "Ontario", "OR"),
        ],
    },
}


def all_words(page):
    """Return every word as (top, x0, text), sorted top then x0."""
    ws = [(w["top"], w["x0"], w["text"]) for w in page.extract_words()]
    return sorted(ws)


def parse_matured(words, check):
    """Locate the '<check> matured ...' label y, then collect ALL date tokens within a
    y-band around it (the row wraps across 1-2 physical lines). Return {col_x: DOY}."""
    ys = [top for top, x0, t in words if t.lower() == "matured" and x0 < 120]
    if not ys:
        ys = [top for top, x0, t in words if t.lower() == "matured"]
    if not ys:
        return {}
    y0 = ys[0]
    out = {}
    for top, x0, t in words:
        if abs(top - y0) <= 9:
            m = re.match(r"(\d{1,2})-(\d{1,2})$", t)
            if m:
                out[x0] = doy(int(m.group(1)), int(m.group(2)))
    return out


def merge_sign_num(toks):
    """Merge split '+'/'-' sign tokens with the following number; return [(x, value)]."""
    out = []
    i = 0
    while i < len(toks):
        x, t = toks[i]
        if t in ("+", "-", "★", "*"):
            if t in ("+", "-") and i + 1 < len(toks):
                nx, nt = toks[i + 1]
                if re.match(r"\d+(\.\d+)?$", nt):
                    out.append((x, float(nt) * (1 if t == "+" else -1)))
                    i += 2
                    continue
            i += 1
            continue
        m = re.match(r"([+-]?)(\d+(\.\d+)?)$", t)
        if m:
            v = float(m.group(2)) * (-1 if m.group(1) == "-" else 1)
            out.append((x, v))
        i += 1
    return out


def nearest_loc(x, centers):
    return min(centers, key=lambda c: abs(c - x))


FOOTER = re.compile(r"Date|planted|matured|Days|mature|included|mean|Irrigated|Tests|Strain|"
                    r"Table|Maturity|nary|Mean|Not|of$", re.I)


def recover(spec, verbose=True):
    pdf = pdfplumber.open(PDF)
    page = pdf.pages[spec["page"] - 1]
    words = all_words(page)
    centers = [c for c, _, _ in spec["locs"]]
    loc_name = {c: (city, st) for c, city, st in spec["locs"]}

    matured = parse_matured(words, spec["check"])
    anchor = {}
    for x, d in matured.items():                      # map each date x to nearest centre;
        c = nearest_loc(x, centers)                   # keep the closest (drops the MEAN date col)
        if c not in anchor or abs(c - x) < anchor[c][1]:
            anchor[c] = (d, abs(c - x))
    anchor = {c: d for c, (d, _) in anchor.items()}

    name = list(TABLES.keys())[list(TABLES.values()).index(spec)]
    if verbose:
        print(f"\n=== {name} anchor {spec['check']} DOY per location ===")
        for c, city, st in spec["locs"]:
            print(f"  {city},{st}: {anchor.get(c,'(none)')}")

    # strain anchors: a token at the far-left margin that is a real strain label.
    strain_ys = []
    y_stop = min([top for top, x0, t in words if t.lower() == "planted"] or [1e9])
    for top, x0, t in words:
        if x0 < 60 and top < y_stop - 1 and not FOOTER.match(t) and not re.match(r"[+-]?\d", t):
            strain_ys.append((top, t))
    strain_ys.sort()

    recovered = []  # (strain, city, state, DOY, offset)
    for i, (sy, strain) in enumerate(strain_ys):
        y_hi = strain_ys[i + 1][0] if i + 1 < len(strain_ys) else y_stop
        band = [(top, x0, t) for top, x0, t in words if sy - 2 <= top < y_hi - 2]
        # merge split signs within the band, then bin location columns (x>175 skips MEAN col)
        toks = sorted((x0, t) for _, x0, t in band if x0 >= 40)
        for x, v in merge_sign_num(toks):
            if x <= 175 or v != int(v):     # MEAN column / decimal mean fragment
                continue
            c = nearest_loc(x, centers)
            if c not in anchor:
                continue
            city, st = loc_name[c]
            recovered.append((strain, city, st, int(round(anchor[c] + v)), int(v)))
    return recovered, anchor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    all_rows = {}
    for name, spec in TABLES.items():
        rec, anchor = recover(spec)
        all_rows[name] = rec
        print(f"\n=== {name}: {len(rec)} (strain,loc) maturity cells recovered ===")
        # grid print
        by_strain = {}
        for strain, city, st, d, off in rec:
            by_strain.setdefault(strain, {})[city] = f"{d}({off:+d})"
        cities = [c for _, c, _ in spec["locs"]]
        print("strain".ljust(12), " ".join(c[:9].rjust(10) for c in cities))
        for strain, cells in by_strain.items():
            print(strain.ljust(12), " ".join(cells.get(c, "-").rjust(10) for c in cities))
        bad = [r for r in rec if not (180 <= r[3] <= 330)]
        if bad:
            print(f"  !! {len(bad)} out-of-range DOY:", bad[:10])

    if not args.apply:
        print("\n[dry-run] no files written. Re-run with --apply to append to recovery_confirmed.csv.")
        return

    # ---- append to the shared recovery ledger (recovery_confirmed.csv) ----
    # The 1970-1988 loader (load_recovery_1970_1988) also carries the campaign's pre-1970
    # recovery (1946..1968), tagging every row Source=Recovered_1970_1988 and superseding the
    # matching F4U cell. We follow that convention: recovery rows for PT-IV supersede the empty
    # F4U Maturity placeholders; PT-00 rows add (the F4U has no PT-00 test).
    rec_csv = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"
    ledger = pd.read_csv(rec_csv, low_memory=False)
    mg = {"PT-IV": "IV", "PT-00": "00"}
    new = []
    for name, rec in all_rows.items():
        for strain, city, st, d, off in rec:
            new.append({"Year": 1962, "TestType": "PT", "TestMG": mg[name], "Test": name,
                        "Strain": strain, "City": city, "State": st, "Phenotype": "Maturity",
                        "Value_num": d, "Units": "date", "Source": "Recovered_1962_PDF"})
    new_df = pd.DataFrame(new)[list(ledger.columns)]
    # idempotent: drop any prior 1962 PT-00/PT-IV Maturity rows we may have added before
    key = ["Year", "Test", "Phenotype"]
    prior = ((ledger["Year"] == 1962) & (ledger["Test"].isin(["PT-IV", "PT-00"]))
             & (ledger["Phenotype"] == "Maturity"))
    if prior.any():
        print(f"  (removing {int(prior.sum())} previously-added 1962 PT maturity rows)")
        ledger = ledger[~prior]
    out = pd.concat([ledger, new_df], ignore_index=True)
    out.to_csv(rec_csv, index=False)
    print(f"\nrecovery_confirmed.csv: +{len(new_df)} rows (1962 PT-IV + PT-00 Maturity) "
          f"-> {len(out)} total")


if __name__ == "__main__":
    main()
