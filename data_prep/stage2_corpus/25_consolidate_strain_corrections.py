"""
25_consolidate_strain_corrections.py
====================================
Gather EVERY proposed Strain correction discovered across the QC work into one review
artifact, keyed on the literal (Strain, Year) pair, with provenance + corpus impact.
Read-only: writes a review table only; applies NOTHING.

Sources:
  ocr_short_code  (6)  : already in 10_assemble STRAIN_OCR_FIX  (user-confirmed)        [applied*]
  pi_restore      (6)  : already in 10_assemble STRAIN_SOURCE_RESTORE (1941, user-conf) [applied*]
  pi_normalize    (n)  : P.I./PI. -> 'PI #####' GRIN convention (already PI_RE)          [applied*]
  numeric_recovery(20) : origin-table prefix recovery (script 23, all confirmed)         [NEW review]
  fragment_safe   (39) : orphaned single-trait fragments, HIGH + safe_ocr (script 24)    [NEW review]
  * "applied" = committed in 10_assemble but DEFERRED (takes effect next rebuild).

For each mapping: n_corpus_rows (current Strain in that year) and whether the target already
exists same Year+MG (=> the correction UNIFIES an OCR-split line) or is new (relabel).
Conflicts on (Strain, Year) are surfaced, not silently resolved.

Output: analysis/data/analysis_results/Corpus_QC/strain_corrections_consolidated.{csv,md,xlsx}
"""
import sys
import re
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
CORPUS = REPO / "analysis" / "data" / "_shared" / "nust_1941_2025_combined.csv"
QC = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
REF = REPO / "reference" / "nust_strain_corrections.csv"   # machine apply-list for 10_assemble

# already in 10_assemble (deferred) ---------------------------------------------------
# NB: MS (1950) is NOT here — the neighbour gate + trait-gap show it is M9 (not the earlier
# string-only guess M8: M8 already has Maturity at MS's locs, M9 is the one missing it). It comes
# in via the fragment_check_digit source (MS->M9) instead.
OCR_SHORT = {("3H", 1944): "H3", ("HI", 1943): "H1", ("Ll", 1962): "L1",
             ("MI", 1948): "M1", ("Ml", 1949): "M1"}
PI_RESTORE = {("68474", 1941): "PI 68474", ("70478", 1941): "PI 70478",
              ("88447-2", 1941): "PI 88447-2", ("91161", 1941): "PI 91161",
              ("92717", 1941): "PI 92717", ("13-177", 1941): "Manchuria 13-177"}
# value/position-matched fragments + poor-OCR garbles (scripts 23/24 + manual; user-confirmed)
FRAGMENT_FIX = {("it;re", 1971): "Wye", ("M76-15.3", 1983): "M76-281",
                ("Ancka", 1969): "Anoka", ("Eark", 1969): "Hark", ("Chippeva6", 1969): "Chippewa64",
                ("M60-406111", 1969): "M60-406", ("M6C-222", 1969): "M60-222",
                ("L66-4120", 1969): "L66-1420", ("Md62-3303-3", 1969): "Md63-3303-3",
                # REVIEW-tier reordered/abbrev garbles, neighbour-gate confirmed (2026-06):
                ("91109P.I.", 1942): "PI 91109", ("91161P.I.", 1942): "PI 91161",
                ("92592P.I.", 1942): "PI 92592", ("92717P.I.", 1942): "PI 92717",
                ("68666P.I.", 1944): "PI 68666", ("31596F.C.", 1944): "F.C.31596",
                ("Wis.Han.3Sel.", 1943): "W.Man.3Sel.", ("Wis.Man.507", 1944): "Wis.Mandarin507",
                ("Wis.606Man.", 1944): "Wis.Manchu606", ("ManchuWis.3", 1945): "Wis.Manchu3",
                ("L7-116C", 1942): "L7-1160", ("Steele+", 1974): "Steele",
                # Mandarin(Ott.) -> Mandarin(Ottawa): normalize the abbreviation in ALL its years
                ("Mandarin(Ott.)", 1950): "Mandarin(Ottawa)", ("Mandarin(Ott.)", 1951): "Mandarin(Ottawa)",
                ("Mandarin(Ott.)", 1954): "Mandarin(Ottawa)", ("Mandarin(Ott.)", 1955): "Mandarin(Ottawa)"}
