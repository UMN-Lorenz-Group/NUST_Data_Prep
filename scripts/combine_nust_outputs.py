#!/usr/bin/env python
"""
combine_nust_outputs.py
=======================
Merge CSVs from multiple NUST historical XLSX extractions into single
combined output files, apply Group->TestCode TEST_MAP rename, and format
all tables to match the NUST database conventions (2025 reference schema).

Output tables produced (combined_{year}_*.csv):
  phenotypesTable         — Strain, Year, Test, Location, City, State, Phenotype, Value, Units
                            Maturity values converted to DOY (day of year).
  strainsTable            — Year, Test, Strain, OriginalStrain, Descriptive.Code,
                            Unique.traits, Gen.Comp., Check
  parentageTable          — Year, Test, Strain, Female, Male
  locationsTable          — Year, Test, City, State, lat, lon, Conductor,
                            PlantingDate, MaturityDate  (lat/lon/Conductor = NULL for historical)
  checksTable             — Year, Test, Strain, OriginalStrain, Phenotype, RM
                            (RM = NULL for historical; Phenotype = MG group label)
  maturityAnchorsTable    — Year, Test, ReferenceCheck, City, State,
                            AnchorDate, AnchorDOY, Source
                            Records the reference check and its maturity date used to
                            anchor relative day offsets per Test × Location.
  maturityVerification    — Strain, Year, Test, City, State, OriginalMaturity,
                            ComputedDOY, Status
                            Intermediate file for manual review of DOY conversion.
  descriptive             — unchanged (raw extraction output)
  disease                 — unchanged (raw extraction output)
  summary                 — unchanged (raw extraction output)

Note: MetaTable (CV%, LSD, location means) requires metadata capture during
extraction — not yet available for historical data.

Usage:
    python combine_nust_outputs.py --out_dir ./output_1980/ --year 1980
    python combine_nust_outputs.py --out_dir ./output_1980/ --year 1980 --no_remap
    python combine_nust_outputs.py --out_dir ./output_1980/ --year 1980 --pdf input_1980/1980_done.pdf
    python combine_nust_outputs.py --out_dir ./output_1980/ --year 1980 --pdf_json output_1980/check_maturity_pdf_raw_1980.json
"""

import argparse
import json
import os
import re
import sys
from datetime import date as _date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd


# ---------------------------------------------------------------------------
# .Env loader
# ---------------------------------------------------------------------------

