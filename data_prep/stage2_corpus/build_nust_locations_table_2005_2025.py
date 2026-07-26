"""
build_nust_locations_table_2005_2025.py
=======================================
Assemble NUST_Locations_Table_Combined_2005_2025.csv with columns:
  Year, Test, Location, State, lat, lon, Conductor, PlantingDate, MaturityDate
(PlantingDate / MaturityDate = day-of-year integers), one row per (Year, Test, Location).

Sources (per era — see project_nust_locations_plot_info / this session's infra scan):
  * 2021-2025 : NUST_Data/<year>/.../LocationsTable1_Test.csv  — ALREADY this exact schema
                (dates already DOY). Reused verbatim.
  * 2016-2020 : NUST_Data/NUST_Data_1993_2020_fromQueryportal/<year>/locationsTable1.csv
                — portal schema (Lat/Longe, M/D/YYYY dates). Transformed: Longe->lon,
                dates -> DOY, keep Conductor; drop Row Spacing/Days to maturity/Comment.
  * 2005-2015 : NO authoritative location metadata exists (portal returns "no data"; no local
                report PDFs). Only the Year/Test/Location/State skeleton is reconstructed from
                the corpus; lat/lon are left BLANK by design (the only available coords would be
                geocoded approximations, not official station GPS). Conductor / PlantingDate /
                MaturityDate also absent (require the 2005-2015 report PDFs).

Writes:
  analysis/data/_shared/NUST_Locations_Table_Combined_2005_2025.csv
  analysis/data/analysis_results/Corpus_QC/NUST_Locations_Table_Combined_2005_2025_coverage.md

Run: uv run python data_prep/stage2_corpus/build_nust_locations_table_2005_2025.py
"""
import sys, re, difflib
from pathlib import Path
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO   = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
ND     = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
QP     = ND / "NUST_Data_1993_2020_fromQueryportal"
SHARED = REPO / "analysis" / "data" / "_shared"
QC_DIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
REF    = REPO / "reference" / "nust_locations_ref.csv"
OUT_CSV = SHARED / "NUST_Locations_Table_Combined_2005_2025.csv"
OUT_MD  = QC_DIR / "NUST_Locations_Table_Combined_2005_2025_coverage.md"
COLS = ["Year", "Test", "Location", "State", "lat", "lon", "Conductor", "PlantingDate", "MaturityDate"]

# 2021-2025 LocationsTable1_Test.csv paths
LOC_2021_2025 = {
    2021: ND / "2021" / "LocationsTable1_Test.csv",
    2022: ND / "2022" / "2022_NUST_Processing" / "LocationsTable1_Test.csv",
    2023: ND / "2023" / "2023_NUST_Processing" / "LocationsTable1_Test.csv",
    2024: ND / "2024" / "2024_NUST_Processing" / "LocationsTable1_Test.csv",
    2025: ND / "2025" / "2025_NUST_Processing" / "Files4Upload" / "LocationsTable1.csv",
}

def to_doy(x):
    """M/D/YYYY -> DOY int; passthrough ints/DOY; NaN/blank -> NA."""
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if s in ("", "NA", "nan"):
        return np.nan
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        mo, da, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return int(pd.Timestamp(yr, mo, da).dayofyear)
    try:
        f = float(s)
        if 1 <= f <= 366:
            return int(round(f))
    except ValueError:
        pass
    return np.nan

def clean_test(t):
    return re.sub(r"\s+", "", str(t)).strip()

def load_2021_2025():
    frames = []
    for yr, fp in LOC_2021_2025.items():
        if not fp.exists():
            print(f"  {yr}: MISSING {fp}")
            continue
        d = pd.read_csv(fp)
        d.columns = [c.strip() for c in d.columns]
        d = d.rename(columns={c: c for c in d.columns})
        d["Year"] = yr
        d["Test"] = d["Test"].map(clean_test)
        d = d[d["Test"].str.lower() != "test"]          # drop stray header-as-row
        for c in ("PlantingDate", "MaturityDate"):
            d[c] = d[c].map(to_doy)
        frames.append(d[COLS])
        print(f"  {yr}: {len(d):>4} rows (LocationsTable1_Test)")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)

