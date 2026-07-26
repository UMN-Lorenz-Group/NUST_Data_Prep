"""
build_location_canonical_map.py
===============================
Build a raw-variant -> canonical (City, State) map for the NUST corpus, to collapse
the ~842 raw City spellings (936 wide Location) down to the ~150 real trial sites.
The same physical site appears under many WITHIN- and ACROSS-year variants (e.g.
East Lansing 11 ways, South Charleston 7 ways, IA/IOWA, St. Paul/StPaul). Because
the asreml RGG models key Location directly (`factor(Location)`, `factor(Year:Location)`),
each spelling is a separate "environment" — standardizing them sharpens the
environment / GxE variance components.

Reuses the existing location assets: STATE_NORM / KNOWN_STATIONS (from
build_location_ref.py, copied here to avoid the geopy import side-effect), the
geocoded canonical list `reference/nust_locations_ref.csv` (source of truth for the
canonical spelling + StationName), and the authoritative synonym/canonical dictionary
ported from `2025_LocationsTable_Processing.R` (CITY_SYNONYM). bounded_levenshtein is
the script-14 pattern.

The map is keyed on the LITERAL corpus (raw_city, raw_state) pair so the assembly-time
apply is an exact dict lookup (the builder decides the canonical; the apply re-runs no
inference). Manual-review corrections folded in (location_bugs_to_check.csv, 2026-06):
  * "City ST" embedded-state cities (Worthington IN / Manhattan KS / Poplar Hill MD) ->
    split: State = trailing token, junk State-column code (rep/block/year) discarded.
  * "...Planted 5-14" planting-date suffix stripped (Lafayette IN Planted -> West Lafayette).
  * PENN/PENN. -> PA ; MDB/MDW (Maryland block B/W) -> MD.
  * Reversed early-era "State City" un-swapped (Iowa/STUART->Stuart IA, Ill/URBANA->Urbana IL,
    multi-word S Dakota/ELK POINT->Elk Point SD, Portage/VILLE->Portageville MO).
  * Trailing rep/block tokens stripped (Manhattan I -> Manhattan; preserves ManhattanB).
  * SOIL SUB-PLOTS KEPT DISTINCT as hyphenated sites (per the R reference + user): the soil
    type is part of the city name, NOT a junk state -> Portageville-Clay / Portageville-Loam
    (MO), East Lansing-Mineral / East Lansing-Muck (MI).
  * summary-in-state rows (Central/MEAN, East Coast/MEAN) and loc{n}/Composite/Yield/Rank
    pseudo-locations -> drop (these are mis-parsed location fields; the YieldRank TRAIT lives
    in the Phenotype column and is NEVER touched — only omitted from the heatmap via script 12).

Tiers / actions:
  map_auto     : HIGH-confidence merge — canonical != the literal raw pair. Feeds 10_assemble now.
  review       : OCR edit-distance / directional-DROP substring / ambiguous blank-state. Curate.
  keep_separate: same City name, DIFFERENT state (Arlington WI vs SD) — never merged.
  drop         : pseudo / summary location fields.
  canonical    : raw already equals canonical (identity; not applied).

Outputs:
  reference/nust_location_canonical_map.csv          (the lookup)
  reference/location_canonicalization_review.xlsx    (human review)
Read-only over the corpus; modifies nothing else.
"""
import sys
import re
from pathlib import Path
from collections import defaultdict
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
REF = REPO / "reference" / "nust_locations_ref.csv"
OUT_MAP = REPO / "reference" / "nust_location_canonical_map.csv"
OUT_XLSX = REPO / "reference" / "location_canonicalization_review.xlsx"

