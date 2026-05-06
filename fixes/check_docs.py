import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

for f in ["README.md", "docs/NUST_Historical_Extraction_Workflow.md"]:
    txt = open(f, encoding="utf-8").read()
    checks = [
        ("metaTable1.csv in output table", "metaTable1.csv" in txt),
        ("QC step present", "qc_pdf_vs_csv" in txt),
        ("consistency_check present", "consistency_check" in txt),
        ("verify_phase3 present", "verify_phase3" in txt),
    ]
    print(f"{f}:")
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'MISSING'}] {label}")
    print()