def load_2016_2020():
    frames = []
    for yr in range(2016, 2021):
        fp = QP / str(yr) / "locationsTable1.csv"
        if not fp.exists():
            print(f"  {yr}: MISSING {fp}")
            continue
        d = pd.read_csv(fp)
        d.columns = [c.strip() for c in d.columns]
        ren = {"Lat": "lat", "Longe": "lon", "Long": "lon",
               "Planting date": "PlantingDate", "Maturity date": "MaturityDate"}
        d = d.rename(columns=ren)
        d["Year"] = yr
        d["Test"] = d["Test"].map(clean_test)
        d = d[d["Test"].str.lower() != "test"]
        d["PlantingDate"] = d["PlantingDate"].map(to_doy)
        d["MaturityDate"] = d["MaturityDate"].map(to_doy)
        for c in COLS:
            if c not in d.columns:
                d[c] = np.nan
        frames.append(d[COLS])
        print(f"  {yr}: {len(d):>4} rows (queryportal locationsTable1)")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)

def _key(city, state):
    return (re.sub(r"[^a-z0-9]", "", str(city).lower()), str(state).strip().upper())

def load_2005_2015_skeleton():
    c = pd.read_csv(SHARED / "nust_1941_2025_combined.csv", low_memory=False)
    s = c[(c.Year >= 2005) & (c.Year <= 2015)].copy()
    s = s[s["City"].notna() & (s["City"].astype(str).str.strip() != "")]
    sk = s[["Year", "Test", "Variant", "City", "State"]].drop_duplicates()
    # normalize Test to the location-table style: de-hyphenate + era RR suffix for Traited
    def testcode(row):
        t = str(row["Test"]).replace("-", "")
        if str(row["Variant"]).strip().lower() == "traited":
            t += "RR"      # 2005-2015 used the RR suffix (TM switch came 2018)
        return t
    sk["Test"] = sk.apply(testcode, axis=1)
    sk = sk.rename(columns={"City": "Location"}).drop(columns=["Variant"]).drop_duplicates()
    # lat/lon left BLANK by design — no official station GPS pre-2020 (only geocoded
    # approximations exist). PlantingDate/MaturityDate absent (would need per-test maturity
    # tables). Conductor IS recoverable: the report 'Uniform and Preliminary Test Location(s)'
    # grower table exists 1989+ — extracted to reference/nust_conductors_2005_2015.csv by
    # extract_conductors_2005_2015.py; joined here per (Year, State, Location) with name
    # normalization + prefix/fuzzy fallback (SAME-year matches only — faithful to that report).
    sk["lat"] = np.nan
    sk["lon"] = np.nan
    sk["Conductor"] = _join_conductors(sk)
    pdt, mdt = _join_dates(sk)
    sk["PlantingDate"] = pdt
    sk["MaturityDate"] = mdt
    n_c = int(sk["Conductor"].notna().sum())
    n_p = int(sk["PlantingDate"].notna().sum())
    n_m = int(sk["MaturityDate"].notna().sum())
    print(f"  2005-2015: {len(sk):>4} rows (corpus skeleton; lat/lon blank; "
          f"Conductor {n_c}, PlantingDate {n_p}, MaturityDate {n_m} filled from report tables)")
    return sk[COLS]

def _join_dates(sk):
    """Per-(Year,Test,State,Location) PlantingDate/MaturityDate (DOY) from the maturity
    tables (extract_dates_2005_2015.py). Match Year+Test+State then Location exact/prefix/fuzzy."""
    fp = REPO / "reference" / "nust_planting_maturity_2005_2015.csv"
    if not fp.exists():
        n = pd.Series([np.nan] * len(sk), index=sk.index)
        return n, n.copy()
    d = pd.read_csv(fp)
    d["k"] = d["Location"].map(_locnorm)
    d["s"] = d["State"].map(_stnorm)
    d["t"] = d["Test"].astype(str).str.replace("-", "").str.upper()
    exact = {}
    for _, r in d.iterrows():
        exact.setdefault((r.Year, r.t, r.s, r.k), (r.PlantingDOY, r.MaturityDOY))
    pl_out, mt_out = [], []
    for _, r in sk.iterrows():
        rt = str(r["Test"]).replace("-", "").upper()
        rk, rs = _locnorm(r["Location"]), _stnorm(r["State"])
        hit = exact.get((r["Year"], rt, rs, rk))
        if hit is None:
            cand = d[(d.Year == r["Year"]) & (d.t == rt) & (d.s == rs)]
            for _, c in cand.iterrows():                        # prefix
                if c.k and rk and (c.k.startswith(rk) or rk.startswith(c.k)):
                    hit = (c.PlantingDOY, c.MaturityDOY); break
            if hit is None and len(cand):                       # fuzzy
                m = difflib.get_close_matches(rk, cand.k.tolist(), n=1, cutoff=0.8)
                if m:
                    cc = cand[cand.k == m[0]].iloc[0]; hit = (cc.PlantingDOY, cc.MaturityDOY)
        pl_out.append(hit[0] if hit else np.nan)
        mt_out.append(hit[1] if hit else np.nan)
    return pd.Series(pl_out, index=sk.index), pd.Series(mt_out, index=sk.index)

