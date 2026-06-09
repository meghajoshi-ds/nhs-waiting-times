"""
SQLite schema + connection helpers for the NHS waiting times project.

The database lives at data/nhs_waiting.db and is built by ingest.py.
Three tables:

    ae_monthly   trust-level A&E activity & 4-hour performance, one row per
                 (period, org_code)
    ae_national  national A&E time series (attendances + 4-hour performance),
                 one row per period  -- taken from the published time series file
    rtt_monthly  RTT incomplete-pathway summary, one row per
                 (period, provider_code, treatment_function)
"""

from pathlib import Path
import sqlite3

# Project root = parent of this file's parent (src/ -> project root)
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "nhs_waiting.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ae_monthly (
    period            TEXT NOT NULL,          -- ISO date, first of month e.g. 2025-03-01
    org_code          TEXT NOT NULL,
    parent_org        TEXT,                   -- NHS region, e.g. 'NHS ENGLAND LONDON'
    org_name          TEXT,
    region            TEXT,                   -- cleaned region label
    att_type1         INTEGER DEFAULT 0,
    att_type2         INTEGER DEFAULT 0,
    att_other         INTEGER DEFAULT 0,
    att_total         INTEGER DEFAULT 0,
    over4hr_type1     INTEGER DEFAULT 0,
    over4hr_type2     INTEGER DEFAULT 0,
    over4hr_other     INTEGER DEFAULT 0,
    over4hr_total     INTEGER DEFAULT 0,
    within4hr_total   INTEGER DEFAULT 0,
    pct_within_4hrs   REAL,                   -- all types
    pct_within_4hrs_t1 REAL,                  -- type 1 only (the headline metric)
    wait_4_12hr_dta   INTEGER DEFAULT 0,
    wait_12hr_dta     INTEGER DEFAULT 0,
    emergency_admissions INTEGER DEFAULT 0,
    PRIMARY KEY (period, org_code)
);

CREATE TABLE IF NOT EXISTS ae_national (
    period            TEXT PRIMARY KEY,       -- ISO date, first of month
    att_type1         REAL,
    att_type2         REAL,
    att_other         REAL,
    att_total         REAL,
    pct_within_4hrs   REAL                    -- all types, national
);

CREATE TABLE IF NOT EXISTS rtt_monthly (
    period              TEXT NOT NULL,        -- ISO date, first of month
    region_code         TEXT,
    provider_code       TEXT NOT NULL,
    provider_name       TEXT,
    tfc_code            TEXT,
    treatment_function  TEXT NOT NULL,
    total_waiting       INTEGER DEFAULT 0,
    within_18wk         INTEGER DEFAULT 0,
    pct_within_18wk     REAL,
    median_wait_wks     REAL,
    pct92_wait_wks      REAL,
    over_52wk           INTEGER DEFAULT 0,
    over_65wk           INTEGER DEFAULT 0,
    over_78wk           INTEGER DEFAULT 0,
    PRIMARY KEY (period, provider_code, treatment_function)
);

CREATE TABLE IF NOT EXISTS scotland_ae_monthly (
    period            TEXT NOT NULL,          -- ISO date, first of month
    hb_code           TEXT NOT NULL,          -- health board code, e.g. S08000024
    hb_name           TEXT,                   -- e.g. 'Lothian'
    att_total         INTEGER DEFAULT 0,
    within4hr_total   INTEGER DEFAULT 0,
    over4hr_total     INTEGER DEFAULT 0,
    over8hr_total     INTEGER DEFAULT 0,
    over12hr_total    INTEGER DEFAULT 0,
    att_type1         INTEGER DEFAULT 0,
    within4hr_type1   INTEGER DEFAULT 0,
    pct_within_4hrs   REAL,                   -- all department types
    pct_within_4hrs_t1 REAL,                  -- Type 1 (major ED) only
    PRIMARY KEY (period, hb_code)
);

CREATE INDEX IF NOT EXISTS idx_scot_period ON scotland_ae_monthly(period);
CREATE INDEX IF NOT EXISTS idx_ae_period   ON ae_monthly(period);
CREATE INDEX IF NOT EXISTS idx_ae_org      ON ae_monthly(org_name);
CREATE INDEX IF NOT EXISTS idx_rtt_period  ON rtt_monthly(period);
CREATE INDEX IF NOT EXISTS idx_rtt_tfc     ON rtt_monthly(treatment_function);
"""


def connect():
    """Open a connection to the project database (creates the file if needed)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_schema(conn):
    """Create all tables and indexes if they do not already exist."""
    conn.executescript(SCHEMA)
    conn.commit()


def reset(conn):
    """Drop and recreate every table -- used for a clean rebuild."""
    for tbl in ("ae_monthly", "ae_national", "rtt_monthly", "scotland_ae_monthly"):
        conn.execute(f"DROP TABLE IF EXISTS {tbl}")
    conn.commit()
    init_schema(conn)
