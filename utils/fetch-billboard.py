"""
Retrieve Billboard Hot 100 chart data, including year-end and weekly charts.
The data is fetched using https://github.com/guoguo12/billboard-charts.

The script writes an Excel workbook (.xlsx) with these columns:
  Year | Artist | Album | Song Title

Sources:
  - Weekly Hot 100 top-40: every chart week 1981-1988
  - Year-end Hot 100:      every year 1962-2025

Requirements:
  pip install billboard.py openpyxl
"""

import time
import billboard
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

OUTPUT_FILE = "billboard_songs.xlsx"
WEEKLY_TOP40_YEARS = range(1981, 1989)   # 1981-1988 inclusive
YEAR_END_YEARS     = range(1962, 2026)   # 1962-2025 inclusive
REQUEST_DELAY      = 0.5                 # seconds between requests (be polite)


def fetch_year_end(year):
    """Fetch the year-end Hot 100 for a given year. Returns list of ChartEntry."""
    try:
        chart = billboard.ChartData("hot-100", year=str(year))
        print(f"  [year-end] {year}: {len(chart.entries)} entries")
        return chart.entries
    except Exception as e:
        print(f"  [year-end] {year}: FAILED ({e})")
        return []


def fetch_weekly_top40(year):
    """
    Fetch every weekly Hot 100 chart for a given year and collect entries
    that peaked at position <= 40. Returns list of ChartEntry.
    """
    entries = []
    # Start at the first chart of the year and follow .previousDate links
    # Going forward: fetch Jan 1, then use chart.date + 7 days, etc.
    # billboard.py exposes chart.nextDate for the next chart date.
    from datetime import date, timedelta

    current = date(year, 1, 1)
    end     = date(year, 12, 31)
    seen_dates = set()

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        if date_str in seen_dates:
            current += timedelta(days=7)
            continue
        seen_dates.add(date_str)

        try:
            chart = billboard.ChartData("hot-100", date=date_str)
            top40 = [e for e in chart.entries if e.rank <= 40]
            entries.extend(top40)
            print(f"  [weekly]   {chart.date}: {len(top40)} top-40 entries")
            # Jump to the actual next chart date billboard knows about
            next_date_str = chart.nextDate
            if next_date_str:
                from datetime import datetime
                current = datetime.strptime(next_date_str, "%Y-%m-%d").date()
            else:
                current += timedelta(days=7)
        except Exception as e:
            print(f"  [weekly]   {date_str}: FAILED ({e})")
            current += timedelta(days=7)

        time.sleep(REQUEST_DELAY)

    return entries


def build_song_dict(all_entries):
    """
    Deduplicate by (artist, title), keeping the earliest year.
    Returns sorted list of (year, artist, title).
    """
    songs = {}  # (artist, title) -> year
    for year, entries in all_entries:
        for e in entries:
            key = (e.artist, e.title)
            if key not in songs or (year is not None and (songs[key] is None or year < songs[key])):
                songs[key] = year

    return sorted(songs.items(), key=lambda x: (x[1] or 9999, x[0][0], x[0][1]))


def write_xlsx(rows, path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Billboard Songs"

    headers = ["Year", "Artist", "Album", "Song Title"]
    header_font  = Font(name="Arial", bold=True, color="FFFFFF")
    header_fill  = PatternFill("solid", start_color="1F4E79")
    header_align = Alignment(horizontal="center", vertical="center")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font  = header_font
        cell.fill  = header_fill
        cell.alignment = header_align
    ws.row_dimensions[1].height = 20

    data_font = Font(name="Arial", size=10)
    for i, ((artist, title), year) in enumerate(rows, 2):
        ws.cell(row=i, column=1, value=year).font   = data_font
        ws.cell(row=i, column=2, value=artist).font = data_font
        ws.cell(row=i, column=3, value="").font     = data_font  # Album not in source
        ws.cell(row=i, column=4, value=title).font  = data_font

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 32
    ws.column_dimensions["D"].width = 44
    ws.freeze_panes = "A2"

    wb.save(path)


def main():
    all_entries = []  # list of (year, [ChartEntry])

    # --- Year-end charts ---
    print("Fetching year-end charts...")
    for year in YEAR_END_YEARS:
        entries = fetch_year_end(year)
        all_entries.append((year, entries))
        time.sleep(REQUEST_DELAY)

    # --- Weekly top-40 charts ---
    print("\nFetching weekly top-40 charts (1981-1988)...")
    for year in WEEKLY_TOP40_YEARS:
        entries = fetch_weekly_top40(year)
        all_entries.append((year, entries))

    # --- Deduplicate and write ---
    rows = build_song_dict(all_entries)
    write_xlsx(rows, OUTPUT_FILE)
    print(f"\nDone. {len(rows)} unique songs written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
