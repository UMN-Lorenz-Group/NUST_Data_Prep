"""
110_relabel_year.py
===================
General roster-driven F4U Test-code relabeler for the pre-1970 "mislabel / orphaned
leftover" class (the 1959 scramble bug class; see 108_relabel_1959.py for the prototype
and 107_label_integrity_audit.py for detection).

Unlike 108 (a full 1959 permutation), most pre-1970 years are CORRECTLY labeled except
for a single orphaned leftover group (an unmapped "Group_NN" carrying the real data of a
canonical code that combine_nust_outputs.py mapped to an empty slot). This applies a
VERIFIED per-year remap from the registry below, with safety checks:
  * each `new` code must currently be ABSENT in the F4U (we recover a dropped section,
    never collide with an existing one),
  * each `old` code must be present,
  * roster sanity: the old group's strains best-match the `new` code's Maturity-Group
    family in the Red PDF rosters (coverage), confirming the MG class.
Backs up the F4U to `.orig_prelabel` (once). Idempotent. Run with `--apply` to write.

Registry entries are added ONLY after manual PDF-roster confirmation (no auto-guessing).

Usage:  uv run python 110_relabel_year.py <year> [--apply]
"""
import sys
import re
import shutil
from collections import defaultdict
from pathlib import Path
import pandas as pd
import pdfplumber

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
NUST_DATA = Path("C:/Users/vramasub/Desktop/UMN_Projects/NUST_Projects/NUST_Data")
HIST = NUST_DATA / "NUST_Historical_Data_1941_1988"

# VERIFIED per-year relabels (old F4U code -> true canonical code). Confirmed by PDF
# rosters + combine_nust_outputs.py map analysis. See analysis_notes / memory.
VERIFIED_RELABELS = {
    # 1957 (PERMUTATION). Applied incrementally; entries whose `old` is already gone are skipped.
    #  - Group_11 -> PT-IV: combine mapped Group_10 -> PT-IV but that slot was empty; the real
    #    group-IV preliminary (southern C1068/CX171-.. at Beltsville/Carbondale) orphaned as the
    #    unmapped "Group_11". (Already applied.)
    #  - UT-00 -> UT-0, UT-0 -> PT-0: MG-00 did NOT exist until 1958 (1958 UT-00 = Acme/Crest/
    #    Manitoba; 1957 "UT-00" = Capital/Grant/Mandarin = MG-0). 1957's two Group-0 sections
    #    ("UNIFORM TEST GROUP 0" + "UNIFORM AND PRELIMINARY TEST GROUP 0") were mislabeled
    #    UT-00/UT-0 instead of UT-0/PT-0 (matching groups I-IV that year). User-confirmed.
    1957: {"Group_11": "PT-IV", "UT-00": "UT-0", "UT-0": "PT-0"},
    # 1985 (F4U POSITIONAL BACKWARD-SHIFT, MG III->IV). Confirmed 2026-07-02 by F4U-cell-roster vs
    # PDF-section-roster overlap: F4U UT-III==PDF PT-IIIA(ov39), PT-IIIA==PT-IIIB(36), PT-IIIB==UT-IV(19),
    # UT-IV==PT-IVA(27), PT-IVA==PT-IVB(28); true UT-III DROPPED, PT-IVB slot unused. This permutation
    # restores true UT-IV (from the PT-IIIB slot) + all PT-III*/PT-IV* cells; UT-III becomes an honest gap
    # until re-extracted (task #6, Phase 2). See ut_pt_mislabel_audit_1941_1990.md.
    1985: {"UT-III": "PT-IIIA", "PT-IIIA": "PT-IIIB", "PT-IIIB": "UT-IV",
           "UT-IV": "PT-IVA", "PT-IVA": "PT-IVB"},
    # 1977 (backward shift, MG III->IV; DOUBLE drop). Confirmed 2026-07-02 (verify_label_shift.py):
    # F4U UT-III==PDF PT-III(ov35, self ov4), PT-III==PT-IV(ov35, self ov2). true UT-III AND UT-IV both
    # DROPPED. Restores PT-III/PT-IV; UT-III+UT-IV become gaps (Phase 2 re-extract). (corpus loc-count is
    # noisy from multi-year summary columns; roster overlap is authoritative.)
    1977: {"UT-III": "PT-III", "PT-III": "PT-IV"},
    # 1988 (backward shift, EARLY block 00->II, 6-link). Confirmed 2026-07-02 (verify_label_shift.py):
    # UT-00==PDF UT-0(ov31,self15), UT-0==UT-I(16,self1), UT-I==PT-I(31,self2), UPT-I==UT-II(?),
    # UT-II==PT-IIA(30,self1), UPT-IIA==PT-IIB(25,self0). F4U uses UPT- for preliminary. true UT-00 dropped.
    # Restores UT-0/I/II + UPT-I/IIA/IIB; UT-00 becomes a gap. Geometry confirms (UT-I=7loc PT-shaped).
    1988: {"UT-00": "UT-0", "UT-0": "UT-I", "UT-I": "UPT-I", "UPT-I": "UT-II",
           "UT-II": "UPT-IIA", "UPT-IIA": "UPT-IIB"},
}


