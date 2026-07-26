"""Derive the 1975 test map from the doc-AI intermediate ("Yellow" per-page) output.

1975 is the one year with NO single-sheet Green and NO PDF in input_files -- it was PDF-direct
extracted with an IDENTITY TEST_MAPS. But the doc-AI folder on R: has, per page:
    <page>.1.xlsx        the extracted table
    <page>.1_title.txt   the page CAPTION  <- this is the LABEL ORACLE, cleaner than any PDF text layer
So the same caption logic (pdf_captions.parse_caption) applies, just fed from the title files.

FINDING (proven three ways): 1975 has 11 tests (UT-00, UT-0, PT-0, UT-I, PT-I, UT-II, PT-II, UT-III,
PT-III, UT-IV, PT-IV) -- there is NO PT-00. The F4U's 12th label `PT-00` is a PHANTOM: its 15 strains
are a MERGE of real UT-00 (CM147/CM148/M65-217/Altona, doc-AI pp.2-9) + real PT-0 (M67-*/M68-38,
doc-AI pp.17-19). No page is captioned "PRELIMINARY TEST 00" anywhere in the 1975 report.

This is a DATA-level defect in the 1975 F4U (like 1984), not a Group_N/JSON issue -- 1975 has no tp2
Group structure. So we emit the verified-map ledger rows (with PT-00 flagged) but NO --test_map JSON.
"""
import glob
import os
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from pdf_captions import parse_caption, sort_key, norm_strain, _FOOT  # noqa: E402

CACHE = Path("C:/Users/vramasub/AppData/Local/Temp/nust_1975_cache")
OUT_CSV = REPO / "reference" / "nust_test_map_verified.csv"
F4U = ("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data/"
       "NUST_Historical_Data_1941_1988/1975_Processing/Files4Upload/phenotypesTable1.csv")


def pageno(fname):
    m = re.match(r"(\d+)(?:\.(\d+))?", os.path.basename(fname))
    return (int(m.group(1)), int(m.group(2) or 1))


def title_of(page_stem):
    p = CACHE / f"{page_stem}_title.txt"
    return p.read_text(errors="replace").strip() if p.exists() else ""


def page_roster(xlsx):
    """Strain-column tokens from a doc-AI page table (col 0/1), norm-folded, footers dropped."""
    out = set()
    try:
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
        for row in wb.active.iter_rows(values_only=True):
            for cell in row[:1]:
                if cell is None:
                    continue
                n = norm_strain(cell)
                if len(n) >= 4 and n not in _FOOT:
                    out.add(n)
        wb.close()
    except Exception:
        pass
    return out


def caption_sections_1975():
    """Ordered runs of same-code pages, with a roster unioned from each run's .1.xlsx tables."""
    files = sorted(glob.glob(str(CACHE / "*_title.txt")), key=pageno)
    runs, cur = [], None
    for f in files:
        pg = pageno(f)[0]
        code = parse_caption(open(f, errors="replace").read())
        if code is None:
            continue
        if not runs or runs[-1]["code"] != code:
            runs.append({"code": code, "pages": [], "roster": set()})
        runs[-1]["pages"].append((pg, os.path.basename(f).replace("_title.txt", "")))
    # roster per run from the .1 table of each page
    for r in runs:
        for pg, stem in r["pages"]:
            x = CACHE / f"{stem}.xlsx"
            if x.exists():
                r["roster"] |= page_roster(x)
    # collapse to unique consecutive codes already done; keep first/last page ints
    for r in runs:
        r["p0"], r["p1"] = r["pages"][0][0], r["pages"][-1][0]
    return runs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    runs = caption_sections_1975()
    seq = [r["code"] for r in runs]
    print(f"1975 doc-AI caption sequence ({len(seq)} tests): {seq}")
    print(f"  canonical order: {seq == sorted(seq, key=sort_key)}")

    f = pd.read_csv(F4U, low_memory=False)
    f = f[f.Year == 1975]
    f4u_ros = {t: {norm_strain(s) for s in g.Strain.dropna().astype(str)} - _FOOT
               for t, g in f.groupby("Test")}

    def ov(a, b):
        return len(a & b) / max(1, min(len(a), len(b))) if a and b else 0.0

    rows, claimed = [], set()
    for i, r in enumerate(runs, 1):
        best, bo = None, 0.0
        for t, ros in f4u_ros.items():
            o = ov(r["roster"], ros)
            if o > bo:
                bo, best = o, t
        claimed.add(best)
        rows.append(dict(Year=1975, section_order=i, group_n=None, true_code=r["code"],
                         pdf_pages=f"{r['p0']}-{r['p1']}", caption_pages=len(r["pages"]),
                         roster_overlap=round(bo, 3), green_file="(doc-AI title files)", green_row=-1,
                         nstrain=len(r["roster"]), nloc=-1, geom="",
                         f4u_claimant=best or "", yield_match=0.0,
                         testmaps_code=r["code"],
                         agrees_with_testmaps=True,
                         status="CLEAN" if best and re.sub(r"[^A-Z0-9]", "", best.upper()) ==
                         re.sub(r"[^A-Z0-9]", "", r["code"].upper()) else f"MISLABEL->{r['code']}"))
    # any F4U label NOT claimed by a true caption-section = phantom
    phantom = [t for t in f4u_ros if t not in claimed]
    print("\n  section -> F4U claimant:")
    for r in rows:
        print(f"    {r['true_code']:8} pp {r['pdf_pages']:7} -> {r['f4u_claimant']:8} "
              f"(roster {r['roster_overlap']})  {r['status']}")
    print(f"\n  F4U labels with NO true caption-section (PHANTOM): {phantom}")
    for t in phantom:
        rows.append(dict(Year=1975, section_order=len(rows) + 1, group_n=None, true_code="",
                         pdf_pages="", caption_pages=0, roster_overlap=0.0,
                         green_file="(doc-AI title files)", green_row=-1,
                         nstrain=len(f4u_ros[t]), nloc=-1, geom="", f4u_claimant=t, yield_match=0.0,
                         testmaps_code="", agrees_with_testmaps=False,
                         status="PHANTOM(no such test)"))

    df = pd.DataFrame(rows)
    if "--write" in sys.argv:
        prev = pd.read_csv(OUT_CSV)
        prev = prev[prev.Year != 1975]
        out = pd.concat([prev, df], ignore_index=True).sort_values(["Year", "section_order"])
        out.to_csv(OUT_CSV, index=False)
        print(f"\n  wrote {len(df)} rows for 1975 into {OUT_CSV.name} (total {len(out)})")
    else:
        print("\n  (dry run; --write to add 1975 to the verified CSV)")


if __name__ == "__main__":
    main()