# ---- copied verbatim from build_location_ref.py (avoids the geopy import) --------
STATE_NORM = {
    "ill": "IL", "ill.": "IL", "ind": "IN", "ind.": "IN", "mo": "MO", "mo.": "MO",
    "wis": "WI", "wis.": "WI", "wisc": "WI", "wisc.": "WI", "mich": "MI", "mich.": "MI",
    "minn": "MN", "minn.": "MN", "n.d": "ND", "n.d.": "ND", "nd": "ND",
    "s.d": "SD", "s.d.": "SD", "sd": "SD", "kans": "KS", "kans.": "KS", "kan": "KS",
    "kan.": "KS", "ks": "KS", "md": "MD", "md.": "MD", "va": "VA", "va.": "VA",
    "pa": "PA", "pa.": "PA", "del": "DE", "del.": "DE", "n.j": "NJ", "n.j.": "NJ",
    "nj": "NJ", "ohio": "OH", "oh": "OH", "ore": "OR", "ore.": "OR", "wash": "WA",
    "wash.": "WA", "neb": "NE", "neb.": "NE", "nebr": "NE", "nebraska": "NE",
    "ia": "IA", "iowa": "IA", "ky": "KY", "ky.": "KY", "ny": "NY", "n.y": "NY",
    "la": "LA", "la.": "LA", "ms": "MS", "al": "AL", "ala": "AL", "ga": "GA",
    "nc": "NC", "n.c": "NC", "sc": "SC", "tx": "TX", "tex": "TX", "ok": "OK",
    "okla": "OK", "ar": "AR", "ark": "AR", "tn": "TN", "tenn": "TN", "in": "IN",
    "il": "IL", "wi": "WI", "mi": "MI", "mn": "MN", "indiana": "IN", "illinois": "IL",
    "michigan": "MI", "minnesota": "MN", "missouri": "MO", "wisconsin": "WI",
    "ont": "ONT", "ont.": "ONT", "on": "ONT", "ontario": "ONT", "man": "MAN",
    "man.": "MAN", "mb": "MAN", "sask": "SK", "sask.": "SK", "alta": "AB", "ab": "AB",
    "bc": "BC", "que": "QC", "que.": "QC", "qc": "QC", "ns": "NS", "nb": "NB", "sas": "SK",
    # full state names (for the reversed-format "State City" swap)
    "kansas": "KS", "maryland": "MD", "kentucky": "KY", "virginia": "VA",
    "delaware": "DE", "oregon": "OR", "washington": "WA", "california": "CA",
    "colorado": "CO", "idaho": "ID", "tennessee": "TN", "arkansas": "AR",
    "oklahoma": "OK", "texas": "TX", "georgia": "GA", "louisiana": "LA",
    "mississippi": "MS", "alabama": "AL",
    # manual-review additions: Pennsylvania spelt out, Maryland block codes
    "penn": "PA", "penn.": "PA", "pennsylvania": "PA", "mdb": "MD", "mdw": "MD",
}
KNOWN_STATIONS = {
    ("ames", "ia"): "ISU Agronomy and Agricultural Engineering Research Center",
    ("rosemount", "mn"): "UMN Rosemount Research and Outreach Center",
    ("morris", "mn"): "UMN West Central Research and Outreach Center",
    ("crookston", "mn"): "UMN Northwest Research and Outreach Center",
    ("lamberton", "mn"): "UMN Southwest Research and Outreach Center",
    ("waseca", "mn"): "UMN Southern Research and Outreach Center",
    ("st paul", "mn"): "UMN St Paul Campus Farm",
    ("fargo", "nd"): "NDSU Main Station / USDA ARS Fargo",
    ("brookings", "sd"): "SDSU Agricultural Experiment Station",
    ("west lafayette", "in"): "Purdue Agronomy Center for Research and Education",
    ("lafayette", "in"): "Purdue Agronomy Center for Research and Education",
    ("wooster", "oh"): "OARDC (Ohio Ag Research and Development Center)",
    ("columbia", "mo"): "MU Bradford Research Center",
    ("mt vernon", "mo"): "MU Southwest Research Center",
    ("portageville", "mo"): "MU Portageville Research Center",
    ("manhattan", "kan"): "Kansas State University Agronomy Farm",
    ("manhattan", "ks"): "Kansas State University Agronomy Farm",
    ("urbana", "il"): "UIUC Crop Sciences Research and Education Center",
    ("dekalb", "il"): "NIU / DeKalb County research station",
    ("east lansing", "mi"): "MSU Agronomy Farm",
    ("beltsville", "md"): "USDA ARS Beltsville Agricultural Research Center",
    ("state college", "pa"): "Penn State Agronomy Research Farm",
    ("ithaca", "ny"): "Cornell University Experiment Station",
    ("geneva", "ny"): "Cornell AgriTech (NYS Agricultural Experiment Station)",
    ("ottawa", "ont"): "AAFC Ottawa Research Centre",
    ("harrow", "ont"): "AAFC Harrow Research Centre",
    ("elora", "ont"): "University of Guelph Elora Research Station",
    ("guelph", "ont"): "University of Guelph", ("ridgetown", "ont"): "Guelph Ridgetown",
    ("morden", "man"): "AAFC Morden", ("brandon", "man"): "AAFC Brandon",
    ("winnipeg", "man"): "AAFC Winnipeg", ("swift current", "sk"): "AAFC Swift Current",
    ("ashland", "wi"): "Northern Soils and Crops Research Station",
    ("arlington", "wi"): "UW-Madison Arlington Agricultural Research Station",
    ("madison", "wi"): "UW-Madison Agronomy Farm",
    ("stoneville", "ms"): "USDA ARS Stoneville Mississippi Delta",
    ("queenstown", "md"): "University of Maryland Upper Chesapeake Agricultural Center",
}

