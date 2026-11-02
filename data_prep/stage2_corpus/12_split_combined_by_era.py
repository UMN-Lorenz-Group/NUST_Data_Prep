"""
12_split_combined_by_era.py
===========================
Split the master long combined file into three smaller year-range files
(additive — the master and its alias are left untouched as the canonical
analysis inputs):
    nust_1941-1984_combined.csv   (1941-1984)
    nust_1985-2004_combined.csv   (1985-2004)
    nust_2005-2025_combined.csv   (2005-2025)
all written to analysis/data/ with the master's exact header/column order.

Streams the 3.77M-row master once (low memory). Asserts the three row counts
sum to the master and every year lands in exactly one file.

NOTE: never open these in Excel — even a single era slice can exceed Excel's
1,048,576-row cap and a save there truncates the file.

Usage:
    PYTHONUTF8=1 uv run python data_prep/stage2_corpus/12_split_combined_by_era.py
"""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
DATA = REPO / "analysis/data/_shared"
MASTER = DATA / "nust_1941_2025_combined.csv"

# (start, end_inclusive, filename)
ERAS = [
    (1941, 1984, "nust_1941-1984_combined.csv"),
    (1985, 2004, "nust_1985-2004_combined.csv"),
    (2005, 2025, "nust_2005-2025_combined.csv"),
]


def era_index(year):
    for i, (lo, hi, _) in enumerate(ERAS):
        if lo <= year <= hi:
            return i
    return None


def main():
    if not MASTER.exists():
        sys.exit(f"Master not found: {MASTER}")

    with open(MASTER, newline="", encoding="utf-8", errors="replace") as fi:
        r = csv.reader(fi)
        header = next(r)
        try:
            yi = header.index("Year")
        except ValueError:
            sys.exit("No 'Year' column in master header")

        writers, files, counts = [], [], [0, 0, 0]
        by_year = Counter()
        unrouted = 0
        for _, _, fname in ERAS:
            fh = open(DATA / fname, "w", newline="", encoding="utf-8")
            w = csv.writer(fh)
            w.writerow(header)
            files.append(fh)
            writers.append(w)

        n = 0
        for row in r:
            n += 1
            try:
                y = int(float(row[yi]))
            except (ValueError, IndexError):
                unrouted += 1
                continue
            idx = era_index(y)
            if idx is None:
                unrouted += 1
                continue
            writers[idx].writerow(row)
            counts[idx] += 1
            by_year[y] += 1

        for fh in files:
            fh.close()

    print(f"Master rows (excl. header): {n:,}")
    total = 0
    for (lo, hi, fname), c in zip(ERAS, counts):
        yrs = sorted(y for y in by_year if lo <= y <= hi)
        span = f"{yrs[0]}-{yrs[-1]}" if yrs else "EMPTY"
        print(f"  {fname:30s} rows={c:>10,}  years={span}")
        total += c
    print(f"  {'sum of splits':30s} rows={total:>10,}  unrouted={unrouted}")

    # acceptance assertions
    assert unrouted == 0, f"{unrouted} rows had a year outside 1941-2025 or unparseable"
    assert total == n, f"split sum {total} != master {n}"
    # every year present in exactly one era
    overlap = [y for y in by_year if sum(1 for lo, hi, _ in ERAS if lo <= y <= hi) != 1]
    assert not overlap, f"years routed to !=1 era: {sorted(overlap)}"
    print("\nOK: splits sum to master, no unrouted rows, every year in exactly one file.")


if __name__ == "__main__":
    main()
