"""
NHS Waiting Times Data Scraper
================================
Downloads A&E monthly trust-level CSV files from NHS England.

Folder structure created:
    data/
    ├── raw/
    │   ├── timeseries/     <- File 1: national time series (1 file)
    │   ├── ae_monthly/     <- File 2: trust-level monthly CSVs (~60 files)
    │   └── rtt_monthly/    <- File 3: RTT Incomplete-Provider only (~36 files)
    └── nhs_waiting.db      <- created later by ingest.py

Usage:
    pip install requests beautifulsoup4
    python scrape_nhs_data.py

    To download only A&E:       python scrape_nhs_data.py --ae
    To download only RTT:       python scrape_nhs_data.py --rtt
    To download only timeseries: python scrape_nhs_data.py --timeseries
    To do a dry run:            python scrape_nhs_data.py --dry-run
"""

import time
import argparse
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin

# ── Folders ───────────────────────────────────────────────────────────────────
BASE_DIR       = Path("data/raw")
AE_DIR         = BASE_DIR / "ae_monthly"
RTT_DIR        = BASE_DIR / "rtt_monthly"
TIMESERIES_DIR = BASE_DIR / "timeseries"

for d in [AE_DIR, RTT_DIR, TIMESERIES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Source pages ──────────────────────────────────────────────────────────────
AE_YEAR_PAGES = [
    "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/ae-attendances-and-emergency-admissions-2024-25/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/ae-attendances-and-emergency-admissions-2023-24/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/ae-attendances-and-emergency-admissions-2022-23/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/ae-attendances-and-emergency-admissions-2021-22/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/ae-attendances-and-emergency-admissions-2020-21/",
]

RTT_YEAR_PAGES = [
    "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2024-25/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2023-24/",
    "https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2022-23/",
]

# National time series — single file
TIMESERIES_URL = "https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/03/Monthly-AE-Time-Series-February-2026-D36ah6.xls"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NHS-data-scraper/1.0; research project)"
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_file_links(page_url, extensions=(".csv",), prefix_filter=None):
    """
    Scrape a NHS England stats page and return file links.

    prefix_filter: if set, only return files whose filename starts with this string.
    e.g. prefix_filter="Incomplete-Provider" for RTT
    """
    print(f"\n  Scraping: {page_url}")
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR fetching page: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("/"):
            href = urljoin("https://www.england.nhs.uk", href)

        if not any(href.lower().endswith(ext) for ext in extensions):
            continue

        filename = href.split("/")[-1].split("?")[0]

        # Apply prefix filter if set (used for RTT)
        if prefix_filter and not filename.startswith(prefix_filter):
            continue

        links.append({"url": href, "label": a.get_text(strip=True)})

    print(f"  Found {len(links)} file(s)")
    return links


def download_file(url, dest_dir, dry_run=False):
    """
    Download a single file into dest_dir.
    Skips if file already exists (re-run safe).
    """
    filename = url.split("/")[-1].split("?")[0]
    dest_path = dest_dir / filename

    if dest_path.exists():
        print(f"    SKIP (exists): {filename}")
        return False

    if dry_run:
        print(f"    DRY RUN — would download: {filename}")
        return False

    try:
        print(f"    Downloading: {filename} ... ", end="", flush=True)
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_kb = dest_path.stat().st_size // 1024
        print(f"done ({size_kb} KB)")
        return True
    except requests.RequestException as e:
        print(f"FAILED — {e}")
        return False


def scrape_and_download(year_pages, dest_dir, extensions,
                        dry_run, prefix_filter=None):
    """Scrape each year page and download all matching files."""
    total_downloaded = 0
    total_skipped = 0

    for page_url in year_pages:
        links = get_file_links(page_url, extensions, prefix_filter)
        if not links:
            continue

        for link in links:
            result = download_file(link["url"], dest_dir, dry_run)
            if result:
                total_downloaded += 1
            else:
                total_skipped += 1
            time.sleep(0.5)

    print(f"\n  Summary: {total_downloaded} downloaded, {total_skipped} skipped")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Download NHS England A&E and RTT waiting times data"
    )
    parser.add_argument("--ae",         action="store_true",
                        help="Download A&E monthly CSV files only")
    parser.add_argument("--rtt",        action="store_true",
                        help="Download RTT Incomplete-Provider files only")
    parser.add_argument("--timeseries", action="store_true",
                        help="Download national A&E time series XLS only")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Print what would be downloaded without downloading")
    args = parser.parse_args()

    run_all = not (args.ae or args.rtt or args.timeseries)

    # ── File 1: National time series (1 file) ─────────────────────────────────
    if run_all or args.timeseries:
        print("\n=== FILE 1: National A&E Time Series (1 file) ===")
        download_file(TIMESERIES_URL, TIMESERIES_DIR, args.dry_run)

    # ── File 2: Trust-level A&E monthly CSVs (~60 files) ─────────────────────
    if run_all or args.ae:
        print("\n=== FILE 2: Trust-level A&E Monthly CSV (~60 files) ===")
        scrape_and_download(
            year_pages=AE_YEAR_PAGES,
            dest_dir=AE_DIR,
            extensions=(".csv",),
            dry_run=args.dry_run,
        )

    # ── File 3: RTT Incomplete-Provider only (~36 files) ─────────────────────
    # Each month has 8 RTT files. We only need "Incomplete-Provider" —
    # this shows patients still waiting by trust and specialty.
    # Filtering by prefix cuts 288 files down to ~36.
    if run_all or args.rtt:
        print("\n=== FILE 3: RTT Incomplete-Provider (~36 files) ===")
        scrape_and_download(
            year_pages=RTT_YEAR_PAGES,
            dest_dir=RTT_DIR,
            extensions=(".xls", ".xlsx"),
            dry_run=args.dry_run,
            prefix_filter="Incomplete-Provider",
        )

    print("\nDone. Check data/raw/ for downloaded files.")
    print("Next step: run  python -m src.ingest  to load into SQLite.")


if __name__ == "__main__":
    main()