DIRECTIONAL = {"e": "east", "w": "west", "n": "north", "s": "south", "so": "south",
               "no": "north", "mt": "mount", "st": "saint", "ft": "fort", "ne": "northeast",
               "nw": "northwest", "se": "southeast", "sw": "southwest"}
# OCR / spelling-collapse fixes on the normalized key (seed: clean_location_ref.py +
# 2025_LocationsTable_Processing.R + manual review). Keys are post-directional normkeys.
OCR_FIX = {
    "oueenstown": "queenstown", "qeenstown": "queenstown",
    "ubana": "urbana", "urbanail": "urbana",
    "giradr": "girard", "elkpoint": "elkpoint",
    "cooik": "cook", "costesfield": "cotesfield", "southerland": "sutherland",
    "holderage": "holdrege", "carnan": "carman", "porageville": "portageville",
    "scharleston": "southcharleston",   # glued reversed form -> ref "S. Charleston"
    "saginawcounty": "saginaw",
    # 1970s Red-PDF header OCR variants surfaced by the per-location recovery (script 112):
    "marshalitown": "marshalltown",     # "Marshal Itown" (I/L split) -> Marshalltown IA
    "blufftan": "bluffton",             # "Blufftan" -> Bluffton IN
    "quanticow": "quantico",            # "QuanticoW" (stray W) -> Quantico
}

# Authoritative synonym -> canonical City spelling, ported from
# 2025_LocationsTable_Processing.R. Keys are loc_normkey() values (post directional
# expansion: "St." -> saint, "S." -> south, embedded-state/block tokens dropped).
CITY_SYNONYM = {
    "cook": "Cook",
    "saginaw": "Saginaw", "saginawcounty": "Saginaw",
    "cotesfield": "Cotesfield",
    "urbana": "Urbana",
    "eastlansing": "East Lansing",
    "elmcreek": "Elm Creek",
    "sutherland": "Sutherland",
    "westlafayette": "West Lafayette", "lafayette": "West Lafayette",
    "holdrege": "Holdrege",
    "rosemount": "Rosemount",
    "thiefriverfalls": "Thief River Falls",
    "carman": "Carman",
    "saintpauls": "St. Pauls",
    "sainthyacinthe": "St. Hyacinthe",
    "saintmathieudebeloeil": "St. Mathieu de Beloeil",
    "saintmarys": "St. Marys",
    "stevenscreek": "Stevens Creek",
    "rockport": "Rock Port",
    "crookston": "Crookston", "novelty": "Novelty", "wanatah": "Wanatah",
    "ames": "Ames", "butlerville": "Butlerville",
    "poplarhill": "Poplar Hill", "elkpoint": "Elk Point",
    "universitypark": "University Park", "univpark": "University Park",
    # soil sub-plots kept DISTINCT (hyphenated canonical names)
    "portagevilleclay": "Portageville-Clay", "portagevilleloam": "Portageville-Loam",
    "eastlansingmineral": "East Lansing-Mineral", "eastlansingmuck": "East Lansing-Muck",
}