PI_RE = re.compile(r"(?i)^P\.?\s*I\.?[\s.\-]*(\d.*)$")


def main():
    corp = pd.read_csv(CORPUS, low_memory=False, usecols=["Year", "TestMG", "Strain"])
    corp["Strain"] = corp.Strain.astype(str)
    # quick lookups
    by_sy = corp.groupby(["Strain", "Year"]).size()
    sy_mg = corp.groupby(["Strain", "Year"])["TestMG"].agg(lambda x: sorted(set(x.astype(str))))
    s_ym = corp.groupby("Strain").apply(lambda d: set(zip(d.Year, d.TestMG.astype(str))),
                                        include_groups=False)

    recs = []

    def add(cur, yr, proposed, source, status, note=""):
        recs.append({"current_strain": cur, "year": yr, "proposed_strain": proposed,
                     "source": source, "status": status, "note": note})

    # neighbour-confirmation status per fragment (script 26): (fragment, year) -> CONFIRMED?
    nbr = {}
    nc = QC / "fragment_neighbor_confirmation.csv"
    if nc.exists():
        nd = pd.read_csv(nc, keep_default_na=False)
        nbr = {(str(r.fragment), int(r.Year)): (r.status == "CONFIRMED") for r in nd.itertuples()}

    # 1) ocr_short_code + pi_restore + manual value-matched fragments (all user/source-confirmed)
    for (s, y), v in OCR_SHORT.items():
        add(s, y, v, "ocr_short_code", "apply")
    for (s, y), v in PI_RESTORE.items():
        add(s, y, v, "pi_restore", "apply")
    for (s, y), v in FRAGMENT_FIX.items():
        add(s, y, v, "fragment_value_match", "apply", "value/position-matched (user-confirmed)")

    # 2) pi_normalize: distinct P.I./PI. corpus forms -> 'PI #####' (per year present)
    pis = sorted(set(corp.Strain[corp.Strain.str.contains(r"(?i)^P\.?I\.?\d|^P\.?\s*I\.?\s*\d",
                                                           regex=True, na=False)]))
    for f in pis:
        prop = PI_RE.sub(r"PI \1", f)
        if prop != f:
            for y in sorted(set(corp.Year[corp.Strain == f])):
                add(f, int(y), prop, "pi_normalize", "apply")

    # 3) numeric_recovery (script 23, origin-table confirmed)
    nv = QC / "numeric_strain_source_verification.csv"
    if nv.exists():
        d = pd.read_csv(nv, keep_default_na=False)
        for _, r in d[d.status == "confirmed"].iterrows():
            add(str(r.corpus_strain), int(r.year), str(r.source_code),
                "numeric_recovery", "apply", "origin-table prefix recovery (script 23)")

    # 4) orphaned fragments (script 24, full HIGH tier) — status from the neighbour gate (script 26):
    #    apply if the source-table neighbours line up, else review (likely a sister selection).
    fr = QC / "orphaned_trait_fragments.csv"
    if fr.exists():
        d = pd.read_csv(fr, keep_default_na=False)
        d = d[d.confidence == "HIGH"]
        for _, r in d.iterrows():
            ok = nbr.get((str(r.fragment), int(r.Year)), False)
            add(str(r.fragment), int(r.Year), str(r.proposed_parent),
                f"fragment_{r.match_class}", "apply" if ok else "review",
                f"orphaned {r.trait} fragment; neighbour-gate {'CONFIRMED' if ok else 'unconfirmed'}")

    df = pd.DataFrame(recs)

    # corpus impact + unify/relabel
    def impact(r):
        n = int(by_sy.get((r.current_strain, r.year), 0))
        tgt = s_ym.get(r.proposed_strain, set())
        mgs = sy_mg.get((r.current_strain, r.year), [])
        unify = any((r.year, mg) in tgt for mg in mgs)
        return pd.Series({"n_rows": n,
                          "MG": ",".join(mgs),
                          "effect": "UNIFY (target present same yr+MG)" if unify
                          else ("target elsewhere" if tgt else "relabel (new)")})
    df = pd.concat([df, df.apply(impact, axis=1)], axis=1)

    # de-dup (current_strain, year); surface conflicts (different proposed targets)
    df["key"] = list(zip(df.current_strain, df.year))
    conf = (df.groupby("key")["proposed_strain"].nunique())
    conflict_keys = set(conf[conf > 1].index)
    df["conflict"] = df["key"].isin(conflict_keys)
    df = (df.sort_values(["status", "source", "year", "current_strain"])
            .drop_duplicates(["current_strain", "year", "proposed_strain"]))

    QC.mkdir(parents=True, exist_ok=True)
    cols = ["status", "source", "year", "MG", "current_strain", "proposed_strain",
            "effect", "n_rows", "conflict", "note"]
    df[cols].to_csv(QC / "strain_corrections_consolidated.csv", index=False)
    try:
        with pd.ExcelWriter(QC / "strain_corrections_consolidated.xlsx", engine="openpyxl") as xl:
            df[df.status == "apply"][cols].to_excel(xl, sheet_name="apply", index=False)
            df[df.status == "review"][cols].to_excel(xl, sheet_name="review_held", index=False)
            if conflict_keys:
                df[df.conflict][cols].to_excel(xl, sheet_name="conflicts", index=False)
    except Exception as e:
        print(f"  (xlsx skipped: {e})")

    # MACHINE APPLY-LIST consumed by 10_assemble: only status==apply, the columns it needs.
    apply_df = (df[df.status == "apply"][["current_strain", "year", "proposed_strain", "source"]]
                .rename(columns={"proposed_strain": "corrected_strain"})
                .sort_values(["year", "current_strain"]))
    REF.parent.mkdir(parents=True, exist_ok=True)
    apply_df.to_csv(REF, index=False)

    rev = df[df.status == "review"]
    L = ["# Consolidated Strain corrections\n",
         f"{len(df)} mappings: {df.status.value_counts().to_dict()}. The status==apply rows are "
         f"written to `reference/{REF.name}` and applied by 10_assemble (deferred).\n",
         f"apply by source: {df[df.status=='apply'].source.value_counts().to_dict()}.\n",
         f"UNIFY (merges an OCR-split line into its twin): {(df.effect.str.startswith('UNIFY')).sum()}; "
         f"conflicts (same Strain+Year -> different target): {df.conflict.sum()}.\n",
         "## review — held (not applied)\n",
         "| source | year | MG | current | -> proposed | effect | rows | note |",
         "|--------|------|----|---------|-------------|--------|-----:|------|"]
    for _, r in rev.sort_values(["year", "current_strain"]).iterrows():
        L.append(f"| {r.source} | {r.year} | {r.MG} | {r.current_strain} | {r.proposed_strain} "
                 f"| {r.effect} | {r.n_rows} | {r.note} |")
    if conflict_keys:
        L.append("\n## Conflicts (review which target is correct)\n")
        for _, r in df[df.conflict].sort_values("current_strain").iterrows():
            L.append(f"- {r.current_strain} ({r.year}) -> {r.proposed_strain}  [{r.source}]")
    (QC / "strain_corrections_consolidated.md").write_text("\n".join(L), encoding="utf-8")

    print(f"{len(df)} consolidated mappings -> {df.status.value_counts().to_dict()}")
    print(f"apply by source: {df[df.status=='apply'].source.value_counts().to_dict()}")
    print(f"UNIFY: {(df.effect.str.startswith('UNIFY')).sum()} | conflicts: {df.conflict.sum()}")
    if len(rev):
        print(f"\nheld for review ({len(rev)}):")
        print(rev[["source", "year", "current_strain", "proposed_strain", "n_rows"]].to_string(index=False))
    print(f"\nWrote reference/{REF.name} ({len(apply_df)} apply rows) + consolidated.{{csv,md,xlsx}}")


if __name__ == "__main__":
    main()