def norm(s):
    s = re.sub(r"\s*\([^)]*\)", "", str(s))
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return s.replace("O", "0").replace("L", "1").replace("I", "1")


def f4u_path(year):
    p = HIST / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv"
    return p if p.exists() else NUST_DATA / f"{year}_Processing" / "Files4Upload" / "phenotypesTable1.csv"


def pdf_group_rosters(year):
    """{MG_family: set(strain_norm)} from any 'group X' title/table pages (1940s-60s).
    Keyed by bare MG (0/00/I..) — used only for a coarse MG-class sanity check."""
    p = REPO / "input_files" / f"input_{year}" / f"{year}_done.pdf"
    if not p.exists():
        return {}
    title = re.compile(r"(uniform and preliminary|uniform|preliminary) test[.,]?\s*group\s+(0{1,2}|[ivx]+)", re.I)
    out = defaultdict(set)
    with pdfplumber.open(p) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            m = title.search(re.sub(r"\s+", " ", t.lower()))
            if not m:
                continue
            grp = m.group(2).upper()
            ws = pg.extract_words()
            if not ws:
                continue
            x0 = min(w["x0"] for w in ws)
            lines = defaultdict(list)
            for w in ws:
                if w["x0"] < x0 + 55:
                    lines[round(w["top"] / 3) * 3].append(w)
            for top in sorted(lines):
                tok = sorted(lines[top], key=lambda w: w["x0"])
                n = norm(re.sub(r"^\d+\.?$", "", tok[0]["text"]))
                if n and len(n) >= 3 and not n.isdigit():
                    out[grp].add(n)
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: 110_relabel_year.py <year> [--apply]")
    year = int(sys.argv[1])
    apply = "--apply" in sys.argv
    remap = VERIFIED_RELABELS.get(year)
    if not remap:
        sys.exit(f"No VERIFIED_RELABELS entry for {year} — add one (PDF-confirmed) first.")

    f4u = f4u_path(year)
    if not f4u.exists():
        sys.exit(f"F4U not found: {f4u}")
    d = pd.read_csv(f4u, dtype=str, low_memory=False)
    tcol = next(c for c in d.columns if c.lower() == "test")
    scol = next(c for c in d.columns if c.lower() in ("strain", "germplasmid", "entry"))
    codes = set(d[tcol].dropna().unique())
    rosters = {c: {norm(s) for s in d[d[tcol] == c][scol].dropna() if str(s).strip().lower() != "mean"}
               for c in codes}
    pdfr = pdf_group_rosters(year)

    print(f"=== {year} relabel plan ===  F4U codes: {sorted(codes)}")
    active = {o: n for o, n in remap.items() if o in codes}   # idempotent: skip already-applied
    skipped = [o for o in remap if o not in codes]
    if skipped:
        print(f"  (skipping already-applied / absent: {skipped})")
    news = list(active.values())
    problems = []
    if len(news) != len(set(news)):
        problems.append(f"two codes map to the same target (merge): {news}")
    for old, new in active.items():
        # a target that already exists is only OK if it is itself vacated by the permutation
        if new in codes and new not in active:
            problems.append(f"{new}: already present and not vacated — would collide")
        mg = re.sub(r"^(UT|PT)-", "", new)
        cov = None
        if pdfr.get(mg):
            fr = rosters[old]
            cov = round(len(fr & pdfr[mg]) / max(1, len(fr)), 2)
        print(f"  {old:9s}[{len(rosters[old]):2d} strains, {len(d[d[tcol]==old])} rows] -> {new}"
              f"   PDF group-{mg} coverage={cov}")
        if cov is not None and cov < 0.4:
            problems.append(f"{old}->{new}: low PDF group-{mg} coverage {cov}")
    if not active:
        print("Nothing to do (all already applied)."); return
    if problems:
        print("\n".join("  ! " + p for p in problems))
        if any("collide" in p or "merge" in p for p in problems):
            sys.exit("ABORT: structural problem with remap.")
        print("  (coverage warnings only — PDF rosters are noisy; proceeding requires --apply)")
    remap = active

    if not apply:
        print("\nDRY RUN — re-run with --apply to write.")
        return
    backup = f4u.with_suffix(".csv.orig_prelabel")
    if not backup.exists():
        shutil.copy2(f4u, backup)
        print(f"  backup -> {backup.name}")
    d[tcol] = d[tcol].map(lambda x: remap.get(x, x))
    d.to_csv(f4u, index=False)
    print(f"\nApplied {remap} -> {f4u}")
    print(f"  new Test codes: {sorted(d[tcol].dropna().unique())}")


if __name__ == "__main__":
    main()
