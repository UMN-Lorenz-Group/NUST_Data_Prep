"""
Generate `anchor_leak_fixes.csv` for fix_maturity_anchor.py.

Two correction FAMILIES, kept apart by provenance tag so each can be reverted alone and
neither can compound on the other's rows:

  |fix_mat_anchor   anchor-row COLUMN LEAK -- the "Mean of N Tests" off-by-one that gives a
                    location its LEFT neighbour's anchor. Per-column additive shift.
  |fix_leap_doy     leap-year 1-day DOY slip from non-leap date conversion. Per-column too:
                    the 1972 lesson is that a blanket per-year shift corrupts the majority
                    of columns, because the damage lands per (year x test x MG) table and,
                    within 1972, per row-class.

Sources, in precedence order
----------------------------
1. `maturity_anchor_row_audits.csv` -- columns a verification agent read off the rendered
   page. Highest authority; wins any conflict.
2. `maturity_anchor_vs_oracle_defects.csv` -- HIGH-confidence oracle columns. HIGH means
   both anchor routes agree (printed date AND planted+days) and the offset match is strong
   and unambiguous; measured 87/87 correct against the independently verified rows across
   1944/1948/1952/1955/1956/1965/1988. MED/LOW are deliberately NOT used.

Guard: every emitted row guards on the table's own anchor check at the printed anchor DOY,
so each fix is self-limiting and idempotent, and re-running after a rebuild is a no-op.

Usage:
    python data_prep/stage2_corpus/build_anchor_leak_fixes.py [--min-delta 2]
"""

from __future__ import annotations

import argparse
import calendar
import sys
from pathlib import Path

import pandas as pd

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
QC = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
OUT = REPO / "data_prep" / "stage2_corpus" / "anchor_leak_fixes.csv"

COLS = ["id", "year", "mg", "test", "city", "state", "op", "add", "min_v", "max_v",
        "exclude", "guard_strain", "guard_true", "guard_tol", "guard_mode", "tag", "note"]

def already_fixed() -> set[tuple]:
    """Cells an earlier pass already corrected -- re-emitting them would double-shift.

    Derived from the existing batch plus the hand-written CONFIG ids rather than hardcoded,
    so the exclusion cannot drift out of date as that batch grows.
    """
    keys = set()
    tier = REPO / "data_prep" / "stage2_corpus" / "tier23_maturity_fixes.csv"
    if tier.exists():
        t = pd.read_csv(tier, dtype=str, keep_default_na=False)
        for r in t.to_dict("records"):
            keys.add((str(r["year"]), str(r["mg"]).strip(), str(r["test"]).strip(),
                      str(r["city"]).strip().lower()))
    # cells corrected by the in-script CONFIG list (not in any CSV)
    keys |= {
        ("1950", "III", "PT", "worthington"), ("1950", "III", "PT", "urbana"),
        ("1950", "III", "PT", "columbia"), ("1957", "III", "UT", "lincoln"),
        ("1957", "III", "UT", "ames"), ("1955", "III", "UT", "ames"),
        ("1957", "0", "PT", "hoytville"), ("1989", "I", "UT", "corwith"),
        ("1977", "III", "PT", "columbia"), ("1966", "II", "UT", "columbia"),
        ("1968", "II", "UT", "columbia"), ("1986", "II", "PT", "arlington"),
        ("1967", "II", "UT", "hoytville"), ("1968", "II", "UT", "spickard"),
        ("2011", "IV", "PT", "portageville-clay"), ("2012", "III", "PT", "hoytville"),
        ("1996", "I", "PT", "brookings"), ("2004", "I", "PT", "lamberton"),
        ("2011", "I", "UT", "west lafayette"), ("2004", "0", "PT", "watertown"),
    }
    return keys


ALREADY_FIXED = already_fixed()

# Oracle HIGH-confidence FALSE POSITIVES, caught by the shared-check (Gate-2) PT/UT audit and
# then PDF-verified. The oracle assumes each (Year,Test,MG,City) corpus group is ONE printed
# column; where the corpus cell is actually a MERGED / MIXED-MG pile, a low-strain (n=3) offset
# match binds a spurious PDF column and yields a confident-but-wrong shift. In both cases below
# the PT side already matched the report and the UT "fix" over-shot. Excluded here and reverted
# in the corpus. Lesson: treat oracle rows with a small n_offsets_matched on a City that also
# carries other-MG strains as suspect, not HIGH.
ORACLE_FALSE_POSITIVE = {
    ("1969", "III", "UT", "ottawa"),     # corpus "Ottawa" = MG-IV KS + MG-III + null MG-00 pile;
                                         # true Clark63=268/Wayne=260, our +22 overshot. PT correct.
    ("1960", "III", "UT", "manhattan"),  # two Manhattan sub-cols (Shelby 275/273) + mixed cell;
                                         # pre-fix UT Shelby=274 was correct, our -17 corrupted it.
}
ALREADY_FIXED |= ORACLE_FALSE_POSITIVE