# pseudo-LOCATION markers (flagged for the location map only; this NEVER drops corpus rows,
# and never touches the YieldRank TRAIT which lives in the Phenotype column).
PSEUDO_RE = re.compile(r"composite|^loc ?\d*$|^loc \d+|\bmean\b|mean$|\blsd\b|average|^\?+$|"
                       r"diaporthe|purple ?stain|miscellaneous|^nan$|^$|^col [a-z]$|^cl vi|"
                       r"descriptivecode|east ?coast|coast east", re.I)
# City field IS a non-location summary token (mis-parsed location field, e.g. Yield/RANK).
PSEUDO_CITY_EXACT = {"yield", "rank", "mean", "average", "composite", "col"}
# State field is a summary marker (Yield/RANK, Central/MEAN) — NO empty/^$ patterns, so a
# blank State never trips it (only genuine summary tokens do).
STATE_PSEUDO_RE = re.compile(r"\bmean\b|mean$|\brank\b|\blsd\b|average|composite", re.I)

# Multi-word state names for the reversed-format swap.
MULTIWORD_STATES = {"south dakota": "SD", "s dakota": "SD", "north dakota": "ND",
                    "n dakota": "ND", "new jersey": "NJ", "new york": "NY",
                    "west virginia": "WV", "north carolina": "NC", "south carolina": "SC",
                    "new hampshire": "NH", "rhode island": "RI"}
# One-off (City, State) corpus artifacts.
CITY_STATE_OVERRIDE = {("Portage", "VILLE"): ("Portageville", "MO")}
STATE_SUFFIX = re.compile(r"^(.*?)[_ ]([A-Z]{2,3})$")   # "EastLansing_MI" / "Ottawa ONT"
PLANTED_RE = re.compile(r"\bplanted", re.I)             # "...Planted 5-14" suffix
BLOCK_RE = re.compile(r"^(?:[ivx]{1,3}|[a-w]|ai|bi|\d{1,2})$", re.I)  # trailing rep/block code

# Valid state/province codes — anything else in the State column (rep/year numbers,
# single letters, soil-types not yet folded into the city) is JUNK -> treated as blank,
# then inferred from the city.
VALID_STATES = {
    "AL", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN", "IA", "KS", "KY",
    "LA", "MD", "MI", "MN", "MS", "MO", "NE", "NJ", "NY", "NC", "ND", "OH", "OK", "OR",
    "PA", "SC", "SD", "TN", "TX", "VA", "WA", "WI", "WV", "WY", "ME", "VT", "NH", "MA", "RI",
    "ONT", "MAN", "SK", "AB", "BC", "QC", "NS", "NB",
}

# Soil-type tokens. A soil token is NOT a junk state — at the two known soil-plot sites it
# is part of the city name (Portageville-Clay/-Loam in MO, East Lansing-Mineral/-Muck in MI).
SOIL_TOKENS = {"clay", "loam", "mineral", "muck"}
SOIL_SITES = {"portageville": ("Portageville", "MO"), "eastlansing": ("East Lansing", "MI")}


def norm_state(s):
    s = str(s).strip().rstrip(".")
    if not s or s.lower() == "nan":
        return ""
    return STATE_NORM.get(s.lower(), s.upper())


def fix_reversed(city, state):
    """Early-era 'State City' stored reversed (City=a state name, State=the real city,
    e.g. 'Iowa'/'STUART' = Stuart IA; 'Ill'/'URBANA' = Urbana IL). Swap when the City IS a
    state name and the State is a non-state, non-blank token. 'Ontario'/'ORE' is NOT swapped
    (ORE->OR is a valid state, so City Ontario is the real city = Ontario OR)."""
    if (str(city).strip(), str(state).strip()) in CITY_STATE_OVERRIDE:
        return CITY_STATE_OVERRIDE[(str(city).strip(), str(state).strip())]
    cn = MULTIWORD_STATES.get(re.sub(r"\.", "", str(city).strip().lower()), norm_state(city))
    st = str(state).strip()
    if cn in VALID_STATES and st and st.lower() != "nan" and norm_state(st) not in VALID_STATES:
        return (st, cn)
    return (city, state)


