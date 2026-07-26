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
    python combine_nust_outputs.py --out_dir ./output_files/output_1980/ --year 1980
    python combine_nust_outputs.py --out_dir ./output_files/output_1980/ --year 1980 --no_remap
    python combine_nust_outputs.py --out_dir ./output_files/output_1980/ --year 1980 --pdf input_files/input_1980/1980_done.pdf
    python combine_nust_outputs.py --out_dir ./output_files/output_1980/ --year 1980 --pdf_json output_files/output_1980/check_maturity_pdf_raw_1980.json
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
            return str(doy) if doy else v
        # Date with frost annotation prefix: "* 9/17" or "*9/22"
        m = re.match(r'^\*\s*(\d{1,2})[/\-](\d{1,2})', s)
        if m:
            doy = _parse_md_to_doy(f"{m.group(1)}/{m.group(2)}", year)
            return str(doy) if doy else v
        # M-DD or M/DD with optional trailing *
        s_clean = s.rstrip("*").strip()
        m = re.match(r'^(\d{1,2})[\-/](\d{1,2})$', s_clean)
        if m:
            doy = _parse_md_to_doy(f"{m.group(1)}/{m.group(2)}", year)
            return str(doy) if doy else v
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
            _candidates = grp.loc[grp["_doy"] == doy, "Strain"]
            ref = _candidates.iloc[0] if len(_candidates) > 0 else grp["Strain"].iloc[0] if len(grp) > 0 else "unknown"
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
    # If response includes a leading text preamble before the JSON object
    # (seen with early-era PDFs where Claude narrates table discovery), strip
    # to just the {...} object that contains "anchors".
    if not raw.lstrip().startswith("{"):
        m = re.search(r'\{[\s\S]*"anchors"[\s\S]*\}', raw)
        if m:
            raw = m.group(0)

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
            ph.at[i, "Value"] = str(int(doy_map[key]))

    sc = verif["Status"].value_counts()
    print(f"    already_doy:      {sc.get('already_doy', 0)}")
    print(f"    offset_converted: {sc.get('offset_converted', 0)}")
    print(f"    mean_averaged:    {sc.get('mean_averaged', 0)}")
    print(f"    no_anchor:        {sc.get('no_anchor', 0)}")
    print(f"    null/special:     {sc.get('null', 0) + sc.get('special', 0)}")

    return ph, anchors_table, verif


