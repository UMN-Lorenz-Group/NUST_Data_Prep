from datetime import date
import calendar

yr = 1980
print(f"{yr} leap year: {calendar.isleap(yr)}")
print()

# Key maturity-range dates
for (m, d) in [(9,1),(9,5),(9,15),(9,19),(10,1),(10,15)]:
    doy = date(yr, m, d).timetuple().tm_yday
    print(f"  {m}/{d}/{yr} -> DOY {doy}")

print()
print("Perpetual calendar values (from PDF, non-leap):")
perp = {(9,1):244,(9,5):248,(9,15):258,(9,19):262,(10,1):274,(10,15):288}
for (m,d),v in perp.items():
    print(f"  {m}/{d} perpetual={v}  leap={v+1}  python={date(yr,m,d).timetuple().tm_yday}")

print()
print("Offset: leap - perpetual =", date(yr,9,1).timetuple().tm_yday - 244)

# What do the anchors look like — are they leap-correct?
print()
import csv
anchors = {}
with open("output_1980/maturity_anchors_1980.csv") as f:
    for row in csv.DictReader(f):
        anchors[(row["Test"], row["City"])] = int(row["AnchorDOY"])

# For UT-0 Rosemount — known Evans anchor was 9/19 in source PDF
# Leap-correct DOY for 9/19/1980 = 263
# Perpetual DOY for 9/19 = 262
sample_keys = [("UT-0","Rosemount"),("UT-II","Ames"),("UT-III","Rosemount"),("UT-IV","Lexington")]
print("Sample anchor DOY values (expect leap-correct = perpetual+1 for Mar+ dates):")
for k in sample_keys:
    if k in anchors:
        doy = anchors[k]
        print(f"  {k}: AnchorDOY={doy}  (perpetual equivalent would be {doy-1})")
