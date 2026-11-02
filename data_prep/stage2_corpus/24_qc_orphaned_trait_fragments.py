"""
24_qc_orphaned_trait_fragments.py
=================================
Sweep the corpus for ORPHANED SINGLE-TRAIT FRAGMENTS — an OCR artifact of the scanned
1941-1988 reports where a strain code was mis-read IN ONE TRAIT TABLE only (e.g. the
lodging or plant-height table), splitting that table's values off under a garbled code
while the same line's other traits read correctly under the true code.

Diagnosed manually first (script 23): in 1942 Group III the lodging table garbled
L6-690 -> "16-390" and L6-700 -> "L3-700"; in Group IV the height table garbled
C160 -> "250". These are NOT distinct strains and NOT duplicates — they are recoverable
fragments (the fragment's single trait fills the parent's gap).

Detection (per Year x TestMG, restricted to the OCR era <=1988):
  fragment  = strain whose NON-NULL values cover exactly ONE phenotype (a small orphan).
  parent    = a well-populated strain (>=3 non-null phenotypes) in the same Year x MG that
              is MISSING that trait (0 non-null for it) yet present at the fragment's
              locations (fragment.locs subset of parent.locs).
  HIGH      = the fragment code is an OCR-garble of the parent code (confusion-folded
              Levenshtein <=2: L<->1, O<->0, S<->5, B<->8, G<->6, plus a residual 3<->6/8).
  REVIEW    = single-trait fragment with a complementary parent but NO string-near code
              (e.g. 250->C160, which needed table-position + value match — see script 23).

Read-only. Output: analysis/data/analysis_results/Corpus_QC/orphaned_trait_fragments.{csv,md}
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
OUTDIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"

OCR_ERA_MAX = 1988                     # scanned-report era; >=1989 is the digital master DB
MAX_FRAG_TRAITS = 1                     # orphan carries exactly one non-null phenotype
MIN_PARENT_TRAITS = 3                  # parent is well-populated
MAX_FRAG_NONNULL = 25                  # an orphan is small (<= one row per location)
EDIT_MAX = 2

# OCR confusion folding: collapse confusable glyphs to one canonical rep, strip separators.
_FOLD = {"I": "1", "L": "1", "1": "1", "O": "0", "0": "0", "Q": "0",
         "S": "5", "5": "5", "B": "8", "8": "8", "Z": "2", "2": "2", "G": "6", "6": "6"}


def ocr_fold(code):
    s = re.sub(r"[^A-Za-z0-9]", "", str(code).upper())
    return "".join(_FOLD.get(ch, ch) for ch in s)


def fold_digits(code):
    """Digit subsequence after folding (L->1, S->5, O->0 ...). If two codes share this, their
    difference is purely alphabetic (safe OCR letter confusion); if it differs, a real digit
    differs -> could be a genuine adjacent SISTER selection, flag for a human check."""
    return re.sub(r"\D", "", ocr_fold(code))


def bounded_lev(a, b, maxd=2):
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
    df = pd.read_csv(CORPUS, low_memory=False,
                     usecols=["Year", "TestMG", "Test", "City", "Strain", "Phenotype", "Value_num"])
    df = df[(df.Year <= OCR_ERA_MAX) & df.Strain.notna() & df.TestMG.notna()].copy()
    df["Strain"] = df.Strain.astype(str)
    nn = df[df.Value_num.notna()]

    rows = []
    for (yr, mg), g in nn.groupby(["Year", "TestMG"]):
        # per-strain profile in this Year x MG (only non-null values count). tl = the set of
        # (Phenotype, City) cells the strain actually fills.
        prof = {}
        for st, gs in g.groupby("Strain"):
            prof[st] = {"traits": set(gs.Phenotype), "locs": set(gs.City), "n": len(gs),
                        "tl": set(zip(gs.Phenotype, gs.City))}
        frags = {st: p for st, p in prof.items()
                 if len(p["traits"]) == MAX_FRAG_TRAITS and p["n"] <= MAX_FRAG_NONNULL}
        parents = {st: p for st, p in prof.items() if len(p["traits"]) >= MIN_PARENT_TRAITS}
        for fst, fp in frags.items():
            trait = next(iter(fp["traits"]))
            ff = ocr_fold(fst)
            cands = []
            for pst, pp in parents.items():
                if pst == fst:
                    continue
                # complementary AT the fragment's locations: parent fills NONE of (trait, loc)
                # there (it may have the trait elsewhere), and is present at those locs.
                if not fp["locs"].issubset(pp["locs"]):
                    continue
                if any((trait, loc) in pp["tl"] for loc in fp["locs"]):
                    continue
                ed = bounded_lev(ff, ocr_fold(pst), EDIT_MAX)
                cands.append((ed, pp["n"], pst))
            if not cands:
                continue
            cands.sort(key=lambda x: (x[0], -x[1]))
            ed, pn, best = cands[0]
            near = [c for c in cands if c[0] <= EDIT_MAX]
            conf = ("HIGH" if ed <= EDIT_MAX and len(near) == 1
                    else "HIGH_AMBIG" if ed <= EDIT_MAX
                    else "REVIEW")
            # safe_ocr = the difference is purely alphabetic (letter/glyph confusion, incl.
            # L->1/S->5); check_digit = a real digit differs -> verify it isn't a sister selection.
            mclass = ("" if conf == "REVIEW"
                      else "safe_ocr" if fold_digits(fst) == fold_digits(best) else "check_digit")
            rows.append({
                "Year": yr, "MG": mg, "fragment": fst, "trait": trait,
                "n_vals": fp["n"], "frag_locs": len(fp["locs"]),
                "proposed_parent": best if conf != "REVIEW" else "",
                "edit_dist": ed if ed <= EDIT_MAX else "",
                "match_class": mclass, "n_string_near": len(near),
                "review_candidates": "" if conf != "REVIEW" else
                    ",".join(p for _, _, p in cands[:6]),
                "confidence": conf})

    out = pd.DataFrame(rows).sort_values(["confidence", "Year", "MG", "fragment"]) \
        if rows else pd.DataFrame(columns=["Year", "MG", "fragment", "trait", "confidence"])
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTDIR / "orphaned_trait_fragments.csv", index=False)

    L = ["# Orphaned single-trait fragments (OCR garble of a parent code in one trait table)\n",
         f"Scanned era <= {OCR_ERA_MAX}. {len(out)} fragments flagged "
         f"({out.confidence.value_counts().to_dict() if len(out) else {}}).\n",
         "HIGH = parent code is an OCR-garble (folded edit <=2) AND parent missing the trait AND "
         "co-located. REVIEW = complementary parent exists but no string-near code (needs the "
         "table-position/value check, cf. 250->C160).\n",
         "match_class: **safe_ocr** = difference is purely alphabetic glyph confusion "
         "(Horse->Morse, L->1); **check_digit** = a real digit differs — verify it is not a "
         "genuine adjacent SISTER selection (A3-103 vs A3-108) before applying.\n",
         "| Year | MG | fragment | trait | n | -> parent | edit | class | conf | review_candidates |",
         "|------|----|----------|-------|---|-----------|------|-------|------|-------------------|"]
    for _, r in out.iterrows():
        L.append(f"| {r.Year} | {r.MG} | {r.fragment} | {r.trait} | {r.n_vals} | "
                 f"{r.proposed_parent} | {r.edit_dist} | {r.match_class} | {r.confidence} "
                 f"| {r.review_candidates} |")
    (OUTDIR / "orphaned_trait_fragments.md").write_text("\n".join(L), encoding="utf-8")

    print(f"{len(out)} orphaned single-trait fragments flagged "
          f"({out.confidence.value_counts().to_dict() if len(out) else {}})")
    if len(out):
        print("by (confidence, match_class):",
              out.groupby(["confidence", "match_class"]).size().to_dict())
        print("\nHIGH + safe_ocr (auto-safe letter/glyph confusion):")
        hi = out[(out.confidence == "HIGH") & (out.match_class == "safe_ocr")]
        print(hi[["Year", "MG", "fragment", "trait", "n_vals", "proposed_parent", "edit_dist"]]
              .head(45).to_string(index=False) if len(hi) else "  (none)")
        print("\nHIGH + check_digit (verify not a sister selection):")
        cd = out[(out.confidence == "HIGH") & (out.match_class == "check_digit")]
        print(cd[["Year", "MG", "fragment", "trait", "proposed_parent", "edit_dist"]]
              .head(40).to_string(index=False) if len(cd) else "  (none)")
        # validation: are the manually-found ones caught?
        known = out[out.fragment.isin(["16-390", "L3-700", "L6-635", "L7-116C", "250"])]
        print("\nvalidation vs script-23 manual finds:")
        print(known[["Year", "MG", "fragment", "trait", "proposed_parent", "confidence"]]
              .to_string(index=False) if len(known) else "  (none caught)")
    print(f"\nWrote orphaned_trait_fragments.csv + .md to {OUTDIR.name}/")


if __name__ == "__main__":
    main()
