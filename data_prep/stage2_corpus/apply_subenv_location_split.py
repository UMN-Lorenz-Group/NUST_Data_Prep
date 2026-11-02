"""Un-merge collapsed SUB-ENVIRONMENTS in the location canonical map (category-B conflict fix).

At a handful of stations, two genuinely distinct physical plots (irrigated vs dryland, numbered
replicate plots 1..4, soil types, planting-date splits) were printed at ONE city and the plot indicator
landed in the raw STATE slot (e.g. `Manhattan KS`,State=`2`) or as a city suffix (`Georgetown I`,
`Portageville CLAY1`). `build_location_canonical_map` merged them all into the base city, so the same
(Year,Test,City,State,Strain,Phenotype) cell holds 2 values = the corpus value-CONFLICTS that break the
one-obs-per-GxLxY expectation for the RGG (see [[project_nust_corpus_integrity_audit]]).

This routes each plot-indicator raw variant to a DISTINCT canon Location (`Manhattan`, `Manhattan-2`,
`Portageville-Clay`, `West Lafayette-P7-1`, ...) — the same convention Portageville-Clay/Loam already use.
YEAR-in-state noise (`Evansville IN`,State=`1944`) is NOT a sub-env -> left collapsing to base (a same-plot
double-read handled by the A/D dedup). Scope is restricted to the proven category-B 2-plot stations; a
bare plot indicator at a single-plot station would be a stray, not a real split.

`--apply` backs up the map to `.bak_pre_subenv` and rewrites the map_auto canon_city for matched rows.
Idempotent: skips a row whose canon already carries the suffix.
"""
import sys, re, shutil
from pathlib import Path
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
MAP = REPO / "reference" / "nust_location_canonical_map.csv"

# The 21 category-B canon cities (systematic whole-roster doubling; see conflict_categorization.csv).
# Only these are split — a plot indicator elsewhere is likely a stray, not a genuine second plot.
B_CITIES = {"Brookings", "East Lansing-Mineral", "Evansville", "Georgetown", "La Grange", "Manhattan",
            "Mt. Holly", "North Vernon", "Ottawa Lake", "Poplar Hill", "Portageville", "Queenstown",
            "Sikeston", "Snow Hill", "Spickard", "St. Paul", "State College", "University Park",
            "Waseca", "West Lafayette", "Worthington"}

STATES = set("AL AK AZ AR CA CO CT DE FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
             "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY "
             "ON QC MB SK AB BC NB NS".split())
YEAR = re.compile(r"^(18|19|20)\d\d$")
ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5"}
PLOTNUM = re.compile(r"^0*([1-5])$")
ROMANRE = re.compile(r"^(I{1,3}|IV|V)$")
LETTER = re.compile(r"^([AB])$")
SOIL = re.compile(r"(clay|loam|silt|sand)\w*", re.I)
PLANT = re.compile(r"(?:planted?|pd)\s*_?\s*(\d{1,2}[-/]\d{1,2}|\d)", re.I)
IRRIG = re.compile(r"(irrig|dry\s*land|dryland)", re.I)
CITYSUF = re.compile(r"^(.+\S)\s+(I{1,3}|IV|[AB])$")


def norm_num(tok):
    tok = tok.upper()
    return ROMAN.get(tok, tok.lstrip("0") or tok)


def num_suffix(n):
    # Split EVERY explicit plot indicator to its own label (Manhattan-1, Manhattan-2, ...). The plot
    # numbering is inconsistent across years (some years print base+`2`, others base+`1`=the 2nd plot),
    # so a global "1==base" merge would recombine genuinely distinct plots (e.g. dryland base +
    # irrigated `1`) and the A/D mean would then destroy a real 30-bu environmental gap. Over-splitting
    # (base + `-1` as two labels for one plot in a year where `1` is redundant) only mildly fragments an
    # environment's roster and keeps values intact — the safer error for RGG. Residual within-label
    # double-reads (same plot, drifted OCR) are collapsed by the A/D dedup.
    return "-" + n


def indicator(raw_city, raw_state, norm_state=""):
    rc, rs = str(raw_city).strip(), str(raw_state).strip()
    ns = str(norm_state).strip().upper()
    blob = f"{rc} {rs}"
    if SOIL.search(blob):   return "soil", "-" + SOIL.search(blob).group(1).title()
    if PLANT.search(blob):  return "plant", "-P" + PLANT.search(blob).group(1).replace("/", "-")
    if IRRIG.search(blob):  return "irrig", "-Irrig"
    if YEAR.match(rs):      return "year_noise", None
    if PLOTNUM.match(rs):   return "plotnum", num_suffix(norm_num(rs))
    if ROMANRE.match(rs):   return "plotnum", num_suffix(norm_num(rs))
    if LETTER.match(rs):    return "letter", num_suffix(rs.upper())
    mst = re.match(r"^([A-Z]{2})([AB])$", rs.upper())    # state+plot fused in state slot: 'MDB' = MD plot B
    if mst and mst.group(1) in STATES:
        return "letter", num_suffix(mst.group(2))
    if rs.upper() in STATES or ns in STATES:
        mm = re.match(r"^(.+\S)\s+([AB]I?|I{1,3}|IV)$", rc)   # 'Portageville AI'/'BI', 'Georgetown I'
        if mm:
            tok = mm.group(2).upper()
            if tok[0] in "AB":                # A/B plot letter (AI/BI = A/B irrigated) -> keep the letter
                return "citysuffix", "-" + tok[0]
            return "citysuffix", num_suffix(norm_num(tok))
        mm2 = re.match(r"^(.+[a-z])([AB])$", rc)               # attached 'EvansvilleA'
        if mm2:
            return "citysuffix", "-" + mm2.group(2).upper()
    return None, None


def main():
    apply = "--apply" in sys.argv
    m = pd.read_csv(MAP, keep_default_na=False)
    changes = []
    for i, r in m.iterrows():
        if r["action"] != "map_auto" or str(r["canon_city"]) not in B_CITIES:
            continue
        typ, suf = indicator(r["raw_city"], r["raw_state"], r.get("norm_state", ""))
        if not suf or typ == "year_noise":
            continue
        base = str(r["canon_city"])
        if base.endswith(suf):        # idempotent
            continue
        new = base + suf
        changes.append((i, r["raw_city"], r["raw_state"], base, new, typ, r["n_rows"]))

    ch = pd.DataFrame(changes, columns=["idx", "raw_city", "raw_state", "old", "new", "typ", "n_rows"])
    print(f"sub-env split: {len(ch)} map_auto variants -> distinct locations "
          f"({ch.n_rows.sum():,} rows) across {ch.new.str.rsplit('-', n=1).str[0].nunique()} stations")
    print(ch.sort_values(["old", "new"])[["raw_city", "raw_state", "old", "new", "typ", "n_rows"]]
          .to_string(index=False))
    print("\nnew distinct locations:", sorted(ch.new.unique()))

    if apply:
        bak = MAP.with_suffix(".csv.bak_pre_subenv")
        if not bak.exists():
            shutil.copy2(MAP, bak); print(f"\nbacked up -> {bak.name}")
        for _, rc in ch.iterrows():
            m.at[rc["idx"], "canon_city"] = rc["new"]
        m.to_csv(MAP, index=False)
        print(f"wrote {MAP.name}: {len(ch)} canon_city remaps applied")
    else:
        print("\n(dry run; --apply to write the map)")


if __name__ == "__main__":
    main()