def fill_conductor_within_state(full):
    """Fill missing Conductor from within-year, within-state data, and record provenance in
    a `Conductor_source` column so the analysis can weight inferred values:
      * "report"         — from that location's own report grower / LocationsTable row.
      * "state_single"   — the (Year,State) has ONE known conductor -> unambiguous fill
                           (e.g. Danvers MN 2010 = 'J. Orf').
      * "state_majority" — the (Year,State) has 2+ conductors with a UNIQUE plurality ->
                           filled with the most common (e.g. IA -> Fehr); a guess, flagged.
      * <NA>             — still missing (tie between conductors, or none known that year).
    """
    is_rep = full["Conductor"].notna() & (full["Conductor"].astype(str).str.strip() != "")
    src = pd.Series(pd.NA, index=full.index, dtype="object")
    src[is_rep] = "report"
    n_single = n_maj = 0
    for (yr, st), g in full[is_rep].groupby(["Year", "State"]):
        vc = g["Conductor"].value_counts()
        if len(vc) == 1:
            val, tag = vc.index[0], "state_single"
        elif len(vc) >= 2 and vc.iloc[0] > vc.iloc[1]:      # unique plurality
            val, tag = vc.index[0], "state_majority"
        else:
            continue                                        # tie -> leave blank
        mask = (full["Year"] == yr) & (full["State"] == st) & (~is_rep)
        if mask.any():
            full.loc[mask, "Conductor"] = val
            src[mask] = tag
            if tag == "state_single": n_single += int(mask.sum())
            else: n_maj += int(mask.sum())
    full["Conductor_source"] = src
    print(f"  within-state conductor fill: +{n_single} state_single, +{n_maj} state_majority "
          f"(residual missing: {int(full['Conductor'].isna().sum())})")
    return full

def _locnorm(s):
    s = str(s).lower()
    s = re.sub(r"\(.*?\)", "", s)                 # drop (Clay)/(Loam)/(Ames)
    s = re.sub(r"\b(county|co)\b", "", s)         # county / co
    s = re.sub(r"[^a-z0-9]", "", s)
    s = re.sub(r"^(west|w|east|e|north|n|south|s)", "", s)   # directional prefix
    return s

def _stnorm(s):
    s = str(s).strip().upper()
    return {"ON": "ONT", "QC": "QUE", "MB": "MAN", "SK": "SAS"}.get(s, s)

def _join_conductors(sk):
    """Per-(Year,State,Location) conductor from the extracted report grower tables.
    exact -> prefix -> fuzzy(0.8), all within the SAME year+state; else NaN."""
    cfp = REPO / "reference" / "nust_conductors_2005_2015.csv"
    if not cfp.exists():
        return pd.Series([np.nan] * len(sk), index=sk.index)
    cond = pd.read_csv(cfp)
    cond["k"] = cond["Location"].map(_locnorm)
    cond["s"] = cond["State"].map(_stnorm)
    exact = dict(zip(zip(cond.Year, cond.s, cond.k), cond.Conductor))
    out = []
    for _, r in sk.iterrows():
        rk, rs = _locnorm(r["Location"]), _stnorm(r["State"])
        key = (r["Year"], rs, rk)
        if key in exact:
            out.append(exact[key]); continue
        cand = cond[(cond.Year == r["Year"]) & (cond.s == rs)]
        hit = None
        for _, c in cand.iterrows():             # prefix
            if c.k and rk and (c.k.startswith(rk) or rk.startswith(c.k)):
                hit = c.Conductor; break
        if hit is None and len(cand):            # fuzzy
            m = difflib.get_close_matches(rk, cand.k.tolist(), n=1, cutoff=0.8)
            if m:
                hit = cand[cand.k == m[0]].Conductor.iloc[0]
        out.append(hit)
    return pd.Series(out, index=sk.index)

