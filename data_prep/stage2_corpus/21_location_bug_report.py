"""
21_location_bug_report.py
=========================
Surface LOCATION-PARSING BUGS in the corpus for manual verification against the
source PDFs/XLSX — rows where the City/State fields are clearly mangled (not a
normal spelling variant the canonical map already handles). For each bug it lists
the YEAR and TRIAL (Test) + row counts so the user can locate and check the source.

Bug categories (City/State, not the trait columns):
  soil_in_state        : State holds a soil type (CLAY/LOAM/MINERAL/MUCK) — same site,
                         soil sub-plot mis-parsed into State (e.g. Portageville/CLAY).
  reversed_state_city  : City is a STATE name and State is the real city
                         (e.g. Iowa/STUART = Stuart IA; Kansas/MANHATTAN).
  code_in_state        : State is a rep/block/number/single-letter token (1, B, I, ...).
  summary_in_state     : State is a summary marker (MEAN/RANK/AVERAGE) — a summary row
                         mis-parsed into the location (e.g. Yield/RANK, Central/MEAN).
  pseudo_city          : City itself is a non-location (Composite of N Locations, loc{n},
                         Mean, Yield, col C).
  junk_state           : State is some other non-state string.
NOTE: this REPORTS only — it changes nothing. YieldRank the trait is untouched.

Output: analysis/data/analysis_results/Corpus_QC/location_bugs_to_check.{csv,md}
"""
import sys
import re
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
OUTDIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"

VALID_STATES = {  # full US + Canada postal codes (both ONT/ON and MAN/MB conventions)
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT",
    "ONT", "MAN",
}
STATE_WORD = {  # full / abbreviated state names that resolve to a valid code
    "ill": "IL", "ind": "IN", "wis": "WI", "wisc": "WI", "mich": "MI", "minn": "MN",
    "kans": "KS", "kan": "KS", "neb": "NE", "nebr": "NE", "ind.": "IN", "iowa": "IA",
    "ohio": "OH", "ont": "ONT", "man": "MAN", "que": "QC", "sas": "SK", "del": "DE",
    "indiana": "IN", "illinois": "IL", "michigan": "MI", "minnesota": "MN", "missouri": "MO",
    "wisconsin": "WI", "nebraska": "NE", "kansas": "KS", "maryland": "MD", "kentucky": "KY",
    "ontario": "ONT", "tex": "TX", "okla": "OK", "tenn": "TN", "ala": "AL", "ark": "AR",
}

SOIL = re.compile(r"^(clay|loam|mineral|muck|silt|sandy|mc clay|mo clay|clay\d|loam\d)$", re.I)
SUMMARY = re.compile(r"mean|rank|average|lsd|c\.v", re.I)
CODE = re.compile(r"^([0-9]+|[a-z]|[ivx]{1,3}|[a-z]?\d+|\d+-\d+)$", re.I)  # 1 / B / I / 5-14
PSEUDO_CITY = re.compile(r"composite|^loc ?\d*$|\bmean\b|^yield$|^col [a-z]$|^cl vi|^\?+$|"
                         r"\blsd\b|average|^rank$", re.I)


def state_ok(s):
    s = str(s).strip()
    return (s.upper() in VALID_STATES) or (STATE_WORD.get(re.sub(r"\.$", "", s.lower())) is not None)


def city_is_state(c):
    return STATE_WORD.get(re.sub(r"[.\s]+$", "", str(c).strip().lower())) in VALID_STATES \
        or str(c).strip().upper() in VALID_STATES


def classify(city, state):
    c, s = str(city).strip(), str(state).strip()
    if PSEUDO_CITY.search(c):
        return "pseudo_city"
    if s == "" or s.lower() == "nan" or state_ok(s):
        return None                       # valid/blank state — not a bug here
    if SOIL.match(s):
        return "soil_in_state"
    if city_is_state(c):
        return "reversed_state_city"
    if SUMMARY.search(s):
        return "summary_in_state"
    if CODE.match(s):
        return "code_in_state"
    return "junk_state"


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(CORPUS, low_memory=False,
                     usecols=["Year", "Test", "Variant", "TestMG", "City", "State"])
    df = df[df["City"].notna()].copy()
    df["bug"] = [classify(c, s) for c, s in zip(df["City"], df["State"])]
    bugs = df[df["bug"].notna()].copy()

    detail = (bugs.groupby(["bug", "City", "State", "Year", "Test"])
              .size().reset_index(name="n_rows")
              .sort_values(["bug", "n_rows"], ascending=[True, False]))
    detail.to_csv(OUTDIR / "location_bugs_to_check.csv", index=False)

    # summary md grouped by bug type
    L = ["# Location-parsing bugs to verify against source (Year + Trial)\n",
         f"Source: `{CORPUS.name}`. REPORT ONLY — nothing changed. {len(bugs):,} bug rows, "
         f"{detail.groupby(['City','State']).ngroups} distinct (City,State).\n"]
    for bug, g in detail.groupby("bug"):
        L.append(f"## {bug} — {int(g['n_rows'].sum()):,} rows, {g.groupby(['City','State']).ngroups} sites\n")
        top = (g.groupby(["City", "State"])
               .agg(rows=("n_rows", "sum"),
                    years=("Year", lambda x: f"{x.min()}-{x.max()}" if x.nunique() > 1 else str(x.iloc[0])),
                    tests=("Test", lambda x: ",".join(sorted(set(x.astype(str)))[:6])))
               .reset_index().sort_values("rows", ascending=False).head(25))
        L.append("| City | State | rows | years | trials |")
        L.append("|------|-------|-----:|-------|--------|")
        for _, r in top.iterrows():
            L.append(f"| {r.City} | {r.State} | {int(r.rows)} | {r.years} | {r.tests} |")
        L.append("")
    (OUTDIR / "location_bugs_to_check.md").write_text("\n".join(L), encoding="utf-8")

    print(f"{len(bugs):,} location-bug rows across "
          f"{detail.groupby(['City','State']).ngroups} distinct (City,State)")
    print("\nby bug type (rows | distinct sites):")
    print(bugs.groupby("bug").agg(rows=("Year", "size"),
          sites=("City", lambda x: x.astype(str).nunique())).to_string())
    print("\nWorst offenders (City,State,years,trials):")
    head = (detail.groupby(["bug", "City", "State"])
            .agg(rows=("n_rows", "sum"), yrs=("Year", lambda x: f"{x.min()}-{x.max()}"),
                 tests=("Test", lambda x: ",".join(sorted(set(x.astype(str)))[:4])))
            .reset_index().sort_values("rows", ascending=False).head(15))
    print(head.to_string(index=False))
    print(f"\nOutputs ({OUTDIR.name}/): location_bugs_to_check.csv + .md")


if __name__ == "__main__":
    main()
