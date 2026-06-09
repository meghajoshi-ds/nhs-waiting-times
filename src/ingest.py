"""
Load the raw NHS files in data/raw/ into the SQLite database.

    python -m src.ingest          # full rebuild from scratch
    python -m src.ingest --no-rtt # skip the large RTT files (faster)

Reads:
    data/raw/ae_monthly/*.csv                  -> ae_monthly
    data/raw/timeseries/*.xls                  -> ae_national
    data/raw/rtt_monthly/Incomplete-Provider*  -> rtt_monthly

The raw NHS column headers vary slightly between years (some months omit the
"Booked Appointments" columns, some have a UTF-8 BOM or trailing junk columns),
so we map by stripped column name rather than position.
"""

from pathlib import Path
import argparse
import re
import warnings

import pandas as pd

from . import database

warnings.simplefilter("ignore")  # silence openpyxl / xlrd style warnings

ROOT = database.ROOT
AE_DIR = ROOT / "data" / "raw" / "ae_monthly"
RTT_DIR = ROOT / "data" / "raw" / "rtt_monthly"
TS_DIR = ROOT / "data" / "raw" / "timeseries"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── shared helpers ────────────────────────────────────────────────────────────
def period_from_text(text):
    """Find 'March 2025' style month+year anywhere in a string -> '2025-03-01'."""
    m = re.search(r"(january|february|march|april|may|june|july|august|"
                  r"september|october|november|december)[\s\-]*?(\d{4})",
                  text.lower())
    if not m:
        return None
    return f"{int(m.group(2)):04d}-{MONTHS[m.group(1)]:02d}-01"


def period_from_abbr(text):
    """Find 'Mar25' style abbreviation in a filename -> '2025-03-01'."""
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[\-]?(\d{2})\b",
                  text.lower())
    if not m:
        return None
    yr = 2000 + int(m.group(2))
    return f"{yr:04d}-{MONTH_ABBR[m.group(1)]:02d}-01"


def clean_region(parent_org):
    """'NHS ENGLAND LONDON' -> 'London'. Falls back to title-cased input."""
    if not isinstance(parent_org, str):
        return None
    label = re.sub(r"^NHS ENGLAND\s*", "", parent_org.strip(), flags=re.I).strip()
    return label.title() if label else None


def to_int(series):
    """Coerce a column to integers, treating blanks / text as 0."""
    return (pd.to_numeric(series, errors="coerce")
            .fillna(0).round().astype("int64"))


# ── A&E trust-level monthly CSVs ──────────────────────────────────────────────
def load_ae_monthly(conn):
    files = sorted(AE_DIR.glob("*.csv"))
    print(f"\n[ae_monthly] {len(files)} CSV file(s)")
    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str, encoding="utf-8-sig")
        df.columns = [c.strip() for c in df.columns]
        df = df[[c for c in df.columns if c and not c.startswith("Unnamed")]]

        def col(name, default="0"):
            return df[name] if name in df.columns else pd.Series(default, index=df.index)

        period = df["Period"].dropna().iloc[0] if "Period" in df.columns else f.stem
        iso = period_from_text(str(period))
        if iso is None:
            print(f"   ! skipping (no period): {f.name}")
            continue

        out = pd.DataFrame({
            "period": iso,
            "org_code": df["Org Code"].str.strip(),
            "parent_org": col("Parent Org", None).str.strip()
                          if "Parent Org" in df.columns else None,
            "org_name": col("Org name", None).str.strip()
                        if "Org name" in df.columns else None,
            "att_type1": to_int(col("A&E attendances Type 1")),
            "att_type2": to_int(col("A&E attendances Type 2")),
            "att_other": to_int(col("A&E attendances Other A&E Department")),
            "over4hr_type1": to_int(col("Attendances over 4hrs Type 1")),
            "over4hr_type2": to_int(col("Attendances over 4hrs Type 2")),
            "over4hr_other": to_int(col("Attendances over 4hrs Other Department")),
            "wait_4_12hr_dta": to_int(
                col("Patients who have waited 4-12 hs from DTA to admission")),
            "wait_12hr_dta": to_int(
                col("Patients who have waited 12+ hrs from DTA to admission")),
            "emergency_admissions": (
                to_int(col("Emergency admissions via A&E - Type 1"))
                + to_int(col("Emergency admissions via A&E - Type 2"))
                + to_int(col("Emergency admissions via A&E - Other A&E department"))
                + to_int(col("Other emergency admissions"))),
        })
        out = out[out["org_code"].notna() & (out["org_code"].str.len() > 0)]
        frames.append(out)

    df = pd.concat(frames, ignore_index=True)

    # derived columns
    df["region"] = df["parent_org"].map(clean_region)
    df["att_total"] = df[["att_type1", "att_type2", "att_other"]].sum(axis=1)
    df["over4hr_total"] = df[["over4hr_type1", "over4hr_type2", "over4hr_other"]].sum(axis=1)
    df["within4hr_total"] = (df["att_total"] - df["over4hr_total"]).clip(lower=0)
    df["pct_within_4hrs"] = (100 * df["within4hr_total"] / df["att_total"]).where(
        df["att_total"] > 0)
    df["pct_within_4hrs_t1"] = (
        100 * (df["att_type1"] - df["over4hr_type1"]) / df["att_type1"]).where(
        df["att_type1"] > 0)

    cols = ["period", "org_code", "parent_org", "org_name", "region",
            "att_type1", "att_type2", "att_other", "att_total",
            "over4hr_type1", "over4hr_type2", "over4hr_other", "over4hr_total",
            "within4hr_total", "pct_within_4hrs", "pct_within_4hrs_t1",
            "wait_4_12hr_dta", "wait_12hr_dta", "emergency_admissions"]
    df = df[cols].drop_duplicates(subset=["period", "org_code"])
    df.to_sql("ae_monthly", conn, if_exists="append", index=False)
    print(f"   loaded {len(df):,} rows, "
          f"{df['period'].nunique()} months, {df['org_code'].nunique()} trusts")