# ---------------------------------------------------------------------------
# TEST_MAPS — per-year Group_N → NUST code registries
# ---------------------------------------------------------------------------
# Group structure varies by year; there is no valid generic fallback.
# Every year must have an explicit entry here or supply --test_map <json>.
# Unknown years abort with a clear error rather than silently mis-mapping.
TEST_MAPS: dict[str, dict[str, str]] = {
    "1942": {
        # 4 tp2 groups, no PTs yet. Reference checks (from PDF / "X matured" rows):
        # MG I (Mandarin), MG II (Illini), MG III (Illini), MG IV (Gibson).
        "Group_1": "UT-I",
        "Group_2": "UT-II",
        "Group_3": "UT-III",
        "Group_4": "UT-IV",
    },
    "1943": {
        # 4 tp2 groups, no PTs. Richland enters as MG II reference.
        # MG I (Mandarin), MG II (Richland), MG III (Illini), MG IV (Gibson).
        "Group_1": "UT-I",
        "Group_2": "UT-II",
        "Group_3": "UT-III",
        "Group_4": "UT-IV",
    },
    "1944": {
        # 10 tp2 in raw XLSX -> 6 after fixes/preprocess_1944_tp2.py clears
        # 4 noise markers (Summary of agronomic / Five-year summary / Summary of yields).
        # Real entries: R3 (UT-0), R231 (UT-I), R531 (UT-II), R1098 (UT-III),
        # R1521 (UT-IV), R1734 (PT-IV) — matches PDF's 6 tests.
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "UT-II",
        "Group_4": "UT-III",
        "Group_5": "UT-IV",
        "Group_6": "PT-IV",
    },
    "1945": {
        # 18 tp2 in raw XLSX -> 5 after fixes/preprocess_1945_tp2.py clears 13
        # mislabeled "tp2"s that are actually summary/ANOVA/per-loc tables.
        # PDF lists 6 tests (5 UT + 1 PT-IV) but PT-IV reuses UT-IV's roster
        # with no separate parentage table; per-location PT-IV data is merged
        # with UT-IV in this extraction. PT-IV split is a deferred open item.
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "UT-II",
        "Group_4": "UT-III",
        "Group_5": "UT-IV",
    },
    "1946": {
        # 5 tp2 groups: UT-0, UT-I, UT-II, UT-III, UT-IV. No PTs in 1946.
        # MG 0 / MG I (Mand. (Ott.)), MG II (Richland), MG III (Illini), MG IV (Gibson).
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "UT-II",
        "Group_4": "UT-III",
        "Group_5": "UT-IV",
    },
    "1947": {
        # 8 tp2 groups: UT/PT pairs for MG 0 and MG I, plus singletons for MG II-IV.
        # PDF lists 9 tests (PT-IV appears twice); two PT-IV blocks merged into Group_8.
        # Refs: Mandarin (Ott.) for 0/I, Richland for II, Lincoln for III, Gibson for IV.
        "Group_1": "UT-0",
        "Group_2": "PT-0",
        "Group_3": "UT-I",
        "Group_4": "PT-I",
        "Group_5": "UT-II",
        "Group_6": "UT-III",
        "Group_7": "UT-IV",
        "Group_8": "PT-IV",
    },
    "1948": {
        # 9 tp2 groups: UT/PT pairs for MG 0, MG I, MG III, MG IV, plus UT-II.
        # Refs: Mandarin (Ottawa) for 0/I, Richland for II, Lincoln for III, Gibson for IV.
        "Group_1": "UT-0",
        "Group_2": "PT-0",
        "Group_3": "UT-I",
        "Group_4": "PT-I",
        "Group_5": "UT-II",
        "Group_6": "UT-III",
        "Group_7": "PT-III",
        "Group_8": "UT-IV",
        "Group_9": "PT-IV",
    },
    "1949": {
        # 8 tp2 groups: UT/PT pairs for MG 0, MG I, MG IV; singletons for UT-II, UT-III.
        # Hawkeye replaces Richland as MG II ref; Wabash replaces Gibson as MG IV ref.
        "Group_1": "UT-0",
        "Group_2": "PT-0",
        "Group_3": "UT-I",
        "Group_4": "PT-I",
        "Group_5": "UT-II",
        "Group_6": "UT-III",
        "Group_7": "UT-IV",
        "Group_8": "PT-IV",
    },
    "1941": {
        # NUST inaugural year. 3 tp2 → 3 entry groups, no PTs (added later in program).
        # MG mapping derived from maturity reference checks in raw XLSX (the "X matured"
        # row with calendar dates per location identifies the reference, which the PDF
        # labels as Group II/III/IV):
        #   Group_1 reference "Illini matured"          → PDF Group II → UT-II
        #   Group_2 reference "Illini or Dunfield matured" → PDF Group III → UT-III
        #   Group_3 reference "Gibson matured"          → PDF Group IV → UT-IV
        # Pre-MG-I era: NUST started with only MG II/III/IV; earlier MGs were added
        # in later years as the program expanded northward.
        # Per-location traits: YIELD, MATURITY, LODGING, HEIGHT, SEED QUALITY (5).
        # Summary-only (tp4): PROTEIN, OIL, IODINE NUMBER OF OIL (legacy phenotype).
        # No YIELD RANK, no SEED SIZE (g/100), no SEED WEIGHT (cg) in 1941.
        "Group_1": "UT-II",
        "Group_2": "UT-III",
        "Group_3": "UT-IV",
    },
    "1950": {
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "UT-II",
        "Group_4": "UT-III",
        "Group_5": "PT-III",
        "Group_6": "UT-IV",
        "Group_7": "PT-IV",
    },
    "1963": {
        # Group_1 contains both UT-00 and PT-00 (XLSX structural merge — no tp2 boundary).
        # Run fixes/split_ut00_pt00_1963.py after combine to recover PT-00 rows.
        "Group_1":  "UT-00",
        "Group_2":  "UT-0",
        "Group_3":  "PT-0",
        "Group_4":  "UT-I",
        "Group_5":  "PT-I",
        "Group_6":  "UT-II",
        "Group_7":  "PT-II",
        "Group_8":  "UT-III",
        "Group_9":  "PT-III",
        "Group_10": "UT-IV",
        "Group_11": "PT-IV",
    },
    "1966": {
        # 14 tp2 in original XLSX; fixes/preprocess_1966_tp2.py clears tp2@574 (PT-0 disease
        # sub-table) and tp2@2672 (special supplement) → 12 real tests.
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "PT-II",
        "Group_9":  "UT-III",
        "Group_10": "PT-III",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1967": {
        # 13 tp2 in original; fixes/preprocess_1967_tp2.py clears tp2@2757 (II-42-37
        # special supplement) → 12 real tests.
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "PT-II",
        "Group_9":  "UT-III",
        "Group_10": "PT-III",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1968": {
        # XLSX had malformed "tp" (not "tp2") at row 380 for UT-0 start, plus 2 stray tp2 at
        # rows 3142/3178 (special supplements). fixes/preprocess_1968_tp2.py fixes "tp"→"tp2"
        # and clears the supplements → 12 real tests.
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "PT-II",
        "Group_9":  "UT-III",
        "Group_10": "PT-III",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1969": {
        # 12 tp2 in original; fixes/preprocess_1969_tp2.py clears tp2@3385 (Pridesoy II
        # supplement) → 11 real tests. NOTE: 1969 has no PT-II (PDF only lists 11 groups).
        # Known data quality issues at tp2@382 (UT-0, "QUALITY TOO POOR TO EDIT") and
        # tp2@1248 (PT-I, "Poor image - not edited") — extracted data for these tests degraded.
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "UT-III",
        "Group_9":  "PT-III",
        "Group_10": "UT-IV",
        "Group_11": "PT-IV",
    },
    "1970": {
        # 14 tp2 in original; fixes/preprocess_1970_tp2.py clears tp2@1 (special breeding-line
        # summary) and tp2@4506 (Yield/Rank/Maturity summary) → 12 real tests.
        # Modern era (transitional → modern boundary).
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "PT-II",
        "Group_9":  "UT-III",
        "Group_10": "PT-III",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1951": {
        # 6 tp2 → 5 after fixes/preprocess_1951_tp2.py clears tp2@1955 (disease table).
        # 5 tests: UT-0 through UT-IV (no PTs in 1951).
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "UT-II",
        "Group_4": "UT-III",
        "Group_5": "UT-IV",
    },
    "1952": {
        # 5 tp2 — clean. 5 tests UT-0 through UT-IV (no PTs).
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "UT-II",
        "Group_4": "UT-III",
        "Group_5": "UT-IV",
    },
    "1953": {
        # 5 tp2 — clean. 5 tests UT-0 through UT-IV (no PTs).
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "UT-II",
        "Group_4": "UT-III",
        "Group_5": "UT-IV",
    },
    "1954": {
        # 7 tp2 → 6 after fixes/preprocess_1954_tp2.py clears tp2@40 (Mean SUMMARY).
        # PT-I added in 1954 (first preliminary test introduced).
        "Group_1": "UT-0",
        "Group_2": "UT-I",
        "Group_3": "PT-I",
        "Group_4": "UT-II",
        "Group_5": "UT-III",
        "Group_6": "UT-IV",
    },
    "1955": {
        # 7 tp2, no preprocessing. Era pattern: no UT-00/PT-0/PT-I, PT-II and PT-III paired,
        # no PT-IV (similar to 1950 but with PT-II added). Check varieties:
        # Capital/Chippewa=UT-0, Blackhawk/Chippewa=UT-I, Adams/Blackhawk=UT-II/PT-II,
        # Clark/Dunfield=UT-III/PT-III, Chief/Clark=UT-IV.
        "Group_1":  "UT-0",
        "Group_2":  "UT-I",
        "Group_3":  "UT-II",
        "Group_4":  "PT-II",
        "Group_5":  "UT-III",
        "Group_6":  "PT-III",
        "Group_7":  "UT-IV",
    },
    "1956": {
        # 9 tp2, no preprocessing. Adds PT-I and PT-IV pairings.
        "Group_1":  "UT-0",
        "Group_2":  "UT-I",
        "Group_3":  "PT-I",
        "Group_4":  "UT-II",
        "Group_5":  "PT-II",
        "Group_6":  "UT-III",
        "Group_7":  "PT-III",
        "Group_8":  "UT-IV",
        "Group_9":  "PT-IV",
    },
    "1957": {
        # CORRECTED 2026-06-29 (user-confirmed: MG-00 did NOT begin until 1958 — 1958 UT-00 =
        # Acme/Crest/Manitoba; 1957 "UT-00" = Capital/Grant/Mandarin = MG-0). The first two
        # Group-0 sections ("UNIFORM TEST GROUP 0" + "UNIFORM AND PRELIMINARY TEST GROUP 0") are
        # UT-0 + PT-0 (matching groups I-IV), NOT UT-00 + UT-0. Group_11 = the real group-IV
        # preliminary (PT-IV), previously orphaned. (F4U relabeled live by 108/110.)
        "Group_1":  "UT-0",
        "Group_2":  "PT-0",
        "Group_3":  "UT-I",
        "Group_4":  "PT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-II",
        "Group_7":  "UT-III",
        "Group_8":  "PT-III",
        "Group_9":  "UT-IV",
        "Group_10": "PT-IV",
        "Group_11": "PT-IV",
    },
    "1958": {
        # 13 tp2 → 9 after fixes/preprocess_1958_tp2.py clears 4 sub-tables.
        # Adds UT-00 first (Acme/Crest pair). PT-I missing this year.
        "Group_1":  "UT-00",
        "Group_2":  "UT-0",
        "Group_3":  "UT-I",
        "Group_4":  "UT-II",
        "Group_5":  "PT-II",
        "Group_6":  "UT-III",
        "Group_7":  "PT-III",
        "Group_8":  "UT-IV",
        "Group_9":  "PT-IV",
    },
    "1959": {
        # 23 tp2 → 10 after fixes/preprocess_1959_tp2.py clears 13 sub-tables (lots of
        # SUMMARY/Mean/No-of-Tests/Disease markers). Modern-era-like 10-test structure
        # arrives in 1959 with full UT/PT pairing for MG 00, I, II, III, IV. No PT-0.
        # VERIFIED 2026-06-29: this map matches Green Sheet1 tp2 document order 10/10
        # (rosters cross-checked vs the Red-PDF group title pages). The on-disk F4U was
        # STALE — generated by an OLDER buggy run (scrambled codes + a leaked, dropped
        # "Group_11") and never regenerated; data_prep/stage2_corpus/108_relabel_1959.py
        # relabeled it to this (correct) assignment. A fresh regen here reproduces it.
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "UT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-II",
        "Group_7":  "UT-III",
        "Group_8":  "PT-III",
        "Group_9":  "UT-IV",
        "Group_10": "PT-IV",
    },
    "1960": {
        # 12 tp2 markers, all parentage tables — clean UT/PT pairing for all 6 MGs.
        # No preprocessing needed.
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "PT-II",
        "Group_9":  "UT-III",
        "Group_10": "PT-III",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1961": {
        # 10 tp2 markers — XLSX missing PT-00 and PT-III (PDF presumably has them).
        # No preprocessing needed; just a mapping that skips those tests.
        "Group_1":  "UT-00",
        "Group_2":  "UT-0",
        "Group_3":  "PT-0",
        "Group_4":  "UT-I",
        "Group_5":  "PT-I",
        "Group_6":  "UT-II",
        "Group_7":  "PT-II",
        "Group_8":  "UT-III",
        "Group_9":  "UT-IV",
        "Group_10": "PT-IV",
    },
    "1962": {
        # 11 tp2 → 10 after fixes/preprocess_1962_tp2.py clears tp2@1961 (SUMMARY).
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
    },
    "1964": {
        # 14 tp2 → 12 after fixes/preprocess_1964_tp2.py clears tp2@32 (SUMMARY)
        # and tp2@1098 (OTH stray marker between UT-I and PT-I).
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "PT-II",
        "Group_9":  "UT-III",
        "Group_10": "PT-III",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1965": {
        # Transitional era. XLSX originally had 8 tp2 markers but PDF has 10 tests.
        # fixes/preprocess_1965_tp2.py inserts tp2 at rows 798/1114/1840 (parentage
        # tables for UT-I, PT-I, UT-III lacking tp2 prefix) and clears tp2@2244
        # (a UT-IV regional-history sub-table opener that was wrongly tp2-marked).
        # Backup at "input_files/input_1965/1965-Sojabone (0-101 OR).xlsx.orig_no_extra_tp2".
        # Check varieties: Acme/Flambeau=UT-00 & PT-00, Grant/Merit=UT-0, Chippewa/Hark=UT-I,
        # Amsoy/Harosoy=UT-II, Shelby/Wayne=UT-III, Bellatti L-263/Clark=UT-IV.
        # Note: 1965 has no PT-0 and no PT-IV in PDF (only 4 preliminary tests).
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "UT-I",
        "Group_5":  "PT-I",
        "Group_6":  "UT-II",
        "Group_7":  "PT-II",
        "Group_8":  "UT-III",
        "Group_9":  "PT-III",
        "Group_10": "UT-IV",
    },
    "1971": {
        # Single XLSX file (Sojabone-1971 (0-86 OR).xlsx), 12 tp2 markers.
        # Test codes derived from check varieties at each tp2 marker:
        #   Altona/Flambeau=UT-00, Morsoy/Norman=PT-00, Clay/Merit=UT-0, Clay/Merit=PT-0,
        #   Chippewa64/SL8=UT-I, Chippewa64/Hark=PT-I, Amsoy71/Beeson=UT-II,
        #   Amsoy71/Corsoy=PT-II, Calland/Wayne=UT-III, Calland/Kanrich=PT-III,
        #   Cutler/Cutler71=UT-IV, Clark63/Cutler71=PT-IV.
        "Group_1":  "UT-00",
        "Group_2":  "PT-00",
        "Group_3":  "UT-0",
        "Group_4":  "PT-0",
        "Group_5":  "UT-I",
        "Group_6":  "PT-I",
        "Group_7":  "UT-II",
        "Group_8":  "PT-II",
        "Group_9":  "UT-III",
        "Group_10": "PT-III",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1972": {
        # File 2 groups (1–3) are renumbered +8 by the combine step → Group_9–11.
        # GlobalParentage is not listed here — apply_test_map passes it through unchanged.
        "Group_1":  "UT-00",
        "Group_2":  "UT-0",
        "Group_3":  "PT-0",
        "Group_4":  "UT-I",
        "Group_5":  "PT-I",
        "Group_6":  "UT-II",
        "Group_7":  "PT-II",
        "Group_8":  "UT-III",
        "Group_9":  "PT-III",
        "Group_10": "UT-IV",
        "Group_11": "PT-IV",
    },
    "1973": {
        # File 1 (0-67 OR) has 8 groups; File 2 (68-97 OR) has 3 groups renumbered +8 → Group_9-11.
        # Derived from XLSX check varieties: Altona/Norman=UT-00, Clay/Merit=UT-0, Swift/Wilkin=PT-0,
        # Chippewa64/Hark=UT-I, Hark/Steele=PT-I, Amsoy71/Beeson=UT-II, Beeson/Corsoy=PT-II,
        # Calland/Wayne=UT-III, Calland/Wayne=PT-III (file2), Bonus/Cutler71=UT-IV, Cutler71/Kent=PT-IV.
        # No PT-00 in XLSX (PDF model mislabeled PT-0 section as PT-00).
        "Group_1":  "UT-00",
        "Group_2":  "UT-0",
        "Group_3":  "PT-0",
        "Group_4":  "UT-I",
        "Group_5":  "PT-I",
        "Group_6":  "UT-II",
        "Group_7":  "PT-II",
        "Group_8":  "UT-III",
        "Group_9":  "PT-III",
        "Group_10": "UT-IV",
        "Group_11": "PT-IV",
    },
    "1974": {
        # File 1 (0-56 OR) has 6 groups; File 2 (57-111 OR) has 4 groups renumbered +6 → Group_7-10.
        # NOTE: File 2 originally shipped with only 2 tp2 markers but contains 4 tests; tp2 markers
        # were inserted at rows 997 (before UT-IV) and 1629 (before PT-IV) by
        # fixes/preprocess_1974_f2_add_tp2.py. Backup at "...orig_no_tp2".
        # XLSX is still missing PT-I from file 1 (genuine data gap; present in PDF).
        # Derived from XLSX check varieties: Altona/Norman=UT-00, Clay/Evans=UT-0, Clay/Swift=PT-0,
        # Hark/Hodgson=UT-I, Amsoy71/Beeson=UT-II, Beeson/Corsoy=PT-II,
        # Calland/Wayne=UT-III, Wayne/Williams=PT-III, Bonus/Cutler71/Kent=UT-IV, Cutler71/Kent=PT-IV.
        "Group_1":  "UT-00",
        "Group_2":  "UT-0",
        "Group_3":  "PT-0",
        "Group_4":  "UT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-II",
        "Group_7":  "UT-III",
        "Group_8":  "PT-III",
        "Group_9":  "UT-IV",
        "Group_10": "PT-IV",
    },
    "1976": {
        # Same 10-group structure as 1980 (confirmed from extract_test_map_pdf.py output)
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
    },
    "1977": {
        # Same 10-group structure as 1976/1980 (confirmed from PDF test map)
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
    },
    "1978": {
        # Same 10-group structure as 1976/1977/1980 (confirmed from PDF test map)
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
    },
    "1979": {
        # Same 10-group structure as 1976–1978/1980 (confirmed from PDF test map)
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
    },
    "1980": {
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
    },
    "1981": {
        # File 1 (1-102 OR) groups 1-7; File 2 (103-178 OR) groups renumbered +7 → 8-12
        "Group_1":  "UT-00",
        "Group_2":  "UT-O",
        "Group_3":  "UT-I",
        "Group_4":  "PT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-IIA",
        "Group_7":  "PT-IIB",
        "Group_8":  "UT-III",
        "Group_9":  "PT-IIIA",
        "Group_10": "PT-IIIB",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1982": {
        # File 1 (1-115 OR) groups 1-7; File 2 (116-211 OR) groups renumbered → 8-12
        "Group_1":  "UT-00",
        "Group_2":  "UT-O",
        "Group_3":  "UT-I",
        "Group_4":  "PT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-IIA",
        "Group_7":  "PT-IIB",
        "Group_8":  "UT-III",
        "Group_9":  "PT-IIIA",
        "Group_10": "PT-IIIB",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1983": {
        # File 1 (1-110 OR) groups 1-7; File 2 (111-215 OR) groups renumbered → 8-12
        "Group_1":  "UT-00",
        "Group_2":  "UT-O",
        "Group_3":  "UT-I",
        "Group_4":  "PT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-IIA",
        "Group_7":  "PT-IIB",
        "Group_8":  "UT-III",
        "Group_9":  "PT-IIIA",
        "Group_10": "PT-IIIB",
        "Group_11": "UT-IV",
        "Group_12": "PT-IV",
    },
    "1984": {
        # File 1 (1-88 OR) groups 1-?; File 2 (89-186 OR) renumbered
        # PT-IV split into PT-IVA + PT-IVB starting 1984 (13 groups)
        "Group_1":  "UT-00",
        "Group_2":  "UT-O",
        "Group_3":  "UT-I",
        "Group_4":  "PT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-IIA",
        "Group_7":  "PT-IIB",
        "Group_8":  "UT-III",
        "Group_9":  "PT-IIIA",
        "Group_10": "PT-IIIB",
        "Group_11": "UT-IV",
        "Group_12": "PT-IVA",
        "Group_13": "PT-IVB",
    },
    "1985": {
        # File 1 (1-104 OR) groups 1-?; File 2 (105-220 OR) renumbered
        # Same 13-group structure as 1984
        "Group_1":  "UT-00",
        "Group_2":  "UT-O",
        "Group_3":  "UT-I",
        "Group_4":  "PT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-IIA",
        "Group_7":  "PT-IIB",
        "Group_8":  "UT-III",
        "Group_9":  "PT-IIIA",
        "Group_10": "PT-IIIB",
        "Group_11": "UT-IV",
        "Group_12": "PT-IVA",
        "Group_13": "PT-IVB",
    },
    "1986": {
        # File 1 (1-101 OR) groups 1-?; File 2 (102-201 OR) renumbered
        # Same 13-group structure as 1984/1985
        "Group_1":  "UT-00",
        "Group_2":  "UT-O",
        "Group_3":  "UT-I",
        "Group_4":  "PT-I",
        "Group_5":  "UT-II",
        "Group_6":  "PT-IIA",
        "Group_7":  "PT-IIB",
        "Group_8":  "UT-III",
        "Group_9":  "PT-IIIA",
        "Group_10": "PT-IIIB",
        "Group_11": "UT-IV",
        "Group_12": "PT-IVA",
        "Group_13": "PT-IVB",
    },
    "1975": {
        # PDF-direct extraction via scripts/extract_nust_pdf.py (Sojabone XLSX
        # never existed for 1975; sole missing year in the 1941-1988 XLSX-era
        # corpus). PDF extractor emits canonical test codes directly, so this
        # map is identity for documentation purposes — apply_test_map() falls
        # back to passing values through unchanged.
        # Roster confirms 12 tests: 6 UT (00, 0, I, II, III, IV) + 6 PT (00,
        # 0, I, II, III, IV). Note: 1975 has PT-00 and PT-0 (preliminary tests
        # at early MGs) which neither 1990 nor earlier years had.
        "UT-00":  "UT-00",
        "PT-00":  "PT-00",
        "UT-0":   "UT-0",
        "PT-0":   "PT-0",
        "UT-I":   "UT-I",
        "PT-I":   "PT-I",
        "UT-II":  "UT-II",
        "PT-II":  "PT-II",
        "UT-III": "UT-III",
        "PT-III": "PT-III",
        "UT-IV":  "UT-IV",
        "PT-IV":  "PT-IV",
    },
    "1990": {
        # PDF-direct extraction via scripts/extract_nust_pdf.py (no Sojabone XLSX
        # ever existed for 1990; master CSV had only 7 PT entries and zero UT).
        # The PDF extractor emits canonical test codes directly in the "Test"
        # column, so this map is identity for documentation purposes only —
        # apply_test_map() falls back to passing values through unchanged.
        # Roster confirms 13 tests: 6 UT (00, 0, I, II, III, IV) + 7 PT
        # (I, IIA, IIB, IIIA, IIIB, IVA, IVB).
        "UT-00":   "UT-00",
        "UT-0":    "UT-0",
        "UT-I":    "UT-I",
        "PT-I":    "PT-I",
        "UT-II":   "UT-II",
        "PT-IIA":  "PT-IIA",
        "PT-IIB":  "PT-IIB",
        "UT-III":  "UT-III",
        "PT-IIIA": "PT-IIIA",
        "PT-IIIB": "PT-IIIB",
        "UT-IV":   "UT-IV",
        "PT-IVA":  "PT-IVA",
        "PT-IVB":  "PT-IVB",
    },
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
# STRAIN_ALIASES — canonicalize OCR variants of the same strain name
# ---------------------------------------------------------------------------
# Applied globally (every year). Keys are regex patterns; values are canonical
# replacements. Use ^...$ anchors and \\. for literal dots so abbreviations
# like "Mand. (Ott.)" don't accidentally match longer strings.
#
# Conservative scope: only entries where the OCR/abbreviation variant clearly
# refers to a single canonical strain. Don't add entries unless you've
# verified the variant appears as a check or reference (not as a distinct
# experimental line).
STRAIN_ALIASES = {
    # Mandarin (Ottawa) — historical MG 0/I reference check (1944-1949+).
    # 6 OCR/abbreviation variants observed in the 1941-1949 batch.
    r"^Mandarin \(Ott\.?\)$":   "Mandarin (Ottawa)",
    r"^Mand\. \(Ott\.?\)$":     "Mandarin (Ottawa)",
    r"^Mand\. \(Ottawa\)$":     "Mandarin (Ottawa)",
    r"^Mendarin \(Ottawa\)$":   "Mandarin (Ottawa)",
    r"^Mandarin- \(Ott\.?\)$":  "Mandarin (Ottawa)",
    r"^Mandarin \(ott\.?\)$":   "Mandarin (Ottawa)",
    # "Mandarin (Ott." — missing closing paren, seen in 1946.
    r"^Mandarin \(Ott\.$":      "Mandarin (Ottawa)",

    # Bavender Special — MG IV strain (1946-1949). 3 OCR variants observed.
    r"^Bav\. Spec\.$":          "Bavender Special",
    r"^Bavender Spec\.$":       "Bavender Special",
    r"^Bavender Specail$":      "Bavender Special",

    # Wis. Manchu line variants (carry-over from 1941 fix_ocr_1941.py; also
    # applies to 1942+). Both lines collapsed to no-space full form.
    r"^Wis\.Man\.\s*3$":        "Wis.Manchu3",
    r"^Wis\.\s*Man\.\s*3$":     "Wis.Manchu3",
    r"^Wis\.\s*Manchu\s*3$":    "Wis.Manchu3",
    r"^Wis\.Man\.\s*606$":      "Wis.Manchu606",
    r"^Wis\.\s*Man\.\s*606$":   "Wis.Manchu606",
    r"^Wis\.\s*Manchu\s*606$":  "Wis.Manchu606",

    # Montreal Manchu variants (1944-1948).
    r"^Mont\. Manchu$":         "Montreal Manchu",
    r"^Mont\.Man\.$":           "Montreal Manchu",
}


def apply_strain_aliases(df: pd.DataFrame, strain_col: str = "Strain") -> tuple[pd.DataFrame, int]:
    """Canonicalize OCR/abbreviation variants of strain names. Returns (df, n_changed)."""
    if strain_col not in df.columns:
        return df, 0
    df = df.copy()
    original = df[strain_col].astype(str)
    out = original.copy()
    for pattern, canonical in STRAIN_ALIASES.items():
        out = out.str.replace(pattern, canonical, regex=True)
    n_changed = int((out != original).sum())
    df[strain_col] = out
    return df, n_changed


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
    parser.add_argument("--test_map", default=None,
                        help="Path to JSON file with {Group_N: NUST_code} mapping (overrides built-in)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    year    = args.year

    if args.test_map:
        with open(args.test_map, encoding="utf-8") as _f:
            _raw = json.load(_f)
        # Handle extract_test_map_pdf.py structured format: {"year":..., "groups":[{group_number, test_code},...]}
        if "groups" in _raw and isinstance(_raw["groups"], list):
            test_map = {f"Group_{g['group_number']}": g["test_code"] for g in _raw["groups"]}
            print(f"  [TEST_MAP] Loaded from {args.test_map} (structured format): {test_map}")
        else:
            # Flat format: {"Group_1": "UT-00", ...}
            test_map = _raw
            print(f"  [TEST_MAP] Loaded from {args.test_map}: {list(test_map.keys())}")
    elif year in TEST_MAPS:
        test_map = TEST_MAPS[year]
        print(f"  [TEST_MAP] Using built-in map for {year} ({len(test_map)} groups)")
    else:
        raise SystemExit(
            f"ERROR: No TEST_MAP registered for year {year}.\n"
            f"Run QC roster mode on the PDF, verify group→test assignments, then either:\n"
            f"  (a) add the year to TEST_MAPS in scripts/combine_nust_outputs.py, or\n"
            f"  (b) pass --test_map <path/to/{year}_test_map.json>"
        )

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

    # Apply strain-alias canonicalization to all tables (Mandarin (Ottawa) variants,
    # Bavender Special, Wis.Manchu, Montreal Manchu — see STRAIN_ALIASES dict).
    print()
    n_alias_total = 0
    for table_name, df in merged.items():
        if df.empty:
            continue
        df_fixed, n = apply_strain_aliases(df)
        merged[table_name] = df_fixed
        if n:
            print(f"  [STRAIN_ALIAS] {table_name}: {n} rows canonicalized")
            n_alias_total += n
    if n_alias_total == 0:
        print("  [STRAIN_ALIAS] no canonicalizations needed")
    else:
        print(f"  [STRAIN_ALIAS] total: {n_alias_total} rows across all tables")

    # Apply TEST_MAP to all tables
    remapped = {t: apply_test_map(df, test_map) for t, df in merged.items() if not df.empty}

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
