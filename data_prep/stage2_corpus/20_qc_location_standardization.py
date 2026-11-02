"""
20_qc_location_standardization.py
=================================
QC audit/gate for the location-name standardization (companion to scripts 13/14).
Applies the HIGH-confidence canonical map (reference/nust_location_canonical_map.csv,
action=map_auto) as a DRY-RUN over the current corpus + wide file and reports the
collapse it achieves — distinct City/Location before vs after, within/across-year
variant reduction, and the key payoff: the reduction in the asreml RGG environment
levels (factor(Location) and factor(Year:Location)) on the UT-eligible subset.

Run BEFORE the corpus rebuild to preview, and AFTER as a gate. Read-only.

Outputs (analysis/data/analysis_results/Corpus_QC/):
  location_standardization_audit.csv  — per raw (City,State): canon, action, n_rows
  location_standardization_summary.md
"""
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path("C:/Users/vramasub/Desktop/UMN_GIT/NUST_Data_Prep")
SHARED = REPO / "analysis" / "data" / "_shared"
LONG = SHARED / "nust_1941_2025_combined.csv"
WIDE = SHARED / "NUST_1941_2025_data_wide.csv"
MAP = REPO / "reference" / "nust_location_canonical_map.csv"
REF = REPO / "reference" / "nust_locations_ref.csv"
OUTDIR = REPO / "analysis" / "data" / "analysis_results" / "Corpus_QC"
MG_ORDER = ["00", "0", "I", "II", "III", "IV"]


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cm = pd.read_csv(MAP, keep_default_na=False)
    lut = {(str(r.raw_city), str(r.raw_state)): (r.canon_city, r.canon_state)
           for r in cm[cm["action"] == "map_auto"].itertuples(index=False)}

    def canon(city, state):
        c = str(city).strip() if pd.notna(city) else ""
        s = str(state).strip() if pd.notna(state) else ""
        return lut.get((c, s), (c, s))

    # ---- long corpus: City/Location collapse + within/across-year variants ------
    df = pd.read_csv(LONG, low_memory=False, usecols=["Year", "City", "State"])
    df = df[df["City"].notna()].copy()
    cc = df.apply(lambda r: canon(r["City"], r["State"]), axis=1, result_type="expand")
    df["cCity"], df["cState"] = cc[0], cc[1]
    bef_city, aft_city = df["City"].nunique(), df["cCity"].nunique()
    bef_cs = df.groupby(["City", "State"]).ngroups
    aft_cs = df.groupby(["cCity", "cState"]).ngroups

    # within-/across-year variant collapse: per canonical site, how many raw City spellings
    site_variants = df.groupby(["cCity", "cState"])["City"].nunique()
    multi = int((site_variants > 1).sum())
    # within-year: a (canon site, year) cell that had >1 raw spelling
    wy = df.groupby(["cCity", "cState", "Year"])["City"].nunique()
    wy_sites = df[df.set_index(["cCity", "cState", "Year"]).index.isin(
        wy[wy > 1].index)].groupby(["cCity", "cState"]).ngroups

    # ---- RGG environment-level reduction on the UT-eligible subset --------------
    env = ""
    if WIDE.exists():
        w = pd.read_csv(WIDE, low_memory=False,
                        usecols=["Year", "Experiment", "MG", "Location", "GermplasmId", "YieldBuA"])
        ut = w[w["Experiment"].astype(str).str.match("UT")
               & w["YieldBuA"].between(5, 100)
               & w["Location"].notna() & w["GermplasmId"].notna()
               & w["MG"].astype(str).str.strip().isin(MG_ORDER)].copy()
        # wide Location is "City_State"; split on the last underscore to recover (City, State)
        split = ut["Location"].astype(str).str.rsplit("_", n=1, expand=True)
        ut["_city"] = split[0]
        ut["_state"] = split[1] if split.shape[1] > 1 else ""
        cc2 = ut.apply(lambda r: canon(r["_city"], r["_state"]), axis=1, result_type="expand")
        ut["Loc_before"] = ut["Location"].astype(str)
        ut["Loc_after"] = cc2[0].astype(str) + "_" + cc2[1].astype(str)
        ut["MG"] = ut["MG"].astype(str).str.strip()
        rows = []
        for mg in MG_ORDER:
            s = ut[ut.MG == mg]
            if not len(s):
                continue
            rows.append((mg, s["Loc_before"].nunique(), s["Loc_after"].nunique(),
                         (s["Year"].astype(str) + s["Loc_before"]).nunique(),
                         (s["Year"].astype(str) + s["Loc_after"]).nunique()))
        env = pd.DataFrame(rows, columns=["MG", "Loc_before", "Loc_after",
                                          "YearLoc_before", "YearLoc_after"])

    # ---- coverage vs the geocoded reference -------------------------------------
    ref = pd.read_csv(REF, keep_default_na=False)
    ref_sites = set(zip(ref["City"], ref["State"]))
    canon_sites = set(zip(df["cCity"], df["cState"]))
    matched = len(canon_sites & ref_sites)

    # ---- write audit + summary --------------------------------------------------
    cm.sort_values(["action", "canon_state", "canon_city", "n_rows"],
                   ascending=[True, True, True, False]).to_csv(
        OUTDIR / "location_standardization_audit.csv", index=False)
    L = ["# Location standardization QC (dry-run preview)\n",
         f"Map: `{MAP.name}` (action=map_auto applied; review/drop NOT applied)\n",
         "## City / (City,State) collapse",
         f"- distinct City:  **{bef_city} -> {aft_city}**  ({bef_city-aft_city} merged)",
         f"- distinct (City,State): **{bef_cs} -> {aft_cs}**",
         f"- canonical sites with >1 raw spelling collapsed: **{multi}**",
         f"- sites that had within-year multiple spellings: **{wy_sites}**",
         f"- corpus rows remapped: **{int(cm[cm.action=='map_auto'].n_rows.sum()):,}**\n",
         "## action breakdown", "```",
         cm["action"].value_counts().to_string(), "```", "",
         "## RGG environment-level reduction (UT-eligible)", "```"]
    if isinstance(env, pd.DataFrame):
        L.append(env.to_string(index=False))
    L.append("```")
    L += ["", f"## Reference coverage: {matched} canonical sites match nust_locations_ref.csv",
          f"({len(canon_sites)} distinct canonical sites total; {len(ref_sites)} in ref)\n"]
    (OUTDIR / "location_standardization_summary.md").write_text("\n".join(L), encoding="utf-8")

    print(f"distinct City {bef_city} -> {aft_city}; (City,State) {bef_cs} -> {aft_cs}")
    print(f"collapsed sites (>1 spelling): {multi}; within-year-variant sites: {wy_sites}")
    if isinstance(env, pd.DataFrame):
        print("\nRGG env-level (UT-eligible):")
        print(env.to_string(index=False))
    print(f"\nref coverage: {matched} canonical sites in nust_locations_ref")
    print(f"\nOutputs ({OUTDIR.name}/): location_standardization_audit.csv + _summary.md")


if __name__ == "__main__":
    main()
