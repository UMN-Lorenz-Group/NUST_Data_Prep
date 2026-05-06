"""Show per-test completion status vs full combo list."""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent

prog_path = ROOT / "output_1980/qc/qc_1980_values_progress.json"
csv_path  = ROOT / "output_1980/validated/combined_1980_phenotypesTable_approved.csv"

try:
    import pandas as pd
except ImportError:
    print("pandas not available"); sys.exit(1)

prog = json.loads(prog_path.read_text(encoding="utf-8"))
done_combos = {(r["test"], r["city"], r["state"]) for r in prog.get("completed", [])}

df = pd.read_csv(csv_path)
df = df[df["City"].notna() & (df["City"] != "") & (df["City"] != "Mean")]
all_combos = df[["Test", "City", "State"]].drop_duplicates().sort_values(["Test", "City"])

status = defaultdict(lambda: {"done": 0, "remaining": 0})
for _, row in all_combos.iterrows():
    t = row["Test"]
    k = (t, row["City"], row["State"])
    if k in done_combos:
        status[t]["done"] += 1
    else:
        status[t]["remaining"] += 1

print(f"Total combos:  {len(all_combos)}")
print(f"Completed:     {len(done_combos)}")
print(f"Remaining:     {len(all_combos) - len(done_combos)}")
print()
for t in sorted(status):
    d = status[t]["done"]
    r = status[t]["remaining"]
    tag = "DONE   " if r == 0 else ("PARTIAL" if d > 0 else "TODO   ")
    print(f"  [{tag}] {t}: {d} done, {r} remaining")