# Leading-state-name prefix in a SINGLE City field ("Illinois Urbana", "Iowa Ames",
# "Ohio Wooster", "Ontario Harrow", "S.D. Brookings", "Indiana Lafayette"). Ordered
# longest-first so multiword/abbrev forms win. The remainder is the real city.
STATE_PREFIX_PATTERNS = [
    (r"south dakota|s\.?\s*dakota|s\.\s*d\.?", "SD"),
    (r"north dakota|n\.?\s*dakota|n\.\s*d\.?", "ND"),
    (r"west virginia", "WV"), (r"north carolina", "NC"), (r"south carolina", "SC"),
    (r"new york", "NY"), (r"new jersey|n\.?\s*j\.?", "NJ"),
    (r"illinois|ill\.?", "IL"), (r"indiana|ind\.?", "IN"), (r"iowa", "IA"),
    (r"ohio", "OH"), (r"michigan|mich\.?", "MI"), (r"minnesota|minn\.?", "MN"),
    (r"missouri", "MO"), (r"nebraska|nebr\.?", "NE"), (r"kansas|kans\.?", "KS"),
    (r"wisconsin|wisc\.?", "WI"), (r"kentucky", "KY"), (r"maryland", "MD"),
    (r"ontario|ont\.?", "ONT"), (r"pennsylvania|penn\.?", "PA"),
]
# Generic suffixes where a state-prefixed City is actually a REAL city, not reversed
# (Iowa City, Kansas City, Nebraska City, Ohio City, Oklahoma City, Virginia Beach).
PREFIX_KEEP_REST = {"city", "beach"}


def split_leading_state(city):
    """If City is '<StateName> <RealCity>' (single field), return (real_city, state_code),
    else None. Guards the '<State> City' real-city collisions (Iowa City, Kansas City)."""
    s = str(city).strip()
    for pat, code in STATE_PREFIX_PATTERNS:
        m = re.match(r"^(?:" + pat + r")\s+(.+)$", s, re.I)
        if m:
            rest = m.group(1).strip()
            # if the remainder is itself a state ("Ontario Ore" = Ontario, OR) this is a
            # City+State pair, not a reversed State+City — let resolve_state handle it.
            if rest and rest.lower() not in PREFIX_KEEP_REST and norm_state(rest) not in VALID_STATES:
                return (rest, code)
    return None


def resolve_state(city, state):
    """Normalized state, restricted to VALID_STATES; junk/blank falls back to a trailing
    state token embedded in the City (e.g. 'EastLansing MI', 'Manhattan KS'), else ''."""
    ns = norm_state(state)
    if ns in VALID_STATES:
        return ns
    for tok in re.split(r"[\s.\-_,/]+", str(city).strip()):
        if len(tok) <= 3 and norm_state(tok) in VALID_STATES:
            return norm_state(tok)
    return ""


def _loc_tokens(city):
    """Tokenize a City: strip planting-date suffix + _STATE suffix, split camelCase,
    expand directionals, drop embedded state abbrevs and trailing rep/block codes."""
    s = str(city).strip()
    m = PLANTED_RE.search(s)
    if m:
        s = s[:m.start()].strip()                        # "Lafayette IN Planted 5-14" -> "Lafayette IN"
    m2 = STATE_SUFFIX.match(s)
    if m2 and m2.group(2).upper() in set(STATE_NORM.values()) | {"ONT", "MAN"}:
        s = m2.group(1)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)           # EastLansing -> East Lansing
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)       # ELansing -> E Lansing
    toks = [t for t in re.split(r"[\s.\-_,/]+", s) if t]
    toks = [DIRECTIONAL.get(t.lower(), t) for t in toks]
    # drop embedded short state-abbrev tokens (Manhattan KS -> Manhattan; keep full-word
    # state-named cities like Indiana PA), never emptying the list.
    stripped = [t for t in toks if not (len(t) <= 3 and norm_state(t) in VALID_STATES)]
    toks = stripped if stripped else toks
    # strip trailing rep/block codes (Manhattan I -> Manhattan, Portageville AI/BI ->
    # Portageville), but PRESERVE a lone 'B' (the distinct ManhattanB sub-location).
    while len(toks) > 1 and BLOCK_RE.match(toks[-1]) and toks[-1].lower() != "b":
        toks.pop()
    return toks


def _key(toks):
    return re.sub(r"[^a-z0-9]", "", " ".join(toks).lower())