def main():
    print("Loading 2021-2025 ...");  a = load_2021_2025()
    print("Loading 2016-2020 ...");  b = load_2016_2020()
    print("Loading 2005-2015 ...");  d = load_2005_2015_skeleton()
    full = pd.concat([d, b, a], ignore_index=True)
    # drop phantom rows from the source files (blank Test AND/OR Location — e.g. 122 empty
    # trailing rows in the 2020 queryportal locationsTable). Not real (Year,Test,Location) entries.
    def _blank(s):
        return s.isna() | (s.astype(str).str.strip().isin(["", "nan", "NaN"]))
    n0 = len(full)
    full = full[~(_blank(full["Test"]) | _blank(full["Location"]))].copy()
    if len(full) < n0:
        print(f"  dropped {n0 - len(full)} phantom rows (blank Test/Location)")
    full["Year"] = full["Year"].astype(int)
    full = fill_conductor_within_state(full)
    for c in ("PlantingDate", "MaturityDate"):
        full[c] = pd.to_numeric(full[c], errors="coerce").astype("Int64")
    full = full.sort_values(["Year", "Test", "State", "Location"]).reset_index(drop=True)
    # output columns = COLS with Conductor_source inserted right after Conductor
    out_cols = COLS[:COLS.index("Conductor") + 1] + ["Conductor_source"] + COLS[COLS.index("Conductor") + 1:]
    full = full[out_cols]
    full.to_csv(OUT_CSV, index=False)

    # coverage report
    lines = ["# NUST_Locations_Table_Combined_2005_2025 — coverage", "",
             f"- rows: **{len(full):,}**  |  years {full.Year.min()}–{full.Year.max()}", ""]
    g = full.assign(has_gps=full.lat.notna(), has_cond=full.Conductor.notna(),
                    has_plant=full.PlantingDate.notna(), has_mat=full.MaturityDate.notna())
    cov = g.groupby("Year").agg(rows=("Test", "size"),
                                gps=("has_gps", "sum"), conductor=("has_cond", "sum"),
                                planting=("has_plant", "sum"), maturity=("has_mat", "sum"))
    lines.append("| Year | rows | lat/lon | Conductor | PlantingDate | MaturityDate |")
    lines.append("|---|---|---|---|---|---|")
    for yr, r in cov.iterrows():
        lines.append(f"| {yr} | {r['rows']} | {r['gps']} | {r['conductor']} | {r['planting']} | {r['maturity']} |")
    # anomaly flags — carried through from the SOURCE location files (not fixed here)
    both = full[full.PlantingDate.notna() & full.MaturityDate.notna()]
    swapped = both[both.MaturityDate <= both.PlantingDate]
    lines += ["", "## Flagged source anomalies (dates carried verbatim from the source files — NOT fixed)",
              f"- rows with MaturityDate <= PlantingDate (impossible / likely swapped): **{len(swapped)}**"]
    if len(swapped):
        lines.append("")
        lines.append("| Year | Test | Location | State | PlantingDate | MaturityDate |")
        lines.append("|---|---|---|---|---|---|")
        for _, r in swapped.sort_values(["Year", "Test", "Location"]).iterrows():
            lines.append(f"| {r.Year} | {r.Test} | {r.Location} | {r.State} | {r.PlantingDate} | {r.MaturityDate} |")
    lines.append("")
    lines += ["", "**Source by era:** 2021-2025 = `LocationsTable1_Test.csv` (report-PDF pipeline, "
              "native DOY); 2016-2020 = SoyBase queryportal `locationsTable1.csv` (dates M/D/YYYY→DOY); "
              "2005-2015 = corpus skeleton only — lat/lon left BLANK by design (no official station "
              "GPS in that era), Conductor/PlantingDate/MaturityDate absent (need the 2005-2015 report PDFs)."]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {OUT_CSV}  ({len(full):,} rows)")
    print(f"Wrote {OUT_MD}")

if __name__ == "__main__":
    main()