# ---------------------------------------------------------------------------------------
# WHOLE-TABLE leap corrections (city="*").
#
# Used only where a table is uniformly affected AND that uniformity is demonstrated, never
# assumed -- the 1972 lesson is that a blanket per-year +1 corrupts the majority of columns.
#
# 1988 qualifies on unusually strong evidence, and it carries its own built-in control:
#   * every bound column in UT 0/II/III/IV and PT I/II/III/IV reads delta = +1 exactly
#     (57 of 57 columns), at a mean offset-match fraction of 0.993
#   * UT-00 reads delta = 0 across all 6 of its columns -- and UT-00 is precisely the one
#     1988 table that was re-derived from the PDF with leap-correct code
#     (Source = Recovered_UTPT_1988_UT00). The clean table is the one that cannot be wrong.
#   * independently, agent verification found 1988 PT off-by-one across all 7 PT tables
#     (most columns at a perfect 28/28-38/38 offset fit) plus UT-II and UT-IV columns.
# These columns sit at MED rather than HIGH only because the 1988 layout does not expose
# both anchor routes in one window (identity_ok is False throughout), not because the
# binding is weak.
#
# 1988 UT-I is deliberately ABSENT: the oracle bound no columns there, so there is no
# evidence either way. It is left uncorrected and flagged rather than assumed.
WHOLE_TABLE_LEAP = [
    ("1988", "PT", "I"), ("1988", "PT", "II"), ("1988", "PT", "III"), ("1988", "PT", "IV"),
    ("1988", "UT", "0"), ("1988", "UT", "II"), ("1988", "UT", "III"), ("1988", "UT", "IV"),
]