def _load_env_file(path=".Env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            elif line.startswith("sk-ant-"):
                os.environ.setdefault("ANTHROPIC_API_KEY", line)

_load_env_file()


# ---------------------------------------------------------------------------
# Rex / database formatting conventions
# ---------------------------------------------------------------------------

PHENOTYPE_MAP = {
    "PLANT HEIGHT":  "Height",
    "LODGING":       "Lodging",
    "MATURITY":      "Maturity",
    "YIELD":         "YieldBuA",
    "YIELD RANK":    "YieldRank",
    "SEED SIZE":     "SeedSize",
    "SEED QUALITY":  "SeedQuality",
    "PROTEIN":       "Protein",
    "OIL":           "Oil",
}

# MG label derived from test code  (UT-00 -> "MG 00", PT-III -> "MG III", etc.)
def _test_to_mg(test: str) -> str:
    m = re.search(r'[-_](.+)$', str(test))
    return f"MG {m.group(1)}" if m else ""


# ---------------------------------------------------------------------------
# Trait / units splitting
# ---------------------------------------------------------------------------

def _split_trait_units(trait: str) -> tuple[str, str]:
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', str(trait).strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else (str(trait).strip(), "")


def ensure_units_column(df: pd.DataFrame) -> pd.DataFrame:
    if "Units" in df.columns:
        return df
    if "Phenotype" not in df.columns:
        return df
    split = df["Phenotype"].apply(_split_trait_units)
    df = df.copy()
    value_idx = df.columns.get_loc("Value")
    df["Phenotype"] = split.apply(lambda x: x[0])
    df.insert(value_idx + 1, "Units", split.apply(lambda x: x[1]))
    return df


# ---------------------------------------------------------------------------
# Table formatters
# ---------------------------------------------------------------------------

def format_phenotypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Output: Strain, Year, Test, Location, City, State, Phenotype, Value, Units
    Location = City_State composite (or 'Mean' for mean rows).
    """
    df = ensure_units_column(df)
    df = df.copy()

    # Rename phenotype values to DB names
    df["Phenotype"] = df["Phenotype"].apply(lambda v: PHENOTYPE_MAP.get(str(v).strip(), v))

    # Build Location composite
    def make_location(row):
        if str(row.get("City", "")).strip() in ("Mean", ""):
            return "Mean"
        state = str(row.get("State", "")).strip()
        city  = str(row.get("City",  "")).strip().replace(" ", "")
        return f"{city}_{state}" if state and state != "nan" else city

    df.insert(df.columns.get_loc("City"), "Location", df.apply(make_location, axis=1))

    # Final column order
    cols = ["Strain", "Year", "Test", "Location", "City", "State", "Phenotype", "Value", "Units"]
    ordered = [c for c in cols if c in df.columns]
    extras  = [c for c in df.columns if c not in cols]
    return df[ordered + extras]


def format_strains(df: pd.DataFrame, descriptive_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Output: Year, Test, Strain, OriginalStrain, Descriptive.Code,
            Unique.traits, Gen.Comp., Check
    """
    df = df.copy()

    # OriginalStrain = same as Strain for historical (no post-processing rename)
    df["OriginalStrain"] = df["Strain"]

    # Merge descriptive code if available
    if descriptive_df is not None and not descriptive_df.empty:
        avail = [c for c in ["Strain", "Test", "DescriptiveCode"] if c in descriptive_df.columns]
        if len(avail) == 3:
            df = df.merge(
                descriptive_df[avail].drop_duplicates(),
                on=["Strain", "Test"], how="left"
            )

    # Add missing columns
    for col in ["DescriptiveCode", "UniqueTraits", "GenComp"]:
        if col not in df.columns:
            df[col] = ""

    # Check = 1 if strain name ends with a MG designation in parens
    check_pat = re.compile(r'\(0{1,2}\)|\([IV]{1,3}\)\s*$', re.IGNORECASE)
    df["Check"] = df["Strain"].apply(lambda s: 1 if check_pat.search(str(s)) else 0)

    col_map = {
        "DescriptiveCode": "Descriptive.Code",
        "UniqueTraits":    "Unique.traits",
        "GenComp":         "Gen.Comp.",
    }
    df = df.rename(columns=col_map)

    cols = ["Year", "Test", "Strain", "OriginalStrain",
            "Descriptive.Code", "Unique.traits", "Gen.Comp.", "Check"]
    ordered = [c for c in cols if c in df.columns]
    extras  = [c for c in df.columns if c not in cols]
    return df[ordered + extras]


def format_parentage(df: pd.DataFrame) -> pd.DataFrame:
    """Output: Year, Test, Strain, Female, Male"""
    df = df.copy()

    if "Parentage" in df.columns:
        def split_cross(val):
            if not val or str(val).strip() in ("", "nan", "None"):
                return "", ""
            parts = re.split(r'\s+[xX]\s+', str(val).strip(), maxsplit=1)
            return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (parts[0].strip(), "")
        df["Female"] = df["Parentage"].apply(lambda v: split_cross(v)[0])
        df["Male"]   = df["Parentage"].apply(lambda v: split_cross(v)[1])

    cols = ["Year", "Test", "Strain", "Female", "Male"]
    ordered = [c for c in cols if c in df.columns]
    return df[ordered]


def build_locations_table(phenotypes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build LocationsTable from unique (Year, Test, City, State) in phenotypes.
    lat, lon, Conductor, PlantingDate, MaturityDate left NULL for historical data.
    """
    df = phenotypes_df[phenotypes_df["City"] != "Mean"].copy()
    locs = (
        df[["Year", "Test", "City", "State"]]
        .drop_duplicates()
        .sort_values(["Test", "City"])
        .reset_index(drop=True)
    )
    locs["lat"]          = None
    locs["lon"]          = None
    locs["Conductor"]    = None
    locs["PlantingDate"] = None
    locs["MaturityDate"] = None
    return locs[["Year", "Test", "City", "State",
                 "lat", "lon", "Conductor", "PlantingDate", "MaturityDate"]]


def build_checks_table(strains_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build checksTable from rows where Check=1.
    Phenotype = MG label extracted from strain name parenthetical first,
                falling back to test code if not present.
    RM left NULL for historical data.
    """
    checks = strains_df[strains_df["Check"] == 1].copy()
    if checks.empty:
        return pd.DataFrame(columns=["Year", "Test", "Strain", "OriginalStrain", "Phenotype", "RM"])

    def strain_to_mg(row):
        m = re.search(r'\((0{1,2}|[IV]{1,3})\)\s*$', str(row["Strain"]), re.IGNORECASE)
        if m:
            return f"MG {m.group(1).upper()}"
        return _test_to_mg(row["Test"])

    checks["Phenotype"] = checks.apply(strain_to_mg, axis=1)
    checks["RM"] = None

    # OriginalStrain = raw name from extraction (same as Strain for historical)
    if "OriginalStrain" not in checks.columns:
        checks["OriginalStrain"] = checks["Strain"]

    cols = ["Year", "Test", "Strain", "OriginalStrain", "Phenotype", "RM"]
    return checks[[c for c in cols if c in checks.columns]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Maturity DOY pipeline
# ---------------------------------------------------------------------------

def _mat_is_doy(v) -> bool:
    """True if value looks like an absolute DOY (>100)."""
    try:
        return float(str(v)) > 100
    except (ValueError, TypeError):
        return False


def _mat_is_offset(v) -> bool:
    """True if value looks like a ±day offset (-60..60)."""
    try:
        return abs(float(str(v).rstrip("*").lstrip("+"))) <= 60
    except (ValueError, TypeError):
        return False


def _parse_md_to_doy(s: str, year: int) -> int | None:
    """Parse 'M/D' or 'M-D' string to DOY for the given year. Returns None on failure."""
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})$', str(s).strip())
    if m:
        try:
            return _date(year, int(m.group(1)), int(m.group(2))).timetuple().tm_yday
        except ValueError:
            pass
    return None


def fix_maturity_values(ph: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Normalise raw Maturity values extracted from XLSX:
      - ISO-with-wrong-year (2026-MM-DD)  -> DOY using correct year
      - M-DD / M/DD text dates            -> DOY
      - Date-with-annotation (* 9/17)     -> DOY (strip annotation)
      - frost / Frost Kill / +N*          -> None
      - Integer offsets                   -> kept as-is (converted later via anchors)
    """
    mat_mask = ph["Phenotype"] == "Maturity"

    def _fix(v):
        if pd.isna(v):
            return v
        s = str(v).strip()
        if re.search(r'frost', s, re.IGNORECASE) or s == "--":
            return None
        # frost-annotated offset (e.g. "+5*") with no date
        if re.match(r'^[+-]?\d+\*$', s) and "/" not in s and "-" not in s.lstrip("-+"):
            return None
        # ISO wrong-year: 2026-MM-DD
        m = re.match(r'^2026-(\d{2})-(\d{2})', s)
        if m:
            doy = _parse_md_to_doy(f"{m.group(1)}/{m.group(2)}", year)
            return doy if doy else v
        # Date with frost annotation prefix: "* 9/17" or "*9/22"
        m = re.match(r'^\*\s*(\d{1,2})[/\-](\d{1,2})', s)
        if m:
            doy = _parse_md_to_doy(f"{m.group(1)}/{m.group(2)}", year)
            return doy if doy else v
        # M-DD or M/DD with optional trailing *
        s_clean = s.rstrip("*").strip()
        m = re.match(r'^(\d{1,2})[\-/](\d{1,2})$', s_clean)
        if m:
            doy = _parse_md_to_doy(f"{m.group(1)}/{m.group(2)}", year)
            return doy if doy else v
        return v  # integer offset or unknown — leave as-is

    ph = ph.copy()
    ph.loc[mat_mask, "Value"] = ph.loc[mat_mask, "Value"].apply(_fix)
    return ph


# Anchor record: {(test, city): {"doy": int, "ref_check": str, "anchor_date": str, "source": str}}
AnchorRecord = dict


def _detect_csv_anchors(ph: pd.DataFrame, checks_df: pd.DataFrame) -> AnchorRecord:
    """
    For each test, find the check variety whose post-fix Maturity values are
    all DOY-like (>100) — those are the reference checks stored as date cells
    in the XLSX.
    """
    mat = ph[ph["Phenotype"] == "Maturity"]
    check_strains = set(checks_df["Strain"]) if checks_df is not None else set()
    anchors: AnchorRecord = {}

    for test in mat["Test"].unique():
        tdf = mat[mat["Test"] == test]
        anchor_check = None
        for strain in check_strains:
            sdf = tdf[tdf["Strain"] == strain]
            doy_vals = sdf["Value"].dropna().apply(_mat_is_doy)
            if len(doy_vals) > 0 and doy_vals.sum() / len(doy_vals) > 0.5:
                anchor_check = strain
                break

        if anchor_check:
            for _, row in tdf[tdf["Strain"] == anchor_check].iterrows():
                if _mat_is_doy(row["Value"]):
                    key = (str(test).strip(), str(row["City"]).strip())
                    anchors[key] = {
                        "doy":          int(float(str(row["Value"]))),
                        "ref_check":    anchor_check,
                        "anchor_date":  str(row["Value"]),
                        "source":       "csv",
                    }

    return anchors


def _fill_gaps_from_doy(ph: pd.DataFrame, anchors: AnchorRecord) -> AnchorRecord:
    """
    For any (test, city) still without an anchor, use the median of all
    already-DOY Maturity values at that location as a gap-fill anchor.
    """
    mat = ph[ph["Phenotype"] == "Maturity"]
    doy_rows = mat[mat["Value"].apply(lambda v: _mat_is_doy(v) if not pd.isna(v) else False)].copy()
    doy_rows = doy_rows.copy()
    doy_rows["_doy"] = doy_rows["Value"].apply(lambda v: int(float(str(v))))
    filled = dict(anchors)

    for (test, city), grp in doy_rows.groupby(["Test", "City"]):
        key = (str(test).strip(), str(city).strip())
        if key not in filled:
            doy = int(grp["_doy"].median())
            # Pick the most common strain at this location with that DOY as "ref"
            ref = grp.loc[grp["_doy"] == doy, "Strain"].iloc[0] if len(grp) else "unknown"
            filled[key] = {
                "doy":         doy,
                "ref_check":   str(ref),
                "anchor_date": None,
                "source":      "gap_fill",
            }

    return filled


def _load_pdf_anchors(pdf_result: dict, year: int) -> AnchorRecord:
    """Parse Claude's JSON anchor response into AnchorRecord dict."""
    anchors: AnchorRecord = {}
    for entry in pdf_result.get("anchors", []):
        test      = str(entry["test"]).strip()
        ref_check = str(entry.get("reference_check", "")).strip()
        for loc in entry.get("locations", []):
            city        = str(loc["city"]).strip()
            anchor_date = str(loc.get("maturity_date", "")).strip()
            doy         = _parse_md_to_doy(anchor_date, year)
            if doy:
                anchors[(test, city)] = {
                    "doy":         doy,
                    "ref_check":   ref_check,
                    "anchor_date": anchor_date,
                    "source":      "pdf",
                }
    return anchors


def _query_pdf_for_anchors(pdf_path: Path, year: int, out_dir: Path) -> AnchorRecord:
    """Upload PDF and ask Claude for reference check maturity dates across all tests."""
    import anthropic

    CHECK_MATURITY_PROMPT = (
        "You are reading a NUST (North American Uniform Soybean Trial) annual report PDF.\n\n"
        "I need the ABSOLUTE maturity dates (shown as calendar dates like '9/5', '9/18', '10/1') "
        "for the PRIMARY REFERENCE CHECK variety in EVERY test in this report.\n\n"
        "Background: In each NUST test table the maturity column shows most strains as ± integer "
        "days relative to one primary reference check. That reference check has its maturity shown "
        "as an actual calendar date (M/D format) rather than as a ± integer.\n\n"
        "For each test, please:\n"
        "  1. Identify which check variety's dates appear as calendar dates in the maturity column.\n"
        "  2. List that variety's maturity date at EVERY test location within that test.\n\n"
        "Return ONLY valid JSON — no markdown fences:\n"
        '{"anchors": [{"test": "<e.g. UT-00>", "reference_check": "<variety name>", '
        '"locations": [{"city": "<city>", "state": "<state>", "maturity_date": "<M/D>"}]}]}\n\n'
        "Include ALL locations. Return only M/D calendar dates, not ± integers."
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  WARNING: ANTHROPIC_API_KEY not set — skipping PDF anchor extraction.")
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    print(f"  Uploading {pdf_path.name} ({pdf_path.stat().st_size // 1024} KB)...")
    with open(pdf_path, "rb") as fh:
        resp = client.beta.files.upload(file=(pdf_path.name, fh, "application/pdf"))
    file_id = resp.id
    print(f"  file_id: {file_id}")

    print("  Querying Claude for reference check maturity dates...")
    msg = client.beta.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "file", "file_id": file_id}},
            {"type": "text",     "text": CHECK_MATURITY_PROMPT},
        ]}],
        betas=["files-api-2025-04-14"],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)

    # Save raw JSON for re-use
    raw_path = out_dir / f"check_maturity_pdf_raw_{year}.json"
    raw_path.write_text(raw, encoding="utf-8")
    print(f"  Raw JSON -> {raw_path.name}")

    return _load_pdf_anchors(json.loads(raw), year)


