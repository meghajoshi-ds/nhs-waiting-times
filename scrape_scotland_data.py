"""
Scotland NHS Data Scraper
==========================
Downloads Scottish A&E and waiting times data from the
Scottish Health and Social Care Open Data portal (opendata.nhs.scot).

Unlike NHS England, Scotland publishes direct CSV download links —
no scraping needed, just download.

Folder structure created:
    data/raw/
    └── scotland/
        ├── ae_monthly/     <- Monthly A&E activity by health board
        └── waiting_times/  <- Inpatient/outpatient waiting times

Usage:
    python scrape_scotland_data.py
    python scrape_scotland_data.py --dry-run
    python scrape_scotland_data.py --ae
    python scrape_scotland_data.py --waiting
"""

import time
import argparse
import requests
from pathlib import Path

# ── Folders ───────────────────────────────────────────────────────────────────
AE_DIR      = Path("data/raw/scotland/ae_monthly")
WAITING_DIR = Path("data/raw/scotland/waiting_times")

for d in [AE_DIR, WAITING_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Direct CSV URLs from opendata.nhs.scot ────────────────────────────────────
# Scotland open data portal provides stable direct CSV links
# These are the full historical datasets — one file covers all years

SOURCES = {
    "ae_monthly": [
        {
            # Monthly A&E activity and waiting times by health board and hospital
            # Covers 2007 to present — attendance counts, 4hr performance
            "url": "https://www.opendata.nhs.scot/datastore/dump/1a1b8483-6f2e-4e3e-8f25-4d7a0d85d8e5?bom=True&format=csv",
            "filename": "scotland_ae_monthly_activity.csv",
        },
        {
            # NHS Boards reference data — maps board codes to names
            "url": "https://www.opendata.nhs.scot/datastore/dump/dde8af6f-d3a3-4dbc-87b8-b89e40e38194?bom=True&format=csv",
            "filename": "scotland_nhs_boards.csv",
        },
    ],
    "waiting_times": [
        {
            # Inpatient and day case waiting times by NHS board
            "url": "https://www.opendata.nhs.scot/datastore/dump/91f35f3c-cc91-4d32-9b07-9b5cfd8c8e68?bom=True&format=csv",
            "filename": "scotland_inpatient_waiting_times.csv",
        },
        {
            # Outpatient waiting times by NHS board and specialty
            "url": "https://www.opendata.nhs.scot/datastore/dump/97f84e99-7b0d-4259-8f0d-5330b41ffc20?bom=True&format=csv",
            "filename": "scotland_outpatient_waiting_times.csv",
        },
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; scotland-nhs-scraper/1.0; research project)"
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def download_file(url, filename, dest_dir, dry_run=False):
    dest_path = dest_dir / filename

    if dest_path.exists():
        print(f"    SKIP (exists): {filename}")
        return False

    if dry_run:
        print(f"    DRY RUN — would download: {filename}")
        return False

    try:
        print(f"    Downloading: {filename} ... ", end="", flush=True)
        resp = requests.get(url, headers=HEADERS, timeout=120,
                            stream=True, allow_redirects=True)
        resp.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = dest_path.stat().st_size // 1024
        if size_kb < 1:
            dest_path.unlink()
            print(f"SKIP (empty file)")
            return False

        print(f"done ({size_kb} KB)")
        return True

    except requests.RequestException as e:
        print(f"FAILED — {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Download Scottish NHS open data CSVs"
    )
    parser.add_argument("--ae",      action="store_true",
                        help="Download A&E monthly data only")
    parser.add_argument("--waiting", action="store_true",
                        help="Download waiting times data only")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be downloaded")
    args = parser.parse_args()

    run_all = not (args.ae or args.waiting)

    grand_downloaded = 0
    grand_skipped = 0

    if run_all or args.ae:
        print("\n=== SCOTLAND A&E MONTHLY DATA ===")
        for item in SOURCES["ae_monthly"]:
            result = download_file(item["url"], item["filename"],
                                   AE_DIR, args.dry_run)
            if result:
                grand_downloaded += 1
            else:
                grand_skipped += 1
            time.sleep(1)

    if run_all or args.waiting:
        print("\n=== SCOTLAND WAITING TIMES DATA ===")
        for item in SOURCES["waiting_times"]:
            result = download_file(item["url"], item["filename"],
                                   WAITING_DIR, args.dry_run)
            if result:
                grand_downloaded += 1
            else:
                grand_skipped += 1
            time.sleep(1)

    print(f"\nTOTAL: {grand_downloaded} downloaded, {grand_skipped} skipped")
    print(f"Files saved to: data/raw/scotland/")
    print(f"\nNext step: run  python src/ingest_scotland.py  to load into SQLite")


if __name__ == "__main__":
    main()
