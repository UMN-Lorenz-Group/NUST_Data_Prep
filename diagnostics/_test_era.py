import sys, types, importlib.util

spec = importlib.util.spec_from_file_location("ex", "scripts/extract_nust_xlsx.py")
mod = types.ModuleType("ex")
sys.modules["ex"] = mod

# Prevent main() from running by patching sys.argv before exec
_argv = sys.argv[:]
sys.argv = ["extract_nust_xlsx.py", "--file", "dummy.xlsx", "--out_dir", "dummy/"]

try:
    spec.loader.exec_module(mod)
except SystemExit:
    pass
finally:
    sys.argv = _argv

for yr in ["1945", "1963", "1980", "1986"]:
    era = mod.get_era(int(yr))
    p = mod.build_system_prompt(yr)
    tag = "EARLY" if "EARLY-ERA" in p else ("TRANS" if "TRANSITIONAL-ERA" in p else "base")
    print(f"{yr}: era={era}  addendum={tag}  prompt_chars={len(p)}")

# test _normalize_tp
cases = [
    ("tp6+7",  "tp6"),
    ("tp9+10", "tp9"),
    ("tp 2",   "tp2"),
    ("tp??",   None),
    ("tp6 (Continued)", "tp6"),
    ("tp2 (NB Baie swak beeld)", "tp2"),
    ("tptp11a", "tp11a"),
    ("tp24",    None),
    ("tp",      None),
    ("tp6",     "tp6"),
]
print("\n_normalize_tp:")
all_ok = True
for raw, expected in cases:
    got = mod._normalize_tp(raw)
    status = "OK" if got == expected else f"FAIL (expected {expected!r})"
    print(f"  {raw!r:30s} -> {str(got):10s}  {status}")
    if got != expected:
        all_ok = False
print("All OK" if all_ok else "FAILURES above")
