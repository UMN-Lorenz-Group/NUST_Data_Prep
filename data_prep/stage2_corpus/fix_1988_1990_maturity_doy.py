"""
fix_1988_1990_maturity_doy.py
=============================
Permanent SOURCE-LEVEL fix for the 1988 & 1990 partial maturity offset leak.

Both years store a MATURITY column that is MOSTLY absolute DOY but leaks raw
relative-day OFFSETS for some (Test, Location) groups (year range dips negative:
1988 [-22,294], 1990 [-17,295]). Prior scripts 94/94b/94c re-anchored 1990 but
patched the WIDE file downstream, so every corpus rebuild reverts it. This fix
converts offsets -> DOY at the SOURCE so it survives rebuilds:

  1990: F4U  NUST_Historical_Data_1941_1988/1990_Processing/Files4Upload/phenotypesTable1.csv
  1988: recovery_confirmed.csv  (UT-00, Source=PDF1988_UT00_review; the F4U main
        tests were DOY-fixed earlier, only my UT-00 recovery kept offsets)

Method (robust, self-validating):
  * Parse the report per-location MATURITY tables (Red PDF, local input_files/{1988,1990}.pdf)
    into a per-column matrix: each location column has the reference-check DATE
    (anchor) plus every strain's day +/- offset. Columns are found by word x-position.
  * Map each PDF column -> the correct source (Test,City) by matching the column's
    full OFFSET VECTOR to the source group's offset vector (verified: F4U offsets are
    correctly city-aligned; only the anchor value was mis-converted). A vector match
    over many strains is far more robust than header-name parsing or single-value votes.
  * DOY_i = anchorDOY(col) + offset_i ; the anchor strain's own cell is set to anchorDOY.

Guard rail ("a gap beats wrong data"): a source group is converted only if a PDF
column matches it with >= MIN_MATCH agreeing strains AND every resulting DOY lands
in the sane band. Otherwise that group's offsets are NULLed (faithful gap).

Usage:
    uv run --with pdfplumber python data_prep/stage2_corpus/fix_1988_1990_maturity_doy.py --report
    uv run --with pdfplumber python data_prep/stage2_corpus/fix_1988_1990_maturity_doy.py --apply
"""
import argparse
import datetime
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
NUST = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
HIST = NUST / "NUST_Historical_Data_1941_1988"
DATA = REPO / "analysis" / "data" / "_shared"

PDFS = {1988: REPO / "input_files/1988.pdf", 1990: REPO / "input_files/1990.pdf"}
F4U_1990 = HIST / "1990_Processing" / "Files4Upload" / "phenotypesTable1.csv"
RECOVERY = REPO / "data_prep" / "stage2_corpus" / "recovery_confirmed.csv"

HDR = re.compile(r"UNIFORM\s+TEST\s+(00|0|[IVX]+)", re.I)
DATE_CELL = re.compile(r"^\d{1,2}/\d{1,2}")
OFFSET_MAX = 90        # |value| below this = an un-anchored offset; >=100 is a DOY
BAND = (210, 322)      # sane maturity DOY band
MIN_MATCH = 3          # min agreeing strains to accept a PDF-column <-> source-group match
MIN_FRAC = 0.60        # min agreement fraction (agree/compared) to accept a match
URT_ANCHORS = DATA / "nust_anchor_checks_1989_2025.csv"   # PT (and UT) anchors, incl 1990


def to_doy(s, year):
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})", str(s))
    if not m:
        return None
    try:
        return datetime.date(year, int(m.group(1)), int(m.group(2))).timetuple().tm_yday
    except ValueError:
        return None


def to_off(s):
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*$", str(s))
    return float(m.group(1)) if m else None


