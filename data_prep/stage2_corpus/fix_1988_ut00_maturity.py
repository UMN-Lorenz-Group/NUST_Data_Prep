"""
fix_1988_ut00_maturity.py
=========================
Source-level fix for the 1988 UT-00 maturity offset leak. The 1988 UT-00 recovery
(ut00_1988_alltraits.csv, folded into the corpus by apply_1988_utpt_relabel.py as
Source=Recovered_UTPT_1988_UT00) stored Maturity as raw relative-day OFFSETS
(-22..23) instead of absolute DOY, so the values leak below the [175,340] DOY-range
gate. (Note: fix_1988_1990_maturity_doy.py targets recovery_confirmed.csv / the F4U
1990 file — neither now carries these UT-00 rows, so this companion fixes the actual
source of record for the 1988 UT-00 block.)

Method = the proven offset-vector match from fix_1988_1990_maturity_doy.py: parse the
1988 Red PDF UNIFORM TEST 00 MATURITY columns (per-location reference-check DATE anchor
+ per-strain day offsets), match each source location group to a PDF column by its full
offset vector (location-agnostic; robust to city/state canonicalization), then
DOY = anchorDOY + offset. Band-checked (210-322); a group that fails to match or lands
out of band is NULLed ("a gap beats wrong data"). Fix is at the source csv so it
survives every corpus rebuild via apply_1988_utpt_relabel -> finalize_corpus_recoveries.

Idempotent + guarded: only rows whose Maturity is still offset-like (|v| < 100) are
touched; re-running after the fix is a no-op.

Usage: PYTHONUTF8=1 uv run --with pdfplumber python data_prep/stage2_corpus/fix_1988_ut00_maturity.py [--apply]
Then re-run finalize_corpus_recoveries.py (re-folds + rebuilds 11/12).
"""
import importlib.util
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
SRC = HERE / "ut00_1988_alltraits.csv"

_spec = importlib.util.spec_from_file_location("f88", HERE / "fix_1988_1990_maturity_doy.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def main():
    apply = "--apply" in sys.argv
    df = pd.read_csv(SRC, dtype=str, low_memory=False)
    ismat = df.Phenotype == "Maturity"
    v = pd.to_numeric(df.Value_num, errors="coerce")
    # guard: anything still offset-like?
    if not (ismat & v.notna() & (v.abs() < 100)).any():
        print("signature absent (already DOY / no offsets) -> no-op.")
        return

    idx, _ = M.build_pdf_index(1988)
    cols00 = idx.get("00", [])
    print(f"PDF 1988 UT-00 maturity columns: {len(cols00)} "
          f"(anchorDOYs {[c['anchor_doy'] for c in cols00]})")

    conv = null = 0
    sub = df[ismat].copy()
    sub["v"] = pd.to_numeric(sub.Value_num, errors="coerce")
    for (t, c, s), g in sub.groupby([sub.Test, sub.City, sub.State]):
        off = {M.nm(r.Strain): r.v for r in g.itertuples()
               if pd.notna(r.v) and abs(r.v) <= M.OFFSET_MAX}
        best, n, cmp = M.match_group(off, cols00)
        ok = False
        adoy = None
        if best is not None and cmp and n / cmp >= M.MIN_FRAC:
            adoy = best["anchor_doy"]
            vals = [adoy + o for o in off.values()]
            ok = all(M.BAND[0] <= x <= M.BAND[1] for x in vals)
        rows = g.index
        if ok:
            for i in rows:
                ov = pd.to_numeric(df.at[i, "Value_num"], errors="coerce")
                if pd.notna(ov) and abs(ov) < 100:
                    df.at[i, "Value_num"] = f"{int(round(adoy + ov))}"
                    conv += 1
            print(f"  OK  {t} {str(c)[:12]:12} {s:4} anchorDOY={adoy} match={n}/{cmp} p{best['page']}")
        else:
            for i in rows:
                ov = pd.to_numeric(df.at[i, "Value_num"], errors="coerce")
                if pd.notna(ov) and abs(ov) < 100:
                    df.at[i, "Value_num"] = ""
                    null += 1
            print(f"  NUL {t} {str(c)[:12]:12} {s:4} (no/weak match {n}/{cmp}) -> NULLed")

    print(f"\nconverted {conv} rows -> DOY, NULLed {null} rows")
    if apply:
        bak = SRC.with_suffix(".csv.orig_maturity_offset")
        if not bak.exists():
            shutil.copy2(SRC, bak)
        df.to_csv(SRC, index=False)
        print(f"APPLIED to {SRC.name} (backup {bak.name}). "
              f"Next: finalize_corpus_recoveries.py to re-fold + rebuild.")
    else:
        print("(dry run; pass --apply to write)")


if __name__ == "__main__":
    main()
