"""Null out the 3 flagged non-numeric values and re-run validator."""
import sys, subprocess
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from pathlib import Path

OUT = Path("output_1980")
ph = pd.read_csv(OUT / "combined_1980_phenotypesTable.csv")

patches = [
    # (id, phenotype, old_val, reason)
    (249,   "Lodging",   "Otbreek", "OCR artifact — known issue (Morden MAN Clay (0))"),
    (16702, "YieldRank", "I",       "Non-numeric 'I' — OCR or incomplete marker; nulled"),
    (18399, "Oil",       "I",       "Non-numeric 'I' — OCR or incomplete marker; nulled"),
]

for row_id, pheno, old_val, reason in patches:
    mask = (ph["id"] == row_id) & (ph["Phenotype"] == pheno)
    actual = ph.loc[mask, "Value"].values
    if len(actual) == 0:
        print(f"  [WARN] id={row_id} {pheno} not found")
        continue
    ph.loc[mask, "Value"] = None
    print(f"  Nulled id={row_id} {pheno} '{old_val}': {reason}")

ph.to_csv(OUT / "combined_1980_phenotypesTable.csv", index=False)
print(f"\nSaved. Re-running validator...")

result = subprocess.run(
    ["python", "validate_nust_hist.py",
     "--input", str(OUT / "combined_1980_phenotypesTable.csv"),
     "--out_dir", str(OUT / "validated/")],
    capture_output=True, text=True, encoding="utf-8"
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