def slug(s: str) -> str:
    return "".join(ch for ch in str(s) if ch.isalnum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-delta", type=float, default=2.0,
                    help="min |delta| for an ANCHOR fix (below this it is leap/noise)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite the FROZEN batch (see the guard below)")
    args = ap.parse_args()

    # FREEZE GUARD. This generator reads maturity_anchor_vs_oracle_defects.csv, which is
    # regenerated every time the oracle runs against the CURRENT corpus. Once the fixes are
    # applied, that file reflects the CORRECTED corpus (~17 residual defects, not the original
    # ~217), so a naive re-run would shrink the batch to almost nothing and silently
    # UNDER-correct on the next rebuild. The applied batch is the durable, committed artifact.
    # Regenerating it correctly requires the PRE-FIX defects file (git-restore it first).
    if OUT.exists() and not args.force:
        cur = pd.read_csv(OUT, dtype=str)
        try:
            hi = pd.read_csv(QC / "maturity_anchor_vs_oracle_defects.csv")
            n_hi = int((hi.confidence == "HIGH").sum())
        except Exception:
            n_hi = -1
        if len(cur) > 50 and 0 <= n_hi < len(cur) // 2:
            sys.exit(
                f"REFUSING to overwrite {OUT.name}: it has {len(cur)} frozen entries but the "
                f"oracle-defects input now shows only {n_hi} HIGH defects (post-fix state). "
                f"Regenerating would under-correct. Restore the PRE-FIX defects CSV first, or "
                f"pass --force if you really intend to rebuild.")

    rows: dict[tuple, dict] = {}

    # ---- source 2 first, so source 1 can overwrite it ---------------------------------
    dfx = pd.read_csv(QC / "maturity_anchor_vs_oracle_defects.csv")
    dfx = dfx[dfx.confidence == "HIGH"]
    for r in dfx.itertuples():
        key = (str(r.Year), str(r.TestMG), str(r.TestType), str(r.City).strip().lower())
        if key in ALREADY_FIXED:
            continue
        delta = float(r.delta)
        leap = (r.klass == "OFF_BY_ONE_LEAP") or (
            abs(delta) == 1 and calendar.isleap(int(r.Year)))
        if not leap and abs(delta) < args.min_delta:
            continue
        fam = "|fix_leap_doy" if leap else "|fix_mat_anchor"
        rows[key] = dict(
            id=f"{r.Year}_{r.TestMG}_{slug(r.City)}_{r.TestType}_"
               f"{'leap' if leap else 'orc'}",
            year=str(r.Year), mg=str(r.TestMG), test=r.TestType, city=str(r.City).strip(),
            state=("" if pd.isna(r.State) else str(r.State).strip()),
            op="shift", add=f"{delta:g}", min_v="", max_v="", exclude="",
            guard_strain="", guard_true=f"{r.anchor_doy:g}", guard_tol="0",
            # tag-mode: idempotency comes from the provenance marker. A value guard here
            # would key on the table's anchor-check name, and if that slug does not match
            # the corpus strain spelling the guard finds nothing and the fix SILENTLY
            # no-ops -- the one failure mode that would look like success.
            guard_mode="tag", tag=fam,
            note=(f"ORACLE HIGH ({r.klass}): printed anchor {r.anchor_date}="
                  f"{r.anchor_doy:g} vs corpus-implied {r.corpus_implied_anchor:g}; "
                  f"match {r.n_offsets_matched}/{r.n_compared} strains, p.{r.page}."))

    n_oracle = len(rows)

    # ---- source 1: agent-verified rows override ---------------------------------------
    aud = pd.read_csv(QC / "maturity_anchor_row_audits.csv", dtype=str, keep_default_na=False)
    for r in aud.to_dict("records"):
        try:
            rep = float(r.get("report_anchor_doy") or "")
            cor = float(r.get("corpus_anchor_doy") or "")
        except ValueError:
            continue
        shift = rep - cor
        if abs(shift) < args.min_delta:
            continue
        tst = "PT" if "PRELIM" in str(r.get("test", "")).upper() \
                      or str(r.get("test", "")).upper().startswith("PT") else "UT"
        city = str(r.get("city", "")).strip()
        key = (str(r.get("year")), str(r.get("mg")).strip(), tst, city.lower())
        if key in ALREADY_FIXED:
            continue
        rows[key] = dict(
            id=f"{r.get('year')}_{r.get('mg')}_{slug(city)}_{tst}_ver",
            year=r.get("year"), mg=str(r.get("mg")).strip(), test=tst, city=city,
            state=str(r.get("state", "")).strip(), op="shift", add=f"{shift:g}",
            min_v="", max_v="", exclude="", guard_strain="",
            guard_true=f"{rep:g}", guard_tol="0", guard_mode="tag",
            tag="|fix_mat_anchor",
            note=f"PDF-VERIFIED ({r.get('verdict','')}): report anchor {rep:g} vs corpus "
                 f"{cor:g}. {str(r.get('note',''))[:160]}")

    # ---- whole-table leap shifts (city="*") -------------------------------------------
    for yr, tst, mg in WHOLE_TABLE_LEAP:
        rows[(yr, mg, tst, "*")] = dict(
            id=f"{yr}_{mg}_ALL_{tst}_leap", year=yr, mg=mg, test=tst, city="*", state="",
            op="shift", add="1", min_v="", max_v="", exclude="", guard_strain="",
            guard_true="", guard_tol="0", guard_mode="tag", tag="|fix_leap_doy",
            note=(f"WHOLE-TABLE leap +1: every bound column in this table reads delta=+1 "
                  f"while 1988 UT-00 (the table re-derived with leap-correct code) reads 0. "
                  f"Corroborated by independent PDF verification of the 1988 PT tables."))

    d = pd.DataFrame(list(rows.values()), columns=COLS).sort_values(
        ["year", "test", "mg", "city"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT, index=False)

    n_leap = int((d.tag == "|fix_leap_doy").sum())
    print(f"wrote {OUT.name}: {len(d)} entries "
          f"({len(d) - n_leap} anchor, {n_leap} leap)")
    print(f"  from oracle HIGH: {n_oracle}   agent-verified overrides applied after")
    print(f"\n  by year:\n{d.groupby(['year']).size().to_string()}")
    print(f"\n  largest shifts:")
    dd = d.copy()
    dd["a"] = pd.to_numeric(dd.add_, errors="coerce") if "add_" in dd else \
        pd.to_numeric(dd["add"], errors="coerce")
    print(dd.reindex(dd.a.abs().sort_values(ascending=False).index)
            .head(15)[["id", "add", "guard_true", "tag"]].to_string(index=False))


if __name__ == "__main__":
    main()