def loc_normkey(city):
    """Cluster key: expand directionals + OCR/spelling fixes (soil tokens retained so soil
    sub-plots stay distinct; soil_resolve handles the State-encoded form)."""
    key = _key(_loc_tokens(city))
    return OCR_FIX.get(key, key)


def soil_resolve(city, state):
    """If (City, State) is a Portageville/East Lansing soil sub-plot, return (normkey, nstate)
    routing it to a DISTINCT hyphenated site (Portageville-Clay etc.). Handles all three forms:
    soil in City ('Portageville-Clay'), soil in State ('Portageville MO'/State='CLAY'), and bare
    soil ('Clay'/MO). Returns None for anything else (so Clay Center / Clayton are untouched)."""
    toks = _loc_tokens(city)
    soil = next((t.lower() for t in toks if t.lower() in SOIL_TOKENS), None)
    if soil is None:
        m = re.search(r"\b(clay|loam|mineral|muck)\b", str(state), re.I)
        soil = m.group(1).lower() if m else None
    if soil is None:
        return None
    base = [t for t in toks if t.lower() not in SOIL_TOKENS]
    bkey = OCR_FIX.get(_key(base), _key(base))
    if bkey == "":                                        # bare "Clay"/"Loam"/"Mineral"/"Muck"
        bkey = "portageville" if soil in ("clay", "loam") else "eastlansing"
    if bkey not in SOIL_SITES:
        return None
    return (bkey + soil, SOIL_SITES[bkey][1])


def clean_city_spelling(s):
    """Fallback canonical spelling (when no synonym/ref hit): strip planting-date suffix,
    a trailing embedded state token, and trailing block codes; title-case all-caps tokens."""
    s = str(s).strip()
    m = PLANTED_RE.search(s)
    if m:
        s = s[:m.start()].strip()
    toks = [t for t in re.split(r"\s+", s) if t]
    while len(toks) > 1 and norm_state(toks[-1]) in VALID_STATES:
        toks.pop()
    while len(toks) > 1 and BLOCK_RE.match(toks[-1]) and toks[-1].lower() != "b":
        toks.pop()
    toks = [t.title() if (t.isupper() and len(t) > 1 and t.isalpha()) else t for t in toks]
    return " ".join(toks) if toks else s


def bounded_levenshtein(a, b, maxd=2):
    la, lb = len(a), len(b)
    if abs(la - lb) > maxd:
        return maxd + 1
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        if min(cur) > maxd:
            return maxd + 1
        prev = cur
    return prev[lb]