def build_maturity_anchors_table(anchors: AnchorRecord, year: int,
                                 ph: pd.DataFrame) -> pd.DataFrame:
    """
    Build maturityAnchorsTable from the anchor dict.
    Joins State from phenotypesTable for completeness.
    Columns: Year, Test, ReferenceCheck, City, State, AnchorDate, AnchorDOY, Source
    """
    # Build City -> State lookup from phenotypes
    city_state = (
        ph[["City", "State"]].dropna(subset=["City"])
        .drop_duplicates()
        .set_index("City")["State"]
        .to_dict()
    )

    rows = []
    for (test, city), rec in sorted(anchors.items()):
        rows.append({
            "Year":           year,
            "Test":           test,
            "ReferenceCheck": rec["ref_check"],
            "City":           city,
            "State":          city_state.get(city, ""),
            "AnchorDate":     rec["anchor_date"] or "",
            "AnchorDOY":      rec["doy"],
            "Source":         rec["source"],
        })
    return pd.DataFrame(rows, columns=["Year","Test","ReferenceCheck","City","State",
                                       "AnchorDate","AnchorDOY","Source"])


def compute_maturity_doy_pipeline(
    ph: pd.DataFrame,
    checks_df: pd.DataFrame,
    year: int,
    out_dir: Path,
    pdf_path: Path = None,
    pdf_json_path: Path = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Full maturity DOY pipeline:
      1. Normalise raw values (fix_maturity_values)
      2. Detect CSV anchors from already-DOY check values
      3. Merge PDF anchors if provided (PDF > CSV > gap_fill priority)
      4. Gap-fill remaining (test, city) pairs
      5. Compute absolute DOY for all offset rows; average Mean rows
      6. Return (updated_phenotypes, anchors_table, verification_table)
    """
    print("\n  [Maturity DOY] Step 1: Normalising raw values...")
    ph = fix_maturity_values(ph, year)
    n_doy = (ph[ph["Phenotype"]=="Maturity"]["Value"].apply(
        lambda v: _mat_is_doy(v) if not pd.isna(v) else False)).sum()
    print(f"    {n_doy} values already in DOY format after normalisation")

    print("  [Maturity DOY] Step 2: Detecting CSV anchors from check DOY values...")
    anchors = _detect_csv_anchors(ph, checks_df)
    print(f"    {len(anchors)} anchors found from CSV")

    # Step 3: PDF anchors (override CSV where available — PDF is more authoritative)
    if pdf_json_path and pdf_json_path.exists():
        print(f"  [Maturity DOY] Step 3: Loading cached PDF anchors from {pdf_json_path.name}...")
        with open(pdf_json_path, encoding="utf-8") as f:
            pdf_result = json.load(f)
        pdf_anchors = _load_pdf_anchors(pdf_result, year)
        anchors.update(pdf_anchors)
        print(f"    {len(pdf_anchors)} PDF anchors loaded; total now {len(anchors)}")
    elif pdf_path and pdf_path.exists():
        print(f"  [Maturity DOY] Step 3: Extracting anchors from PDF {pdf_path.name}...")
        pdf_anchors = _query_pdf_for_anchors(pdf_path, year, out_dir)
        anchors.update(pdf_anchors)
        print(f"    {len(pdf_anchors)} PDF anchors extracted; total now {len(anchors)}")
    else:
        print("  [Maturity DOY] Step 3: No PDF provided — using CSV anchors only")

    print("  [Maturity DOY] Step 4: Gap-filling remaining (Test×City) from existing DOY values...")
    anchors = _fill_gaps_from_doy(ph, anchors)
    print(f"    Total anchors after gap-fill: {len(anchors)}")

    # Build anchor table (before applying, so it reflects what was used)
    anchors_table = build_maturity_anchors_table(anchors, year, ph)

    print("  [Maturity DOY] Step 5: Computing absolute DOY for offset rows...")
    mat_mask = ph["Phenotype"] == "Maturity"
    verif_rows = []

    for i, row in ph[mat_mask].iterrows():
        v    = row["Value"]
        test = str(row["Test"]).strip()
        city = str(row["City"]).strip()
        orig = v

        if pd.isna(v):
            computed, status = None, "null"
        elif _mat_is_doy(v):
            computed, status = int(float(str(v))), "already_doy"
        elif _mat_is_offset(v):
            rec = anchors.get((test, city))
            if rec:
                computed = int(rec["doy"] + float(str(v).rstrip("*").lstrip("+")))
                status   = "offset_converted"
            else:
                computed, status = None, "no_anchor"
        else:
            computed, status = None, "special"

        verif_rows.append({
            "Strain":           row["Strain"],
            "Year":             row["Year"],
            "Test":             test,
            "City":             city,
            "State":            row.get("State", ""),
            "OriginalMaturity": orig,
            "ComputedDOY":      computed,
            "Status":           status,
        })

    verif = pd.DataFrame(verif_rows)

    # Average Mean-row DOY from location-specific values per (Test, Strain)
    location_means = (
        verif[(verif["City"] != "Mean") & verif["ComputedDOY"].notna()]
        .groupby(["Test","Strain"])["ComputedDOY"].mean().round().astype(int)
    )
    for i, r in verif[verif["City"] == "Mean"].iterrows():
        if pd.isna(r["ComputedDOY"]):
            key = (r["Test"], r["Strain"])
            if key in location_means.index:
                verif.at[i, "ComputedDOY"] = int(location_means[key])
                verif.at[i, "Status"]      = "mean_averaged"

    # Apply computed DOY back to phenotypes
    doy_map = {
        (str(r.Strain), str(r.Year), str(r.Test), str(r.City)): r.ComputedDOY
        for r in verif.itertuples()
        if r.ComputedDOY is not None and not pd.isna(r.ComputedDOY)
    }
    ph = ph.copy()
    for i, row in ph[mat_mask].iterrows():
        key = (str(row["Strain"]), str(row["Year"]), str(row["Test"]), str(row["City"]))
        if key in doy_map:
            ph.at[i, "Value"] = int(doy_map[key])

    sc = verif["Status"].value_counts()
    print(f"    already_doy:      {sc.get('already_doy', 0)}")
    print(f"    offset_converted: {sc.get('offset_converted', 0)}")
    print(f"    mean_averaged:    {sc.get('mean_averaged', 0)}")
    print(f"    no_anchor:        {sc.get('no_anchor', 0)}")
    print(f"    null/special:     {sc.get('null', 0) + sc.get('special', 0)}")

    return ph, anchors_table, verif


# ---------------------------------------------------------------------------
# TEST_MAP
# ---------------------------------------------------------------------------
TEST_MAP = {
    "Group_1":  "UT-00",
    "Group_2":  "UT-0",
    "Group_3":  "UT-I",
    "Group_4":  "PT-I",
    "Group_5":  "UT-II",
    "Group_6":  "PT-II",
    "Group_7":  "UT-III",
    "Group_8":  "PT-III",
    "Group_9":  "UT-IV",
    "Group_10": "PT-IV",
}

TABLE_NAMES = ["phenotypes", "strains", "parentage", "descriptive", "disease", "summary"]


def renumber_groups(df: pd.DataFrame, offset: int, test_col: str = "Test") -> pd.DataFrame:
    def shift(val):
        m = re.fullmatch(r"Group_(\d+)", str(val))
        return f"Group_{int(m.group(1)) + offset}" if m else val
    df = df.copy()
    if test_col in df.columns:
        df[test_col] = df[test_col].apply(shift)
    return df


def apply_test_map(df: pd.DataFrame, test_map: dict, test_col: str = "Test") -> pd.DataFrame:
    df = df.copy()
    if test_col in df.columns:
        df[test_col] = df[test_col].apply(lambda v: test_map.get(v, v))
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Combine NUST extraction CSVs and apply TEST_MAP")
    parser.add_argument("--out_dir",   required=True)
    parser.add_argument("--year",      required=True)
    parser.add_argument("--no_remap",  action="store_true")
    parser.add_argument("--pdf",         default=None,
                        help="Source PDF for reference check maturity extraction")
    parser.add_argument("--pdf_json",   default=None,
                        help="Cached PDF anchor JSON from a previous run (skips re-upload)")
    parser.add_argument("--pdf_session", default=None,
                        help="pdf_session_{year}.json from pdf_pipeline.py (auto-locates anchor JSON)")
    parser.add_argument("--no_maturity_doy", action="store_true",
                        help="Skip maturity DOY conversion (leave values as extracted)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    year    = args.year

    prefixes = sorted({
        p.name.replace(f"_{t}.csv", "")
        for t in TABLE_NAMES
        for p in out_dir.glob(f"*_{t}.csv")
        if not p.name.startswith(f"combined_{year}")
    })

    print(f"Found {len(prefixes)} extracted file(s) in {out_dir}:")
    for p in prefixes:
        print(f"  {p}")
    if len(prefixes) < 2:
        print("Warning: only one source file found.")

    combined = {t: [] for t in TABLE_NAMES}

    for file_idx, prefix in enumerate(prefixes):
        group_offset = 0
        if file_idx > 0:
            f1_pheno = out_dir / f"{prefixes[0]}_phenotypes.csv"
            if f1_pheno.exists():
                f1_df = pd.read_csv(f1_pheno)
                f1_groups = [v for v in f1_df["Test"].unique()
                             if re.fullmatch(r"Group_\d+", str(v))]
                group_offset = (
                    max(int(re.fullmatch(r"Group_(\d+)", g).group(1)) for g in f1_groups)
                    if f1_groups else 0
                )

        for table in TABLE_NAMES:
            csv_path = out_dir / f"{prefix}_{table}.csv"
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path)
            if group_offset > 0:
                df = renumber_groups(df, group_offset)
            combined[table].append(df)
            print(f"  Loaded {csv_path.name}: {len(df)} rows (offset={group_offset})")

    print(f"\nWriting combined_{year}_*.csv ...")

    # Merge all tables first (raw)
    merged = {}
    for table, dfs in combined.items():
        if not dfs:
            merged[table] = pd.DataFrame()
            continue
        m = pd.concat(dfs, ignore_index=True).drop_duplicates()
        raw_path = out_dir / f"combined_{year}_{table}_raw.csv"
        m.to_csv(raw_path, index=False)
        print(f"  {raw_path.name}: {len(m)} rows")
        merged[table] = m

    if args.no_remap:
        print("\nDone (no_remap — skipped TEST_MAP and formatting).")
        return

    # Apply TEST_MAP to all tables
    remapped = {t: apply_test_map(df, TEST_MAP) for t, df in merged.items() if not df.empty}

    # ---- phenotypesTable + maturity DOY pipeline ----
    if "phenotypes" in remapped:
        ph = format_phenotypes(remapped["phenotypes"])

        if not args.no_maturity_doy:
            # Build checks_df for anchor detection (needs Check flag)
            desc_tmp = remapped.get("descriptive", pd.DataFrame())
            st_tmp   = format_strains(remapped.get("strains", pd.DataFrame()), desc_tmp)
            ck_tmp   = build_checks_table(st_tmp)

            # Resolve pdf_json from session file if provided
            resolved_pdf_json = args.pdf_json
            if not resolved_pdf_json and args.pdf_session:
                sess_path = Path(args.pdf_session)
                if sess_path.exists():
                    with open(sess_path, encoding="utf-8") as _sf:
                        _sess = json.load(_sf)
                    resolved_pdf_json = _sess.get("queries_completed", {}).get("anchors")
                    if resolved_pdf_json:
                        print(f"  [pdf_session] Using anchor JSON: {resolved_pdf_json}")

            pdf_path      = Path(args.pdf)             if args.pdf             else None
            pdf_json_path = Path(resolved_pdf_json)    if resolved_pdf_json    else None

            ph, anchors_table, verif = compute_maturity_doy_pipeline(
                ph, ck_tmp, int(year), out_dir,
                pdf_path=pdf_path, pdf_json_path=pdf_json_path,
            )

            anchors_path = out_dir / f"combined_{year}_maturityAnchorsTable.csv"
            anchors_table.to_csv(anchors_path, index=False)
            print(f"  combined_{year}_maturityAnchorsTable.csv: {len(anchors_table)} rows")

            verif_path = out_dir / f"combined_{year}_maturityVerification.csv"
            verif.to_csv(verif_path, index=False)
            print(f"  combined_{year}_maturityVerification.csv: {len(verif)} rows")

        ph.to_csv(out_dir / f"combined_{year}_phenotypesTable.csv", index=False)
        print(f"  combined_{year}_phenotypesTable.csv: {len(ph)} rows")

    # ---- strainsTable ----
    if "strains" in remapped:
        desc = remapped.get("descriptive", pd.DataFrame())
        st = format_strains(remapped["strains"], desc)
        st.to_csv(out_dir / f"combined_{year}_strainsTable.csv", index=False)
        print(f"  combined_{year}_strainsTable.csv: {len(st)} rows")

    # ---- parentageTable ----
    if "parentage" in remapped:
        pa = format_parentage(remapped["parentage"])
        pa.to_csv(out_dir / f"combined_{year}_parentageTable.csv", index=False)
        print(f"  combined_{year}_parentageTable.csv: {len(pa)} rows")

    # ---- locationsTable ----
    if "phenotypes" in remapped:
        ph_for_locs = ph if "ph" in dir() else format_phenotypes(remapped["phenotypes"])
        lc = build_locations_table(ph_for_locs)
        lc.to_csv(out_dir / f"combined_{year}_locationsTable.csv", index=False)
        print(f"  combined_{year}_locationsTable.csv: {len(lc)} rows")

    # ---- checksTable ----
    if "strains" in remapped:
        desc = remapped.get("descriptive", pd.DataFrame())
        st_for_checks = format_strains(remapped["strains"], desc)
        ck = build_checks_table(st_for_checks)
        ck.to_csv(out_dir / f"combined_{year}_checksTable.csv", index=False)
        print(f"  combined_{year}_checksTable.csv: {len(ck)} rows")

    # ---- pass-through tables (descriptive, disease, summary) ----
    for table in ["descriptive", "disease", "summary"]:
        if table in remapped and not remapped[table].empty:
            out_path = out_dir / f"combined_{year}_{table}.csv"
            remapped[table].to_csv(out_path, index=False)
            print(f"  combined_{year}_{table}.csv: {len(remapped[table])} rows")

    print("\nDone.")


if __name__ == "__main__":
    main()
