from __future__ import annotations

import csv
import statistics
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path


PPD_COLUMNS = [
    "transaction_id",
    "price",
    "transfer_date",
    "postcode",
    "property_type",
    "old_new",
    "duration",
    "paon",
    "saon",
    "street",
    "locality",
    "town_city",
    "district",
    "county",
    "ppd_category_type",
    "record_status",
]

LONDON_DISTRICTS = {
    "BARKING AND DAGENHAM",
    "BARNET",
    "BEXLEY",
    "BRENT",
    "BROMLEY",
    "CAMDEN",
    "CITY OF LONDON",
    "CITY OF WESTMINSTER",
    "CROYDON",
    "EALING",
    "ENFIELD",
    "GREENWICH",
    "HACKNEY",
    "HAMMERSMITH AND FULHAM",
    "HARINGEY",
    "HARROW",
    "HAVERING",
    "HILLINGDON",
    "HOUNSLOW",
    "ISLINGTON",
    "KENSINGTON AND CHELSEA",
    "KINGSTON UPON THAMES",
    "LAMBETH",
    "LEWISHAM",
    "MERTON",
    "NEWHAM",
    "REDBRIDGE",
    "RICHMOND UPON THAMES",
    "SOUTHWARK",
    "SUTTON",
    "TOWER HAMLETS",
    "WALTHAM FOREST",
    "WANDSWORTH",
}


def yearly_url(year: int) -> str:
    if year < 1995:
        raise ValueError("HM Land Registry Price Paid yearly files start in 1995.")
    return f"https://price-paid-data.publicdata.landregistry.gov.uk/pp-{year}.csv"


def fetch_year(year: int, out: str) -> None:
    destination = Path(out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = yearly_url(year)
    print(f"Downloading {url} -> {destination}", file=sys.stderr)
    urllib.request.urlretrieve(url, destination)
    print(f"Wrote {destination}", file=sys.stderr)


def iter_ppd_rows(path: str):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for raw in reader:
            if not raw:
                continue
            padded = raw + [""] * (len(PPD_COLUMNS) - len(raw))
            yield dict(zip(PPD_COLUMNS, padded[: len(PPD_COLUMNS)]))


def is_london_row(row: dict[str, str]) -> bool:
    district = row["district"].strip().upper()
    county = row["county"].strip().upper()
    town = row["town_city"].strip().upper()
    return (
        district in LONDON_DISTRICTS
        or county == "GREATER LONDON"
        or town == "LONDON"
    )


def filter_london(input_csv: str, out: str) -> None:
    destination = Path(out)
    destination.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    kept = 0
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PPD_COLUMNS)
        writer.writeheader()
        for row in iter_ppd_rows(input_csv):
            total += 1
            if is_london_row(row):
                writer.writerow(row)
                kept += 1

    print(f"Kept {kept:,} London rows from {total:,} transactions.", file=sys.stderr)


def summarize(input_csv: str) -> None:
    prices: list[int] = []
    by_district: dict[str, list[int]] = defaultdict(list)
    by_type: Counter[str] = Counter()

    with Path(input_csv).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                price = int(row["price"])
            except (TypeError, ValueError):
                continue

            prices.append(price)
            by_district[row["district"] or "UNKNOWN"].append(price)
            by_type[row["property_type"] or "UNKNOWN"] += 1

    if not prices:
        print("No valid prices found.")
        return

    print(f"Transactions: {len(prices):,}")
    print(f"Median price: GBP {statistics.median(prices):,.0f}")
    print(f"Mean price:   GBP {statistics.mean(prices):,.0f}")
    print()
    print("Top districts by transaction count:")
    for district, values in sorted(by_district.items(), key=lambda item: len(item[1]), reverse=True)[:10]:
        print(f"- {district}: {len(values):,} tx, median GBP {statistics.median(values):,.0f}")
    print()
    print("Property types:")
    for property_type, count in by_type.most_common():
        print(f"- {property_type}: {count:,}")