def main():
    print(f"Loading {CORPUS.name} ...", flush=True)
    df = pd.read_csv(CORPUS, low_memory=False, usecols=["Year", "City", "State"])
    df = df[df["City"].notna()].copy()
    df["City"] = df["City"].astype(str).str.strip()
    df["State_raw"] = df["State"].fillna("").astype(str).str.strip()

    # --- per LITERAL corpus (City, State) pair -----------------------------------
    # Key the map on the original literal pair so the assembly-time apply is an exact
    # lookup. The canonical is computed from the un-reversed/normalized view.
    raw = (df.groupby(["City", "State_raw"]).size().reset_index(name="n_rows"))

    # un-reverse "State City" rows (two-column swap, then single-field leading-state split),
    # then derive normalized state + cluster key
    def _unreverse(c, s):
        c, s = fix_reversed(c, s)
        sp = split_leading_state(c)
        if sp is not None:
            rest, code = sp
            c = rest
            if norm_state(s) not in VALID_STATES:
                s = code
        return (c, s)
    fc, fs = zip(*[_unreverse(c, s) for c, s in zip(raw["City"], raw["State_raw"])])
    raw["fix_city"], raw["fix_state"] = fc, fs
    raw["nstate"] = [resolve_state(c, s) for c, s in zip(raw["fix_city"], raw["fix_state"])]
    raw["normkey"] = raw["fix_city"].apply(loc_normkey)

    # pseudo / summary location field (City or raw State is a non-location marker). Test
    # City and State INDEPENDENTLY (stripped) so anchored patterns like "^loc\d*$" match a
    # blank-state row — concatenating "loc1 " would break the trailing-$ anchor.
    raw["pseudo"] = [
        bool(PSEUDO_RE.search(str(c).strip()))
        or bool(str(s).strip() and STATE_PSEUDO_RE.search(str(s).strip()))
        or str(c).strip().lower() in PSEUDO_CITY_EXACT
        for c, s in zip(raw["City"], raw["State_raw"])]

    # soil sub-plots -> DISTINCT hyphenated sites (override normkey + nstate)
    for i, r in raw.iterrows():
        if r["pseudo"]:
            continue
        sr = soil_resolve(r["fix_city"], r["fix_state"])
        if sr is not None:
            raw.at[i, "normkey"], raw.at[i, "nstate"] = sr

    # --- reference (canonical spelling + station) keyed by (normkey, state) -------
    ref = pd.read_csv(REF)
    ref_by_key = {}
    for _, r in ref.iterrows():
        ref_by_key[(loc_normkey(r["City"]), str(r["State"]).strip())] = (
            r["City"], str(r["State"]).strip(), r.get("StationName", "") or "")
    known_by_key = {(loc_normkey(c), norm_state(st)): station
                    for (c, st), station in KNOWN_STATIONS.items()}

    # --- infer blank state from unambiguous normkey -> {states} ------------------
    key_states = defaultdict(set)
    for _, r in raw[raw["nstate"] != ""].iterrows():
        key_states[r["normkey"]].add(r["nstate"])
    for (nk, st) in ref_by_key:
        key_states[nk].add(st)
    raw["state_inferred"] = False
    raw["state_ambig"] = False
    for i, r in raw.iterrows():
        if r["nstate"] == "" and not r["pseudo"]:
            cand = key_states.get(r["normkey"], set())
            if len(cand) == 1:
                raw.at[i, "nstate"] = next(iter(cand)); raw.at[i, "state_inferred"] = True
            elif len(cand) > 1:
                raw.at[i, "state_ambig"] = True

    # --- site identity: KNOWN_STATIONS merges Lafayette+West Lafayette etc. -------
    def site_of(r):
        station = known_by_key.get((r["normkey"], r["nstate"]))
        return station if station else f"{r['normkey']}|{r['nstate']}"
    raw["site"] = raw.apply(site_of, axis=1)

    # --- canonical spelling per site: synonym > ref > cleaned top-n_rows raw ------
    canon = {}
    for site, grp in raw[~raw["pseudo"]].groupby("site"):
        top = grp.sort_values("n_rows", ascending=False).iloc[0]
        nk, st = top["normkey"], top["nstate"]
        ref_hit = next((ref_by_key[(k, s)] for k, s in zip(grp["normkey"], grp["nstate"])
                        if (k, s) in ref_by_key), None)
        station = known_by_key.get((nk, st), "")
        if nk in CITY_SYNONYM:
            city, cstate = CITY_SYNONYM[nk], st
            if ref_hit and ref_hit[2]:
                station = ref_hit[2]
        elif ref_hit:
            city, cstate, station = ref_hit
        else:
            city, cstate = clean_city_spelling(top["fix_city"]), st
        canon[site] = (city, cstate, station)

    # --- assemble rows + tiers ---------------------------------------------------
    out = []
    for _, r in raw.iterrows():
        if r["pseudo"]:
            out.append((r["City"], r["State_raw"], r["nstate"], r["normkey"], "", "", "",
                        "drop", "pseudo_location", r["n_rows"])); continue
        cc, cs, station = canon[r["site"]]
        identity = (cc == r["City"] and cs == r["State_raw"])
        if r["state_ambig"]:
            action, conf = "review", "ambiguous_blank_state"
        elif identity:
            action, conf = "canonical", "canonical"
        else:
            action = "map_auto"
            conf = ("ref_match" if (r["normkey"], r["nstate"]) in ref_by_key
                    else "known_station" if (r["normkey"], r["nstate"]) in known_by_key
                    else "synonym" if r["normkey"] in CITY_SYNONYM
                    else "state_inferred" if r["state_inferred"]
                    else "norm_merge")
        out.append((r["City"], r["State_raw"], r["nstate"], r["normkey"], cc, cs, station,
                    action, conf, r["n_rows"]))
    M = pd.DataFrame(out, columns=["raw_city", "raw_state", "norm_state", "normkey",
                                   "canon_city", "canon_state", "station_name",
                                   "action", "confidence", "n_rows"])

    # --- REVIEW pass: OCR edit-distance + directional-DROP substring, same state -
    review_pairs = []
    canon_rows = (M[M["action"].isin(["canonical", "map_auto"])]
                  .groupby(["canon_city", "canon_state", "normkey"])["n_rows"].sum().reset_index())
    by_state = defaultdict(list)
    for _, r in canon_rows.iterrows():
        by_state[r["canon_state"]].append((r["canon_city"], r["normkey"], r["n_rows"]))
    for st, items in by_state.items():
        items.sort(key=lambda x: -x[2])
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ci, ki, ni = items[i]; cj, kj, nj = items[j]
                if ki == kj:
                    continue
                ed = bounded_levenshtein(ki, kj, 2)
                sub = (ki in kj or kj in ki) and min(len(ki), len(kj)) >= 4
                if ed <= 2 or sub:
                    review_pairs.append({"state": st, "keep": ci, "merge": cj,
                                         "keep_rows": ni, "merge_rows": nj,
                                         "reason": "edit_dist" if ed <= 2 else "substring",
                                         "edit_dist": ed})

    OUT_MAP.parent.mkdir(parents=True, exist_ok=True)
    M.sort_values(["action", "canon_state", "canon_city", "n_rows"],
                  ascending=[True, True, True, False]).to_csv(OUT_MAP, index=False)

    # --- review workbook ---------------------------------------------------------
    keep_sep = []
    for nk, grp in M[M["action"].isin(["map_auto", "canonical"])].groupby("normkey"):
        states = sorted(grp["canon_state"].unique())
        if len(states) > 1:
            keep_sep.append({"normkey": nk, "states": ",".join(states),
                             "canon_cities": " | ".join(sorted(set(
                                 f"{c} ({s})" for c, s in zip(grp["canon_city"], grp["canon_state"]))))})
    clusters = (M[M["action"] == "map_auto"]
                .groupby(["canon_city", "canon_state", "confidence"])
                .agg(n_variants=("raw_city", "nunique"), total_rows=("n_rows", "sum"),
                     variants=("raw_city", lambda x: " | ".join(sorted(set(x)))))
                .reset_index().sort_values("total_rows", ascending=False))
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as xl:
        readme = pd.DataFrame({"item": ["PURPOSE", "map_auto", "review", "keep_separate", "drop"],
                               "meaning": [
            "Raw City/State -> canonical map for the corpus. map_auto rows feed 10_assemble now; "
            "review rows need curation before applying.",
            "HIGH-confidence merge (synonym / ref / known-station / directional / state-variant / "
            "embedded-state split / soil sub-plot / reversed-swap).",
            "OCR edit-distance, directional-DROP substring, or ambiguous blank-state — curate first.",
            "Same City name, different state (Arlington WI vs SD) — never merged.",
            "Pseudo / summary location field (Composite/loc{n}/Yield/Rank/Central-MEAN) — dropped."]})
        readme.to_excel(xl, sheet_name="Readme", index=False)
        clusters.to_excel(xl, sheet_name="Clusters_auto", index=False)
        pd.DataFrame(review_pairs).to_excel(xl, sheet_name="Review_OCR_substring", index=False)
        M[M["confidence"] == "ambiguous_blank_state"].to_excel(xl, sheet_name="Review_blank_state", index=False)
        pd.DataFrame(keep_sep).to_excel(xl, sheet_name="KeptSeparate", index=False)
        M[M["action"] == "drop"].to_excel(xl, sheet_name="PseudoLocations", index=False)

    # --- console -----------------------------------------------------------------
    print(f"\n  raw (City,State): {len(M)}  ->  distinct canonical sites: "
          f"{M[M.action.isin(['map_auto','canonical'])].groupby(['canon_city','canon_state']).ngroups}")
    print("  action counts:", M["action"].value_counts().to_dict())
    print(f"  map_auto merges: {(M.action=='map_auto').sum()} raw spellings; "
          f"review: {(M.action=='review').sum()}; drop: {(M.action=='drop').sum()}")
    print(f"  OCR/substring review pairs: {len(review_pairs)}; keep-separate normkeys: {len(keep_sep)}")
    print(f"\nWrote {OUT_MAP.name} + {OUT_XLSX.name}")


if __name__ == "__main__":
    main()
