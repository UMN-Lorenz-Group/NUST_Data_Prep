"""
14_qc_duplicate_strains.py
==========================
Detect POTENTIAL DUPLICATE strain spellings in the corpus — the same variety written
two (or more) ways through OCR error or inconsistent formatting (e.g. `Mardarin(Ottawa)`
vs `Mandarin(Ottawa)`, `A-100` vs `A100`). Companion to the stray-ID audit (script 13);
duplication and formatting drift are a recurring curation problem, so this emits a separate
workbook for manual checking. It DOES NOT modify the corpus.

Method (no external fuzzy-match dependency — pure stdlib):
  * FORMATTING tier  — spellings that collapse to the same alphanumeric key after
                       lower-casing and stripping punctuation/whitespace (case / punct /
                       space variants). Highest confidence.
  * OCR_LETTERS tier — same DIGIT content but a small letter edit distance (<=2) on the
                       alphabetic skeleton. Requiring identical digits means intentional
                       numeric-suffix releases (Williams vs Williams82, Cutler71 vs Cutler,
                       A82-361011 vs A82-365028) are NOT flagged as duplicates.

Confidence is raised when the two spellings CO-OCCUR in the same (Year, Trial) or
(Year, Trial, Location): a variety appearing twice in one trial table is almost certainly
a typo/duplicate, whereas two never-co-occurring similar names may be genuinely distinct
varieties (e.g. Clark vs Clary) — those are left as REVIEW for human judgement.

Blocking keeps it tractable (no O(n^2) over 15k strains): FORMATTING via the alphanumeric
key; OCR_LETTERS via (first letter, digit signature) buckets with a length-window filter.

Outputs (analysis/data/analysis_results/Corpus_QC/):
  potential_duplicate_strains.xlsx
    - Readme            : tier / column legend
    - Duplicate_pairs   : one row per candidate pair (a, b) + context + suggested merge
    - Duplicate_clusters: connected components (canonical-group suggestions)

Input: analysis/data/_shared/nust_1941_2025_combined.csv
"""
import sys
import re
from pathlib import Path
from collections import defaultdict
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
LONG = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
OUTDIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
OUTDIR.mkdir(parents=True, exist_ok=True)

MAX_EDIT = 2          # max letter edit distance for the OCR_LETTERS tier
MIN_LETTERS = 4       # ignore very short skeletons (Hark/Mark-type distance-1 noise)
LEN_WINDOW = 2        # only compare skeletons whose lengths differ by <= this


