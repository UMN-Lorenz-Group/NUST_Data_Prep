"""
fix_maturity_anchor.py
======================
Generalized, PDF-verified re-anchor / repair tool for the maturity anchor-error family surfaced by
audit_maturity_pt_ut_agreement.py (the shared-check PT-vs-UT gate). Supersedes the one-off
fix_1950_ptiii_maturity.py by driving every correction from a single CONFIG list.

Mechanism (same as the 1950/1957/1955 cases): pre-1989 F4U maturity is stored as DOY = per-location
anchor + strain offset. When F4U assigned a WRONG per-location anchor to one test (UT or PT), every
strain at that (year, MG, test, location) is shifted by a constant. The report's "<check> matured"
row gives the true anchor; the OTHER test (and the report) give the true value. Fix = add the signed
per-location correction to the wrong test's DOY (offsets among strains preserved). A few cells are
partial corruptions or physically-impossible values -> op="null".

EVERY entry here was verified cell-by-cell against the Red report PDF (not the gate alone — the gate
mis-attributes at latitude-extreme sites, so the PDF is the authority for which test is wrong and by
how much). See the per-entry `note` for the table/anchor used.

Each op is idempotent + guarded: it acts only while the anomaly signature is present (the guard
check's current DOY is still far from its verified true value), so re-running after the fix is a
no-op. Safe to run repeatedly and in any order (cells are disjoint).

Usage: PYTHONUTF8=1 uv run python data_prep/stage2_corpus/fix_maturity_anchor.py [--apply]
Then rebuild 11 (wide) + 12 (era) + regenerate plots, or just run finalize_corpus_recoveries.py.
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(os.environ.get("NUST_REPO", "C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep"))
SH = REPO / "analysis" / "data" / "_shared"
TAG = "|fix_mat_anchor"          # anchor / re-anchor corrections
TAG_LEAP = "|fix_leap_doy"       # leap-year 1-day DOY conversion corrections
ALL_TAGS = (TAG, TAG_LEAP)


def nk(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)", "", str(s)).lower())


# ---------------------------------------------------------------------------------------------
# CONFIG — one entry per verified severe cell. Populated as PDF verification completes.
#   op="shift": new_DOY = old_DOY + add   (for every Maturity row in the group, except `exclude`)
#   op="null" : set Maturity Value_num -> NaN for the group (impossible / unreconstructable)
#   guard_strain/guard_true/guard_tol: idempotency + safety — skip the entry unless the guard
#       check's current median DOY at the group differs from guard_true by > guard_tol.
# ---------------------------------------------------------------------------------------------
CONFIG = [
    # 1950 PT-III (migrated from fix_1950_ptiii_maturity.py; already baked into the current corpus,
    # so these no-op unless a rebuild reverts them). PDF Table 43: Lincoln matured W.Lafayette 10/4
    # =277 (correct), Worthington 9/22=265, Urbana 9/30=273, Columbia 9/15=258; F4U had 277/285/290/293.
    dict(id="1950_III_Worthington_PT", year="1950", mg="III", test="PT", city="Worthington", state="IN",
         op="shift", add=-20.0, exclude=[], guard_strain="Lincoln", guard_true=265, guard_tol=8,
         note="PDF Table 43: Lincoln matured 9/22=DOY265 at Worthington; F4U anchor 285 (+20)."),
    dict(id="1950_III_Urbana_PT", year="1950", mg="III", test="PT", city="Urbana", state="IL",
         op="shift", add=-17.0, exclude=[], guard_strain="Lincoln", guard_true=273, guard_tol=8,
         note="PDF Table 43: Lincoln matured 9/30=DOY273 at Urbana; F4U anchor 290 (+17)."),
    dict(id="1950_III_Columbia_PT", year="1950", mg="III", test="PT", city="Columbia", state="MO",
         op="shift", add=-35.0, exclude=[], guard_strain="Lincoln", guard_true=258, guard_tol=8,
         note="PDF Table 43: Lincoln matured 9/15=DOY258 at Columbia; F4U anchor 293 (+35)."),
    dict(id="1957_III_Lincoln_UT", year="1957", mg="III", test="UT", city="Lincoln", state="NE",
         op="shift", add=25.0, exclude=[],
         guard_strain="Lincoln", guard_true=279, guard_tol=8,
         note="PDF Table 40 (UT+PT G-III): Lincoln matured 10-6 = DOY 279 at Lincoln NE; corpus UT "
              "had 254 (=Columbia's 9-11 anchor). PT already 279 (correct)."),
    dict(id="1957_III_Ames_UT", year="1957", mg="III", test="UT", city="Ames", state="IA",
         op="shift", add=22.0, exclude=[],
         guard_strain="Lincoln", guard_true=277, guard_tol=8,
         note="PDF Table 40: Lincoln matured 10-4 = DOY 277 at Ames; corpus UT had 255. PT 277 (ok)."),
    dict(id="1955_III_Ames_UT", year="1955", mg="III", test="UT", city="Ames", state="IA",
         op="shift", add=24.0, exclude=[],
         guard_strain="Lincoln", guard_true=260, guard_tol=8,
         note="PDF Table 44 (UT+PT G-III): Lincoln matured 9-17 = DOY 260 at Ames (days-to-mature "
              "129, planted 5-11); corpus UT had 236. PT 260 (ok)."),
    dict(id="1957_0_Hoytville_PT", year="1957", mg="0", test="PT", city="Hoytville", state="OH",
         op="shift", add=-23.0, exclude=[],
         guard_strain="Mandarin", guard_true=248, guard_tol=8,
         note="PDF Tables 3 (UT) & 9 (UT+PT) G-0: Mandarin(Ottawa) matured 9-5 = DOY 248 at Hoytville "
              "(days-to-mature 99). Corpus UT=248 (CORRECT); PT=271 is the error. Gate mis-attributed "
              "(Hoytville is a genuine early-maturity Ohio site, excluded from the report mean)."),
    dict(id="1989_I_Corwith_UT_null", year="1989", mg="I", test="UT", city="Corwith", state="IA",
         op="null", exclude=[], guard_strain="Sibley", guard_true=257, guard_tol=8,
         note="UT-I Sibley Corwith printed 09/28 (DOY 271) is ~14 d too late: it reverses Corwith's "
              "normal early ordering vs Brookings/Waseca/Lamberton in ALL 8 other UT-I years (1989 "
              "+11/+14/+16 vs a -14/-5/+1 norm), and 271 is above Corwith's own 1977-87 UT-I range "
              "(252-268, ~257). The printed Mean-12 (262) was computed WITH the late value, so the "
              "report can't self-diagnose (error is upstream). True ~257 but no clean anchor and the "
              "PT-I 243 is itself mildly early, so NULL the mis-anchored UT-I Corwith column (PT-I "
              "preserved). See maturity_source_report_anomalies.md."),
    dict(id="1977_III_Columbia_PT", year="1977", mg="III", test="PT", city="Columbia", state="MO",
         op="null", exclude=["Cutler71"],
         guard_strain="", guard_true=240, guard_tol=0,
         note="PDF 'PRELIMINARY TEST III 1977' p112: Columbia anchor matured 10-3 = DOY 276 "
              "(Cutler71 corpus=272, valid). But Williams=212 & ~12 other strains sit at DOY 212-221 "
              "(late July — impossible for MG III), a partial corruption Cutler71 escaped -> not a "
              "uniform offset. NULL the impossible values (<240); Cutler71 retained. UT-III Columbia "
              "(Recovered, ~270) is correct and untouched."),
    dict(id="1966_II_Columbia_UT", year="1966", mg="II", test="UT", city="Columbia", state="MO",
         op="shift", add=-22.0, exclude=[],
         guard_strain="Amsoy", guard_true=252, guard_tol=8,
         note="PDF UT-II Table 47 p69 (Harosoy63 matured 9-5=DOY248, footer 5-23+105=248; Amsoy+4=252) "
              "& PT-II Table 58 p85 (Amsoy=252). Corpus PT Amsoy=252 CORRECT; UT Amsoy=274 wrong (-22). "
              "Gate said BOTH_OUTLIER (Columbia genuine-early made correct PT look like the outlier). Fix UT -22."),
    dict(id="1968_II_Columbia_UT", year="1968", mg="II", test="UT", city="Columbia", state="MO",
         op="shift", add=-50.0, exclude=[],
         guard_strain="Amsoy", guard_true=246, guard_tol=8,
         note="PDF UT-II Table 49 p83 (Harosoy63 matured 8-26=DOY239, footer 5-13+105=239; Amsoy+7=246) "
              "& PT-II Table 59 p101 (Harosoy63 8-31=244, Amsoy+2=246). Corpus PT Amsoy=246 CORRECT; "
              "UT Amsoy=296 wrong (-50). Gate said BOTH_OUTLIER; only UT is off (Columbia matured very "
              "early, short 105-day season). Fix UT -50."),
    dict(id="1986_II_Arlington_PT", year="1986", mg="II", test="PT", city="Arlington", state="WI",
         op="shift", add=36.0, exclude=[], max_v=285,
         guard_strain="Zane", guard_true=298, guard_tol=8,
         note="PDF UT-II p57 & PT-IIB p92: Arlington MG-II genuinely matures LATE OCT (Elgin anchor "
              "10-21/10-22 = DOY 294/295, footer 5-21+153/154 verified; UT correct). Corpus PT is a "
              "corpus-assembly defect: the dated Elgin row survived (293/295) but the offset rows "
              "(Zane, Hoyt, ~70 strains) were added to a wrong ~mid-Sept base (~259) -> ~36 d too "
              "early. Shift only the low group (v<=285) +36 (Zane 262->298, Hoyt 261->297); leave Elgin."),
    dict(id="1967_II_Hoytville_UT", year="1967", mg="II", test="UT", city="Hoytville", state="OH",
         op="shift", add=27.0, exclude=[],
         guard_strain="Amsoy", guard_true=285, guard_tol=8,
         note="PDF UT-II Table 48 p72 (self-verified render): Harosoy63 matured 10-12 = DOY 285 "
              "(1967 non-leap), Amsoy offset 0 = 285 at Hoytville. Corpus UT Amsoy=258 (wrong, -27); "
              "PT Amsoy=290 (~correct). Gate mis-attributed to PT (Hoytville MG-II matures late, so "
              "the correct-late PT looked like the cross-location outlier). Fix UT +27."),
    dict(id="1968_II_Spickard_UT", year="1968", mg="II", test="UT", city="Spickard", state="MO",
         op="shift", add=24.0, exclude=[],
         guard_strain="Amsoy", guard_true=265, guard_tol=8,
         note="PDF UT-II Table 49 p66 (self-verified render): Harosoy63 matured 9-19, Amsoy +2 = "
              "9-21 = DOY 265 (1968 LEAP; corpus PT Amsoy=267=9-23 confirms leap DOY). Corpus UT "
              "Amsoy=241 (=Aug 28, wrong, -24); PT ~correct. Fix UT +24."),
    dict(id="2011_IV_Portageville_PT", year="2011", mg="IV", test="PT", city="Portageville-Clay", state="MO",
         op="shift", add=30.0, exclude=[],
         guard_strain="", guard_true=280, guard_tol=10,
         note="PDF UT-IV p223 (LD00-3309 anchor 10/3=DOY276; IA4005=281) vs PT-IV p237 (anchor 9/3="
              "DOY246; IA4005=250) — PT-IV Portageville season 94 days is an outlier (other PT-IV "
              "115-142; UT 124). Corpus UT correct; PT too early. Shift PT-IV Portageville +30."),
    dict(id="2012_III_Hoytville_PT", year="2012", mg="III", test="PT", city="Hoytville", state="OH",
         op="shift", add=-30.0, exclude=[],
         guard_strain="", guard_true=253, guard_tol=10,
         note="PDF UT-III p183 (IA3023 anchor 9/12=DOY256) vs PT-IIIA p198 (IA3023 anchor 10/12="
              "DOY286) — PT-IIIA Hoytville season 150 days is an outlier (other PT 122-131; UT 120). "
              "Corpus UT correct; PT too late. Shift PT-III Hoytville -30."),
    dict(id="1996_I_Brookings_PT", year="1996", mg="I", test="PT", city="Brookings", state="SD",
         op="shift", add=-30.0, exclude=[],
         guard_strain="", guard_true=270, guard_tol=10,
         note="PDF UT-I p64 (Parker anchor 9/25=DOY269) vs PT-I p81 (Parker anchor printed 10/24 = "
              "DOY298, an impossible 161-day season; true 9/24=DOY268 -> month typo). Corpus UT "
              "correct (~269); PT inflated ~+30. Shift PT-I Brookings by -30 (298->268 anchor)."),
    dict(id="2004_I_Lamberton_PT", year="2004", mg="I", test="PT", city="Lamberton", state="MN",
         op="shift", add=21.0, exclude=[],
         guard_strain="", guard_true=271, guard_tol=8,
         note="PDF UT-I p91 (Parker anchor 9/26=DOY270; DtM 139 = northern-cluster normal) vs PT-I p104 "
              "(Parker 9/5=DOY249, DtM 118 breaks the Lamberton<->Waseca coupling). Corpus UT correct; "
              "PT ~21 early. Tight PT column (247-254) -> whole-column shift +21."),
    dict(id="2011_I_WestLafayette_UT", year="2011", mg="I", test="UT", city="West Lafayette", state="IN",
         op="shift", add=-32.0, exclude=[], min_v=265,
         guard_strain="MN1410", guard_true=247, guard_tol=8,
         note="PDF UT-I p87 (MN1410 anchor 10/6=DOY279, DtM 142 = lone high outlier; MN1410 matured "
              "9/12-9/19 at every other UT-I loc) vs PT-I p99 (MN1410 9/4=247). BIMODAL corpus UT: 10 "
              "strains correctly early (239-256) + 7 corrupt-late (267-289, incl. checks MN1410/IA1022/"
              "Sheyenne) from the mis-anchored UT-I column. Shift ONLY the late subset (v>=265) by -32 "
              "(checks confirm: MN1410 279->247, IA1022 283->251, Sheyenne 267->235)."),
    dict(id="2004_0_Watertown_PT", year="2004", mg="0", test="PT", city="Watertown", state="SD",
         op="shift", add=-45.0, exclude=[],
         guard_strain="", guard_true=261, guard_tol=10,
         note="PDF UT-0RR p241 (RG405RR anchor 9/13=DOY257; AG0801=254) vs PT-0RR p252 (RG405RR "
              "anchor printed 10/28=DOY302, impossible 176-day season). Corpus UT correct (~260); PT "
              "inflated ~+45. Shift PT-0 Watertown by -45 (align anchor to UT's 9/13)."),
    # --- HELD (PDF-verified but NOT auto-fixed; documented for a future targeted pass) ---
    # 1954 I St.Paul: PT documented correct (Table 20: Mandarin matured 9-25 = DOY 268, matches
    #   corpus PT). UT St.Paul is ABSENT from the UT-I maturity summary (Table 11, eastern locs
    #   only) -> corpus UT value 248 has no summary source; unverifiable, left unchanged.
    # 1962 II Urbana: NOT FIXABLE from this report -- "Urbana" does not appear anywhere in the 1962
    #   PDF and the MG-II table (Table 45) locations are ONT/OH/MI only. The corpus 1962 MG-II
    #   "Urbana" is undocumented here (likely a mis-classification) -> separate integrity issue.
    # 2013 I West Lafayette: UT values (IA1022=274, A10-456040=276) are DOCUMENTED CORRECT (UT-I
    #   Table p85, reference MN1410 9/25=DOY268, normal 126-day season). The early side is the
    #   PT-IA Lafayette column (105-day season, anomalous) but its whole-column state is unclear
    #   -> held pending a closer look, not auto-shifted.
]


# Data-driven batches. Same schema as a CONFIG dict, one row per cell (or per table when
# city="*"). Kept in separate files so the correction FAMILIES stay separable in the ledger
# and independently revertible:
#   tier23_maturity_fixes.csv  shared-check PT/UT cells + single-test blind-spot cells
#   anchor_leak_fixes.csv      "Mean of N Tests" column-leak repairs + leap-year table shifts
#
# Optional columns (blank = default):
#   tag         provenance marker written into Source. Defaults to TAG. Leap-year entries use
#               TAG_LEAP so a leap shift and an anchor shift on the same cell cannot mask each
#               other's guard, and either family can be reverted on its own.
#   guard_mode  "tag" -> idempotency comes from the provenance marker rather than a value
#               check: rows already carrying this entry's tag are skipped. Required for
#               whole-table ops (city="*"), where no single guard_true could describe every
#               location in the table.
_BATCHES = [Path(__file__).resolve().parent / n
            for n in ("tier23_maturity_fixes.csv", "anchor_leak_fixes.csv",
                      "leap_1972_fixes.csv", "anchor_1972_other_fixes.csv",
                      "gate2_fixes.csv", "residual_anchor_fixes.csv")]
for _bf in _BATCHES:
    if not _bf.exists():
        continue
    # keep_default_na=False so the literal op string "null" is NOT parsed as NaN
    _bt = pd.read_csv(_bf, dtype=str, keep_default_na=False)
    for _r in _bt.to_dict("records"):
        _gm = (_r.get("guard_mode") or "").strip()
        _gt = (_r.get("guard_true") or "").strip()
        _e = dict(id=_r["id"], year=_r["year"], mg=_r["mg"], test=_r["test"],
                  city=_r["city"], state=(_r.get("state") or None), op=_r["op"],
                  note=_r.get("note", ""),
                  exclude=[x for x in str(_r.get("exclude", "")).split("|") if x],
                  # only_strain: restrict the op to just these strains (opposite of exclude).
                  # Used when one column needs two DIFFERENT shifts on disjoint strains -- e.g.
                  # a 1972 dual defect where the check variety needs +1 (leap slip) while the
                  # body strains need a different re-anchor shift.
                  only_strain=[x for x in str(_r.get("only_strain", "")).split("|") if x],
                  guard_strain=_r.get("guard_strain", ""),
                  guard_mode=(_gm or "value"),
                  guard_true=(float(_gt) if _gt else None),
                  guard_tol=float(_r.get("guard_tol") or 0),
                  tag=((_r.get("tag") or "").strip() or TAG),
                  batch=_bf.name)
        if _r["op"] == "shift":
            _e["add"] = float(_r["add"])
        if (_r.get("min_v") or "") != "":
            _e["min_v"] = float(_r["min_v"])
        if (_r.get("max_v") or "") != "":
            _e["max_v"] = float(_r["max_v"])
        CONFIG.append(_e)

# A cell must not be claimed by two different correction families on the SAME rows: an
# anchor-leak shift and a leap shift compounding would double-count. Anchor targets are
# expressed as leap-correct absolute DOY precisely so the two never overlap -- assert it.
# Exemption: a strain-scoped entry (exclude or only_strain) is deliberately partial -- e.g. the
# 1972 dual-defect splits a column into check (only_strain, +1 leap) and body (exclude check,
# re-anchor). Those target DISJOINT strains by construction, so they are not a conflict; only
# WHOLE-cell entries are checked against each other here.
def _whole_cell(e):
    return not e.get("exclude") and not e.get("only_strain") and e["city"] != "*"


_seen: dict[tuple, str] = {}
for _e in CONFIG:
    if not _whole_cell(_e):
        continue
    _k = (_e["year"], _e["mg"], _e["test"], str(_e["city"]).strip().lower())
    if _k in _seen and _seen[_k] != _e.get("tag", TAG):
        raise SystemExit(
            f"CONFLICT: {_k} is targeted by two correction families "
            f"({_seen[_k]} and {_e.get('tag', TAG)}) -- resolve before applying.")
    _seen[_k] = _e.get("tag", TAG)


def group_mask(c, e):
    m = ((c.Year == e["year"]) & (c.TestMG == e["mg"]) & (c.TestType == e["test"])
         & (c.Phenotype == "Maturity"))
    # city="*" targets the WHOLE table -- used by the leap-year conversion fixes, which are
    # uniform across every location in a (year x test x MG) table.
    if e["city"] != "*":
        m &= (c.City.str.strip() == e["city"])
        if e.get("state"):
            m &= (c.State.fillna("").str.strip() == e["state"])
    return m


def guard_ok(c, e):
    """True if the anomaly signature is still present (fix should run)."""
    m = group_mask(c, e)
    sub = c[m].copy()
    sub["v"] = pd.to_numeric(sub.Value_num, errors="coerce")
    if e.get("guard_mode") == "tag":
        # provenance-based idempotency: run while any targeted row is still untagged.
        # Required for whole-table ops, where one guard_true cannot describe every column.
        # Scope the check to the same strain filter the op uses, so an only_strain/exclude
        # entry does not keep "running" because a SIBLING entry's rows are untagged.
        excl = {nk(s) for s in e.get("exclude", [])}
        only = {nk(s) for s in e.get("only_strain", [])}
        skm = sub.Strain.map(nk)
        scope = sub[~skm.isin(excl) & (skm.isin(only) if only else True)]
        tg = e.get("tag", TAG)
        return bool((~scope.Source.astype(str).str.contains(re.escape(tg.strip("|")),
                                                            na=False)).any())
    if e["op"] == "null":
        if e.get("guard_strain"):
            # deviation-based: act while the guard check is still present AND far from its true
            # value (handles both too-early and too-late leaks). After NULL it is NaN -> stop.
            gk = nk(e["guard_strain"])
            g = sub[sub.Strain.map(nk).str.contains(gk, na=False)]
            if g.empty or g["v"].isna().all():
                return False
            return abs(float(g["v"].median()) - e["guard_true"]) > e["guard_tol"]
        # floor mode: act while any impossible-early value remains (guard_true = plausibility floor)
        return bool((sub["v"] < e["guard_true"]).any())
    if not e.get("guard_strain"):
        # group-median guard (used for modern cells with messy check names)
        if sub["v"].isna().all():
            return False
        return abs(float(sub["v"].median()) - e["guard_true"]) > e["guard_tol"]
    gk = nk(e["guard_strain"])
    g = sub[sub.Strain.map(nk).str.contains(gk, na=False)]
    if g.empty or g["v"].isna().all():
        return False
    return abs(float(g["v"].median()) - e["guard_true"]) > e["guard_tol"]


def apply_entry(c, e):
    m = group_mask(c, e)
    idx = list(c.index[m])
    if not guard_ok(c, e):
        return 0, "signature absent (already fixed / not matching) -> skip"
    n = 0
    excl = {nk(s) for s in e.get("exclude", [])}
    only = {nk(s) for s in e.get("only_strain", [])}   # if set, restrict to these strains
    lo_v, hi_v = e.get("min_v"), e.get("max_v")   # optional value window (partial-column fixes)
    tg = e.get("tag", TAG)
    tagkey = tg.strip("|")
    for i in idx:
        sk = nk(c.at[i, "Strain"])
        if sk in excl:
            continue
        if only and sk not in only:
            continue
        # under tag-mode a row is corrected at most once, even across repeated runs
        if e.get("guard_mode") == "tag" and tagkey in str(c.at[i, "Source"]):
            continue
        v = pd.to_numeric(c.at[i, "Value_num"], errors="coerce")
        if pd.isna(v):
            continue
        if lo_v is not None and v < lo_v:
            continue
        if hi_v is not None and v > hi_v:
            continue
        if e["op"] == "shift":
            c.at[i, "Value_num"] = f"{v + e['add']:g}"
        elif e["op"] == "null":
            c.at[i, "Value_num"] = ""
        c.at[i, "Source"] = str(c.at[i, "Source"]) + tg
        n += 1
    return n, "applied"


def _write_all(c):
    """Write combined + alias + era splits (shared by apply and revert)."""
    for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
        c.to_csv(SH / name, index=False)
    c = c.copy()
    c["_y"] = pd.to_numeric(c.Year, errors="coerce")
    for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                       (1985, 2004, "nust_1985-2004_combined.csv"),
                       (2005, 2025, "nust_2005-2025_combined.csv")]:
        c[(c._y >= lo) & (c._y <= hi)].drop(columns="_y").to_csv(SH / fn, index=False)


def build_ledger(c):
    """One row per cell this tool changed (identified by the |fix_mat_anchor tag): before -> after,
    so every correction is reviewable and each shift is exactly revertible (before = after - add)."""
    rows = []
    for e in CONFIG:
        sub = c[group_mask(c, e)]
        tg = e.get("tag", TAG)
        tagged = sub[sub.Source.astype(str).str.contains(re.escape(tg.strip("|")), na=False)]
        for i in tagged.index:
            v = pd.to_numeric(c.at[i, "Value_num"], errors="coerce")
            if e["op"] == "shift":
                after, before = (f"{v:g}" if pd.notna(v) else ""), f"{v - e['add']:g}" if pd.notna(v) else ""
            else:  # null: value already removed, before value is not recoverable from the combined
                after, before = "", "(removed)"
            rows.append(dict(id=e["id"], Year=c.at[i, "Year"], MG=c.at[i, "TestMG"], Test=c.at[i, "TestType"],
                             City=c.at[i, "City"], State=c.at[i, "State"], Strain=c.at[i, "Strain"],
                             before=before, after=after, op=e["op"],
                             add=(e.get("add", "") if e["op"] == "shift" else ""),
                             family=tg.strip("|"), batch=e.get("batch", "CONFIG"),
                             reason=e["note"]))
    return pd.DataFrame(rows)


def revert(c, target, apply):
    """Undo this tool's corrections. target='all' or a specific entry id. SHIFTS are exactly reversed
    (subtract add from tagged rows, strip the tag). NULLs cannot be auto-restored (value was removed) —
    they are reported; restore them by editing the corpus from source if ever needed."""
    n_rev = n_null = 0
    for e in CONFIG:
        # target may be an entry id OR a family name ("fix_leap_doy") to revert a whole family
        tg = e.get("tag", TAG)
        tagkey = tg.strip("|")
        if target != "all" and e["id"] != target and tagkey != target:
            continue
        idx = [i for i in c.index[group_mask(c, e)]
               if tagkey in str(c.at[i, "Source"])]
        if not idx:
            continue
        if e["op"] == "shift":
            for i in idx:
                v = pd.to_numeric(c.at[i, "Value_num"], errors="coerce")
                if pd.notna(v):
                    c.at[i, "Value_num"] = f"{v - e['add']:g}"
                c.at[i, "Source"] = str(c.at[i, "Source"]).replace(tg, "")
                n_rev += 1
            print(f"  reverted shift {e['id']}: {len(idx)} rows (+{-e['add']:g} back)")
        else:
            n_null += len(idx)
            print(f"  NOT reverted (null, value removed) {e['id']}: {len(idx)} rows — restore from source if needed")
    print(f"\nreverted {n_rev} shifted rows; {n_null} nulled rows left as-is.")
    if apply and n_rev:
        _write_all(c)
        print("APPLIED revert: combined + era splits written. Rebuild 11 + 12 + replot + gates.")
    elif not apply:
        print("(dry run; add --apply to write)")


def main():
    # --ledger : write the before/after review ledger and exit
    if "--ledger" in sys.argv:
        c = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
        led = build_ledger(c)
        out = REPO / "analysis/data/analysis_results/Corpus_QC/maturity_corrections_ledger.csv"
        led.to_csv(out, index=False)
        print(f"wrote {out.name}: {len(led)} changed rows "
              f"({(led.op=='shift').sum()} shift [revertible], {(led.op=='null').sum()} null)")
        return
    # --revert[=id] : undo corrections (all, or a single entry id)
    rev = [a for a in sys.argv if a.startswith("--revert")]
    if rev:
        target = rev[0].split("=", 1)[1] if "=" in rev[0] else "all"
        c = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
        revert(c, target, "--apply" in sys.argv)
        return
    apply = "--apply" in sys.argv
    c = pd.read_csv(SH / "nust_1941_2025_combined.csv", dtype=str, low_memory=False)
    total = 0
    for e in CONFIG:
        n, msg = apply_entry(c, e)
        total += n
        print(f"  {e['id']:30s} op={e['op']:5s} -> {n:3d} rows  ({msg})")
    print(f"\ntotal maturity rows corrected: {total}")
    if not CONFIG:
        print("  (CONFIG empty)")
    if apply and total:
        for name in ("nust_1941_2025_combined.csv", "nust_1965_2025_combined.csv"):
            c.to_csv(SH / name, index=False)
        c["_y"] = pd.to_numeric(c.Year, errors="coerce")
        for lo, hi, fn in [(1941, 1984, "nust_1941-1984_combined.csv"),
                           (1985, 2004, "nust_1985-2004_combined.csv"),
                           (2005, 2025, "nust_2005-2025_combined.csv")]:
            c[(c._y >= lo) & (c._y <= hi)].drop(columns="_y").to_csv(SH / fn, index=False)
        print("APPLIED: combined + alias + era splits written. Next: 11, 12, replot + gate.")
    elif apply:
        print("nothing to apply (all guards clean).")
    else:
        print("(dry run; pass --apply to write)")


if __name__ == "__main__":
    main()