# ── National A&E time series (published .xls) ─────────────────────────────────
def load_ae_national(conn):
    files = sorted(TS_DIR.glob("*.xls")) + sorted(TS_DIR.glob("*.xlsx"))
    if not files:
        print("\n[ae_national] no time series file found -- skipping")
        return
    f = files[0]
    print(f"\n[ae_national] {f.name}")

    def read_block(sheet, value_name):
        raw = pd.read_excel(f, sheet_name=sheet, header=None)
        # find the header row that contains 'Period' in column 1
        hdr = next(i for i in range(len(raw))
                   if str(raw.iloc[i, 1]).strip() == "Period")
        block = raw.iloc[hdr + 1:, [1, 2, 3, 4, 5]].copy()
        block.columns = ["period", "type1", "type2", "other", "total"]
        block["period"] = pd.to_datetime(block["period"], errors="coerce")
        block = block.dropna(subset=["period"])
        for c in ["type1", "type2", "other", "total"]:
            block[c] = pd.to_numeric(block[c], errors="coerce")
        block["period"] = block["period"].dt.strftime("%Y-%m-01")
        return block

    activity = read_block("Activity", "attendances")

    # Performance sheet: total attendances < 4 hours is column 5 (index in block)
    perf_raw = pd.read_excel(f, sheet_name="Performance", header=None)
    hdr = next(i for i in range(len(perf_raw))
               if str(perf_raw.iloc[i, 1]).strip() == "Period")
    perf = perf_raw.iloc[hdr + 1:, [1, 5]].copy()
    perf.columns = ["period", "within4hr_total"]
    perf["period"] = pd.to_datetime(perf["period"], errors="coerce")
    perf = perf.dropna(subset=["period"])
    perf["within4hr_total"] = pd.to_numeric(perf["within4hr_total"], errors="coerce")
    perf["period"] = perf["period"].dt.strftime("%Y-%m-01")

    df = activity.merge(perf, on="period", how="left")
    df["pct_within_4hrs"] = (100 * df["within4hr_total"] / df["total"]).where(
        df["total"] > 0)
    out = pd.DataFrame({
        "period": df["period"],
        "att_type1": df["type1"], "att_type2": df["type2"],
        "att_other": df["other"], "att_total": df["total"],
        "pct_within_4hrs": df["pct_within_4hrs"],
    }).drop_duplicates(subset=["period"])
    out.to_sql("ae_national", conn, if_exists="append", index=False)
    print(f"   loaded {len(out):,} months "
          f"({out['period'].min()} -> {out['period'].max()})")


# ── RTT incomplete-pathway summary ────────────────────────────────────────────
def load_rtt(conn):
    files = sorted(RTT_DIR.glob("Incomplete-Provider*.xls")) + \
            sorted(RTT_DIR.glob("Incomplete-Provider*.xlsx"))
    print(f"\n[rtt_monthly] {len(files)} file(s)")
    total = 0
    for f in files:
        iso = period_from_abbr(f.name)
        if iso is None:
            print(f"   ! skipping (no period): {f.name}")
            continue
        df = pd.read_excel(f, sheet_name="Provider", header=13)
        df.columns = [str(c).strip() for c in df.columns]

        def g(name):
            return df[name] if name in df.columns else pd.Series(index=df.index)

        out = pd.DataFrame({
            "period": iso,
            "region_code": g("Region Code"),
            "provider_code": g("Provider Code"),
            "provider_name": g("Provider Name"),
            "tfc_code": g("Treatment Function Code"),
            "treatment_function": g("Treatment Function"),
            "total_waiting": to_int(g("Total number of incomplete pathways")),
            "within_18wk": to_int(g("Total within 18 weeks")),
            "pct_within_18wk": pd.to_numeric(g("% within 18 weeks"), errors="coerce"),
            "median_wait_wks": pd.to_numeric(
                g("Average (median) waiting time (in weeks)"), errors="coerce"),
            "pct92_wait_wks": pd.to_numeric(
                g("92nd percentile waiting time (in weeks)"), errors="coerce"),
            "over_52wk": to_int(g("Total 52 plus weeks")),
            "over_65wk": to_int(g("Total 65 plus weeks")),
            "over_78wk": to_int(g("Total 78 plus weeks")),
        })
        # % columns come as fractions (0-1) in some files, percent in others
        for c in ["pct_within_18wk"]:
            if out[c].max(skipna=True) is not None and out[c].max(skipna=True) <= 1.5:
                out[c] = out[c] * 100

        out = out[out["provider_code"].notna() & out["treatment_function"].notna()]
        out = out.drop_duplicates(subset=["period", "provider_code", "treatment_function"])
        out.to_sql("rtt_monthly", conn, if_exists="append", index=False)
        total += len(out)
        print(f"   {f.name[:42]:42s} {iso}  {len(out):>5,} rows")
    print(f"   loaded {total:,} rows total")


# ── orchestrator ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Build nhs_waiting.db from raw files")
    ap.add_argument("--no-rtt", action="store_true",
                    help="skip the large RTT files for a quicker build")
    args = ap.parse_args()

    conn = database.connect()
    database.reset(conn)
    print(f"Building {database.DB_PATH.relative_to(ROOT)} ...")

    load_ae_monthly(conn)
    load_ae_national(conn)
    if not args.no_rtt:
        load_rtt(conn)

    conn.commit()
    conn.close()
    print("\nDone. Database ready at", database.DB_PATH)


if __name__ == "__main__":
    main()