def norm_key(s: str) -> str:
    """Alphanumeric key: lower-case, drop all non-alphanumeric. Collapses case /
    punctuation / whitespace variants to the same key."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", str(s).lower())


def digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", str(s))


def bounded_levenshtein(a: str, b: str, maxd: int) -> int:
    """Levenshtein distance (full two-row DP), early-exiting at maxd+1 once the whole
    row exceeds maxd. Simple and correct — strings here are short."""
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
    if not LONG.exists():
        sys.exit(f"ERROR: missing {LONG}")
    print(f"Loading {LONG.name} ...", flush=True)
    df = pd.read_csv(LONG, low_memory=False,
                     usecols=["Year", "TestMG", "Test", "City", "Strain"])
    df = df[df["Strain"].notna()].copy()
    df["Strain"] = df["Strain"].astype(str)
    df["MG"] = df["TestMG"].astype(str).str.strip()

    # per-strain context
    print("Building per-strain context ...", flush=True)
    g = df.groupby("Strain")
    ctx = g.agg(n_rows=("Year", "size"),
                n_years=("Year", "nunique"),
                yr_min=("Year", "min"), yr_max=("Year", "max")).to_dict("index")
    mgs = {s: set(v.dropna().astype(str)) for s, v in g["MG"]}
    yt = {s: set(zip(v["Year"], v["Test"])) for s, v in df.groupby("Strain")[["Year", "Test"]]}
    ytl = {s: set(zip(v["Year"], v["Test"], v["City"]))
           for s, v in df.groupby("Strain")[["Year", "Test", "City"]]}

    strains = sorted(ctx.keys())
    print(f"  {len(strains):,} distinct strains")

    pairs = {}   # (a,b) -> dict

    def add_pair(a, b, tier, dist):
        if a == b:
            return
        key = tuple(sorted((a, b)))
        if key in pairs:                          # keep the stronger tier
            if pairs[key]["tier"] == "OCR_LETTERS" and tier == "FORMATTING":
                pairs[key].update(tier=tier, letter_edit_dist=dist)
            return
        pairs[key] = {"tier": tier, "letter_edit_dist": dist}

    # --- FORMATTING tier: same alphanumeric key -----------------------------
    by_key = defaultdict(list)
    for s in strains:
        by_key[norm_key(s)].append(s)
    for k, group in by_key.items():
        if k and len(group) > 1:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    add_pair(group[i], group[j], "FORMATTING", 0)

    # --- OCR_LETTERS tier: same digits, small letter edit distance ----------
    # block by (first letter of skeleton, digit signature); compare within a length window.
    blocks = defaultdict(list)
    for s in strains:
        le = letters(s)
        if len(le) >= MIN_LETTERS:
            blocks[(le[0], digits(s))].append((s, le))
    for (_, _dig), items in blocks.items():
        items.sort(key=lambda x: len(x[1]))
        for i in range(len(items)):
            si, lei = items[i]
            for j in range(i + 1, len(items)):
                sj, lej = items[j]
                if len(lej) - len(lei) > LEN_WINDOW:
                    break
                if lei == lej:                    # same skeleton, differ only by digits-position/case
                    add_pair(si, sj, "FORMATTING", 0)
                    continue
                # Containment = one skeleton is the other + an alphabetic suffix/prefix.
                # These are backcross / near-isogenic / gene-tag lines (Elgin vs ElginBC,
                # Essex vs Essex(v), Amsoy71 vs Amsoy71BC6) — genuinely DISTINCT germplasm,
                # never an OCR duplicate. Flag separately, never promote to HIGH.
                if lei in lej or lej in lei:
                    add_pair(si, sj, "SUFFIX_VARIANT", len(lej) - len(lei))
                    continue
                d = bounded_levenshtein(lei, lej, MAX_EDIT)
                if d <= MAX_EDIT:
                    add_pair(si, sj, "OCR_LETTERS", d)

    print(f"  candidate pairs: {len(pairs)}")

    # --- context + confidence per pair --------------------------------------
    rows = []
    for (a, b), info in pairs.items():
        sa, sb = (a, b) if ctx[a]["n_rows"] >= ctx[b]["n_rows"] else (b, a)  # keep=more frequent
        shared_yt = len(yt[a] & yt[b])
        shared_ytl = len(ytl[a] & ytl[b])
        mg_overlap = ",".join(sorted(mgs[a] & mgs[b]))
        if info["tier"] == "SUFFIX_VARIANT":
            conf = "REVIEW (suffix/variant)"
        elif info["tier"] == "FORMATTING":
            conf = "HIGH"
        elif shared_yt > 0:
            conf = "HIGH (co-occurs in trial)"
        else:
            conf = "REVIEW"
        rows.append({
            "confidence": conf, "tier": info["tier"],
            "letter_edit_dist": info["letter_edit_dist"],
            "strain_a": a, "strain_b": b,
            "suggested_keep": sa, "suggested_merge": sb,
            "shared_year_trial": shared_yt, "shared_year_trial_loc": shared_ytl,
            "mg_overlap": mg_overlap,
            "n_rows_a": ctx[a]["n_rows"], "n_rows_b": ctx[b]["n_rows"],
            "years_a": f"{ctx[a]['yr_min']}-{ctx[a]['yr_max']}",
            "years_b": f"{ctx[b]['yr_min']}-{ctx[b]['yr_max']}",
            "mgs_a": ",".join(sorted(mgs[a])), "mgs_b": ",".join(sorted(mgs[b])),
        })
    pair_df = pd.DataFrame(rows)
    conf_rank = {"HIGH": 0, "HIGH (co-occurs in trial)": 1,
                 "REVIEW": 2, "REVIEW (suffix/variant)": 3}
    if len(pair_df):
        pair_df["_c"] = pair_df["confidence"].map(conf_rank).fillna(2)
        pair_df = pair_df.sort_values(
            ["_c", "tier", "letter_edit_dist", "strain_a"]).drop(columns="_c")

    # --- clusters (connected components) -------------------------------------
    # Build ONLY from HIGH-confidence edges (FORMATTING + co-occurring OCR). A single weak
    # REVIEW edge could otherwise transitively merge genuinely distinct varieties.
    hi_edges = {tuple(sorted((r["strain_a"], r["strain_b"])))
                for r in rows if r["confidence"].startswith("HIGH")}
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        parent[find(x)] = find(y)
    for (a, b) in hi_edges:
        union(a, b)
    comp = defaultdict(list)
    for s in parent:
        comp[find(s)].append(s)
    clusters = []
    for _, members in comp.items():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda s: -ctx[s]["n_rows"])
        clusters.append({
            "canonical_suggestion": members[0],
            "n_members": len(members),
            "total_rows": sum(ctx[m]["n_rows"] for m in members),
            "members": " | ".join(f"{m} (n={ctx[m]['n_rows']})" for m in members),
        })
    clus_df = pd.DataFrame(clusters).sort_values(
        "total_rows", ascending=False) if clusters else pd.DataFrame(
        columns=["canonical_suggestion", "n_members", "total_rows", "members"])

    readme = pd.DataFrame({
        "item": ["PURPOSE", "Duplicate_pairs", "Duplicate_clusters",
                 "tier: FORMATTING", "tier: OCR_LETTERS",
                 "confidence: HIGH", "confidence: HIGH (co-occurs in trial)",
                 "confidence: REVIEW", "suggested_keep / suggested_merge",
                 "shared_year_trial", "NOT flagged"],
        "meaning": [
            "Potential DUPLICATE strain spellings (same variety written two ways) for manual "
            "checking / canonicalisation. Does NOT modify the corpus.",
            "One row per candidate pair, with frequency / year / MG context and a suggested "
            "merge direction (keep the more frequent spelling).",
            "Connected components of the flagged pairs — a canonical-name group suggestion.",
            "Spellings identical after lower-casing + removing punctuation/whitespace "
            "(e.g. 'A-100' vs 'A100', 'Mandarin (Ottawa)' vs 'Mandarin(Ottawa)').",
            "Same digit content, letter edit distance <=2 on the alphabetic skeleton "
            "(e.g. 'Mardarin(Ottawa)' vs 'Mandarin(Ottawa)').",
            "Formatting-only variant — almost certainly the same entity.",
            "Similar spellings that ALSO appear in the same Year+Trial — a variety listed "
            "twice in one table is almost certainly a typo/duplicate.",
            "Similar spelling but never co-occurring — may be two DISTINCT varieties "
            "(e.g. Clark vs Clary). Human judgement required.",
            "Merge direction: keep = more frequent spelling, merge = the rarer one.",
            "# of (Year, Trial) cells where BOTH spellings appear.",
            "Intentional numeric-suffix releases are NOT flagged: pairs with different digit "
            "content (Williams vs Williams82, Cutler71 vs Cutler) are treated as distinct.",
        ],
    })

    outpath = OUTDIR / "potential_duplicate_strains.xlsx"
    with pd.ExcelWriter(outpath, engine="openpyxl") as xl:
        readme.to_excel(xl, sheet_name="Readme", index=False)
        pair_df.to_excel(xl, sheet_name="Duplicate_pairs", index=False)
        clus_df.to_excel(xl, sheet_name="Duplicate_clusters", index=False)
        for sheet in ("Readme", "Duplicate_pairs", "Duplicate_clusters"):
            ws = xl.sheets[sheet]
            ws.freeze_panes = "A2"
            if ws.max_row > 1:
                ws.auto_filter.ref = ws.dimensions
            for col_cells in ws.columns:
                width = min(70, max(10, max(len(str(c.value)) for c in col_cells) + 2))
                ws.column_dimensions[col_cells[0].column_letter].width = width

    # console
    print("\n=== potential duplicate strains ===")
    if len(pair_df):
        print(pair_df["confidence"].value_counts().to_string())
        print(f"\n  {len(pair_df)} candidate pairs, {len(clus_df)} clusters")
        print("\n  top pairs:")
        print(pair_df[["confidence", "tier", "strain_a", "strain_b",
                       "shared_year_trial", "n_rows_a", "n_rows_b"]].head(15).to_string(index=False))
    else:
        print("  no candidate duplicate pairs found")
    print(f"\nOutput: {OUTDIR.name}/potential_duplicate_strains.xlsx")


if __name__ == "__main__":
    main()