def nm(s):
    """strain key: strip parenthetical MG tag, lower-alnum."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*\([^)]*\)", "", str(s)).lower())


def xc(w):
    return (float(w["x0"]) + float(w["x1"])) / 2


def parse_maturity_pages(year, pdf):
    """Yield (test_mg, page_no, columns) where columns = list of dicts:
       {x, anchor_date, anchor_doy, offsets:{strainKey:val}}.  Mean column dropped."""
    for pi, page in enumerate(pdf.pages):
        txt = page.extract_text() or ""
        m = HDR.search(txt)
        if not m or "MATURITY" not in txt.upper():
            continue
        mg = m.group(1).upper()
        words = page.extract_words(x_tolerance=1.5, y_tolerance=1.5)
        mtop = next((float(w["top"]) for w in words
                     if w["text"].upper().startswith("MATURITY")), None)
        if mtop is None:
            continue
        sec = [w for w in words if mtop <= float(w["top"]) < mtop + 300]
        # cluster columns by x-center
        centers = []
        for x in sorted(xc(w) for w in sec):
            if centers and x - centers[-1][-1] <= 12:
                centers[-1].append(x)
            else:
                centers.append([x])
        cen = [sum(c) / len(c) for c in centers]

        def col_of(w):
            return min(range(len(cen)), key=lambda i: abs(cen[i] - xc(w)))

        # rows by top
        rws = defaultdict(list)
        for w in sec:
            rws[round(float(w["top"]) / 6) * 6].append(w)
        grid = []
        for k in sorted(rws):
            row = [""] * len(cen)
            for w in sorted(rws[k], key=lambda w: float(w["x0"])):
                row[col_of(w)] = (row[col_of(w)] + " " + w["text"]).strip()
            grid.append(row)

        # anchor row = row whose cells are dates (>=3); strain col = col 0
        anchor_row = None
        for row in grid:
            nd = sum(1 for c in row if DATE_CELL.match(c))
            if nd >= 3:
                anchor_row = row
                break
        if anchor_row is None:
            continue
        date_cols = [c for c in range(len(cen)) if DATE_CELL.match(anchor_row[c])]
        if len(date_cols) < 2:
            continue
        # leftmost date col = Mean (near strain col); drop it
        loc_cols = date_cols[1:]
        anchor_strain = nm(anchor_row[0])

        # strain col = the column with the most alpha labels (col 0 usually)
        # collect per-strain offsets per loc_col
        columns = {c: {"x": cen[c], "anchor_date": anchor_row[c],
                       "anchor_doy": to_doy(anchor_row[c], year), "offsets": {}}
                   for c in loc_cols}
        for row in grid:
            sk = nm(row[0])
            if not sk or row is anchor_row:
                continue
            for c in loc_cols:
                v = to_off(row[c])
                if v is not None and abs(v) <= OFFSET_MAX:
                    columns[c]["offsets"][sk] = v
        # include the anchor strain itself as offset 0
        for c in loc_cols:
            columns[c]["offsets"].setdefault(anchor_strain, 0.0)
        cols = [d for d in columns.values() if d["anchor_doy"] is not None and d["offsets"]]
        if cols:
            yield mg, pi + 1, cols, anchor_strain


def build_pdf_index(year):
    """test_mg -> list of column dicts (across all pages of that test)."""
    import pdfplumber
    idx = defaultdict(list)
    anchors = {}
    with pdfplumber.open(PDFS[year]) as pdf:
        for mg, pg, cols, astrain in parse_maturity_pages(year, pdf):
            for d in cols:
                d["page"] = pg
            idx[mg].extend(cols)
            anchors[mg] = astrain
    return idx, anchors


def match_group(off_group, cols):
    """off_group: {strainKey: offset} from source. cols: candidate PDF columns.
    Return (best_col, n_agree, n_compared) ranked by agreement FRACTION then count
    (a column that extracted few strains but agrees 3/3 beats a 4/14 spurious hit)."""
    best, best_key, best_n, best_cmp = None, (-1, -1), 0, 0
    for d in cols:
        agree = cmp = 0
        for sk, ov in off_group.items():
            pv = d["offsets"].get(sk)
            if pv is None:
                continue
            cmp += 1
            if abs(pv - ov) < 0.6:
                agree += 1
        if cmp < MIN_MATCH or agree < MIN_MATCH:
            continue
        key = (agree / cmp, agree)
        if key > best_key:
            best, best_key, best_n, best_cmp = d, key, agree, cmp
    return best, best_n, best_cmp


def load_urt_anchors(year):
    """(normTest, cityKey) -> (anchorDOY, route2DOY) from the URT anchor table."""
    a = pd.read_csv(URT_ANCHORS)
    a = a[a.Year == year]
    out = {}
    for x in a.itertuples():
        adoy = getattr(x, "AnchorDOY", None)
        if pd.isna(adoy):
            continue
        r2 = None
        pd_ = getattr(x, "DatePlanted", None)
        dm = getattr(x, "DaysToMature", None)
        pdoy = to_doy(pd_, year) if pd.notna(pd_) else None
        if pdoy is not None and pd.notna(dm):
            try:
                r2 = int(round(pdoy + float(dm)))
            except (ValueError, TypeError):
                r2 = None
        key = (re.sub(r"[^A-Z0-9]", "", str(x.Test).upper()),
               re.sub(r"[^a-z0-9]", "", str(x.Location).split("_")[0].lower()))
        out[key] = (int(adoy), r2)
    return out


def leaked_groups_1990():
    d = pd.read_csv(F4U_1990, low_memory=False)
    d = d[d.Phenotype == "Maturity"].copy()
    d["v"] = pd.to_numeric(d.Value, errors="coerce")
    d = d.dropna(subset=["v"])
    out = {}
    for (t, c, s), g in d.groupby([d.Test, d.City, d.State]):
        if (g.v < 100).any():
            off = {nm(r.Strain): r.v for r in g.itertuples() if abs(r.v) <= OFFSET_MAX}
            out[(t, c, s)] = off
    return out


def leaked_groups_1988():
    r = pd.read_csv(RECOVERY, low_memory=False)
    r = r[(r.Year == 1988) & (r.Phenotype == "Maturity")].copy()
    r["v"] = pd.to_numeric(r.Value_num, errors="coerce")
    out = {}
    for (t, c, s), g in r.groupby([r.Test, r.City, r.State]):
        off = {nm(x.Strain): x.v for x in g.itertuples() if abs(x.v) <= OFFSET_MAX}
        out[(t, c, s)] = off
    return out


def mg_of_test(test):
    return re.sub(r"^UT-?", "", str(test)).upper()


def resolve(year, groups, idx, urt):
    """For each source group, find anchorDOY. PT tests -> URT table (offset+anchor),
    UT tests -> PDF offset-vector match. Band-check always. Return dict
    (test,city,state) -> {anchor_doy, n_agree, n_cmp, page, src, ok, reason}."""
    res = {}
    for (t, c, s), off in groups.items():
        rec = {"anchor_doy": None, "n_agree": 0, "n_cmp": 0, "page": None,
               "src": "", "ok": False, "reason": "", "city": c, "state": s, "test": t}
        adoy = None
        if t.upper().startswith("PT"):
            key = (re.sub(r"[^A-Z0-9]", "", t.upper()),
                   re.sub(r"[^a-z0-9]", "", str(c).split("_")[0].lower()))
            hit = urt.get(key)
            if hit:
                adoy = hit[0]
                rec["src"] = "URT"
                rec["reason"] = f"URT(r2={hit[1]})"
            else:
                rec["reason"] = "URT-missing"
        else:
            best, n, cmp = match_group(off, idx.get(mg_of_test(t), []))
            rec["n_agree"], rec["n_cmp"] = n, cmp
            if best is None:
                rec["reason"] = "no-match"
            elif n / cmp < MIN_FRAC:
                rec["reason"] = f"weak-match({n}/{cmp})"
                rec["page"] = best["page"]
            else:
                adoy = best["anchor_doy"]
                rec["src"] = f"PDF p{best['page']}"
                rec["page"] = best["page"]
                rec["reason"] = f"match({n}/{cmp})"
        if adoy is not None:
            vals = [adoy + o for o in off.values()]
            if all(BAND[0] <= v <= BAND[1] for v in vals):
                rec.update(anchor_doy=adoy, ok=True)
            else:
                rec["ok"] = False
                rec["reason"] += f" OUT-OF-BAND(anchor={adoy},min={min(vals):.0f},max={max(vals):.0f})"
        res[(t, c, s)] = rec
    return res


def report():
    for year, groups_fn in [(1990, leaked_groups_1990), (1988, leaked_groups_1988)]:
        print(f"\n===== {year} =====")
        idx, anchors = build_pdf_index(year)
        print(f"PDF maturity columns by test: {{ {', '.join(f'{k}:{len(v)}' for k,v in idx.items())} }}")
        groups = groups_fn()
        res = resolve(year, groups, idx, load_urt_anchors(year))
        ok = sum(1 for r in res.values() if r["ok"])
        print(f"leaked source groups: {len(groups)} | RESOLVED(convert): {ok} | NULL: {len(res)-ok}")
        for k, r in sorted(res.items()):
            tag = "OK " if r["ok"] else "NUL"
            print(f"  {tag} {r['test']:7} {str(r['city'])[:16]:16} {r['state']:4} "
                  f"anchorDOY={r['anchor_doy']} agree={r['n_agree']}/{r['n_cmp']} p{r['page']} {r['reason']}")


def fix_georgetown_1990(df):
    """Patch UT-III Georgetown DE maturity in-place on df (F4U 1990). The whole
    column was mis-extracted by the original pilot (DOY 157-180 = June); values look
    like DOY so they slipped past the offset re-anchor. Re-extract fresh from PDF p157
    by header (anchor Resnik 09/21=DOY 264 + per-strain Georgetown offset). Reuses the
    proven extractor in 94c_fix_1990_georgetown.py. Returns #rows patched."""
    import importlib.util
    import pdfplumber
    spec = importlib.util.spec_from_file_location(
        "g94c", REPO / "data_prep/stage2_corpus/94c_fix_1990_georgetown.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    with pdfplumber.open(PDFS[1990]) as pdf:
        geo, _, _ = g.extract_georgetown(g.build_grid(pdf.pages[g.PAGE]))
    mask = (df.Test == "UT-III") & (df.City == "Georgetown") & (df.Phenotype == "Maturity")
    n = 0
    for i in df[mask].index:
        d = geo.get(g.nm(df.at[i, "Strain"]))
        df.at[i, "Value"] = str(int(d)) if d is not None else ""
        n += d is not None
    return n


def apply_fix():
    summary = {}
    # ---- 1990 F4U ----
    idx90, _ = build_pdf_index(1990)
    g90 = leaked_groups_1990()
    r90 = resolve(1990, g90, idx90, load_urt_anchors(1990))
    df = pd.read_csv(F4U_1990, low_memory=False)
    bak = F4U_1990.with_suffix(".csv.orig_maturity_doy")
    if not bak.exists():
        shutil.copy2(F4U_1990, bak)
    df["v"] = pd.to_numeric(df.Value, errors="coerce")
    nconv = nnull = 0
    ismat = df.Phenotype == "Maturity"
    for (t, c, s), rec in r90.items():
        grp = ismat & (df.Test == t) & (df.City == c) & (df.State == s) & df.v.notna()
        off_mask = grp & (df.v.abs() <= OFFSET_MAX)
        surv_mask = grp & (df.v >= 100)          # mis-converted anchor row (offset 0)
        if rec["ok"]:
            a = rec["anchor_doy"]
            df.loc[off_mask, "Value"] = (df.loc[off_mask, "v"] + a).round().astype(int).astype(str)
            df.loc[surv_mask, "Value"] = str(int(a))
            nconv += int(off_mask.sum()) + int(surv_mask.sum())
        else:
            df.loc[off_mask, "Value"] = ""
            nnull += int(off_mask.sum())
    # ---- 1990 UT-III Georgetown: whole-column corrupt (DOY 157-180 = June), not a
    # simple offset leak; re-extract fresh from PDF p157 by header (reuses 94c logic) ----
    ngeo = fix_georgetown_1990(df)
    df.drop(columns=["v"]).to_csv(F4U_1990, index=False)
    summary["1990"] = (nconv + ngeo, nnull, sum(1 for r in r90.values() if r["ok"]), len(r90))

    # ---- 1988 recovery_confirmed ----
    idx88, _ = build_pdf_index(1988)
    g88 = leaked_groups_1988()
    r88 = resolve(1988, g88, idx88, load_urt_anchors(1988))
    rec_df = pd.read_csv(RECOVERY, low_memory=False)
    rbak = RECOVERY.with_suffix(".csv.orig_maturity_doy")
    if not rbak.exists():
        shutil.copy2(RECOVERY, rbak)
    rec_df["v"] = pd.to_numeric(rec_df.Value_num, errors="coerce")
    m88 = (rec_df.Year == 1988) & (rec_df.Phenotype == "Maturity")
    c88 = n88 = 0
    for (t, c, s), rec in r88.items():
        mask = m88 & (rec_df.Test == t) & (rec_df.City == c) & (rec_df.State == s) & rec_df.v.notna()
        if rec["ok"]:
            rec_df.loc[mask, "Value_num"] = (rec_df.loc[mask, "v"] + rec["anchor_doy"]).round()
            c88 += int(mask.sum())
        else:
            rec_df.loc[mask, "Value_num"] = pd.NA
            n88 += int(mask.sum())
    rec_df.drop(columns=["v"]).to_csv(RECOVERY, index=False)
    summary["1988"] = (c88, n88, sum(1 for r in r88.values() if r["ok"]), len(r88))

    print("APPLIED (source-level):")
    for y, (conv, null, gok, gtot) in summary.items():
        print(f"  {y}: converted {conv} rows ({gok}/{gtot} groups), NULLed {null} rows")
    print(f"  backups: {bak.name}, {rbak.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply:
        apply_fix()
    else:
        report()
