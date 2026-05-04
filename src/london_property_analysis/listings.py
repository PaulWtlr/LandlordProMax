from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser


LISTING_COLUMNS = [
    "source",
    "sourceId",
    "address",
    "postcode",
    "neighbourhood",
    "price",
    "bedrooms",
    "bathrooms",
    "sqft",
    "lat",
    "lng",
    "propertyType",
    "tenure",
    "agent",
    "status",
    "url",
    "capturedAt",
    "daysOnMarket",
    "serviceCharge",
    "leaseYears",
    "rentEstimate",
    "grossYield",
    "score",
    "notes",
]

FOXTONS_LONDON_URL = "https://www.foxtons.co.uk/properties-for-sale/london"
FOXTONS_PRIME_URLS = [
    "https://www.foxtons.co.uk/properties-for-sale/chelsea-sw3",
    "https://www.foxtons.co.uk/properties-for-sale/chelsea-harbour-sw10",
    "https://www.foxtons.co.uk/properties-for-sale/south-kensington-sw7",
    "https://www.foxtons.co.uk/flats-for-sale/chelsea-sw3",
    "https://www.foxtons.co.uk/flats-for-sale/chelsea-harbour-sw10",
    "https://www.foxtons.co.uk/flats-for-sale/south-kensington-sw7",
    "https://www.foxtons.co.uk/houses-for-sale/chelsea-sw3",
    "https://www.foxtons.co.uk/houses-for-sale/chelsea-harbour-sw10",
    "https://www.foxtons.co.uk/houses-for-sale/south-kensington-sw7",
]
USER_AGENT = "LandlordProMax/0.1 local research"
LONDON_BOUNDS = {"south": 51.28, "north": 51.70, "west": -0.55, "east": 0.35}
PRIME_POSTCODES = {"SW3", "SW7", "SW10"}
PRIME_AREA_NAMES = {"CHELSEA", "SOUTH KENSINGTON", "CHELSEA HARBOUR"}


def fetch_foxtons(url: str = FOXTONS_LONDON_URL, limit: int = 100) -> list[dict[str, object]]:
    ensure_allowed_by_robots(url)
    payload = fetch_text(url)
    rows = parse_foxtons_page(payload, url)
    rows = [row for row in rows if is_london_row(row)]
    return rows[:limit]


def fetch_foxtons_prime(limit: int = 1000, urls: list[str] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for url in urls or FOXTONS_PRIME_URLS:
        print(f"Fetching {url}")
        rows.extend(fetch_foxtons(url, limit=limit))
    rows = [row for row in dedupe(rows) if is_prime_row(row)]
    rows.sort(key=lambda row: (-(to_int(row.get("price")) or 0), str(row.get("address") or "")))
    return rows[:limit]


def ensure_allowed_by_robots(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    robots = robotparser.RobotFileParser()
    robots.set_url(robots_url)
    robots.read()
    if not robots.can_fetch(USER_AGENT, url):
        raise PermissionError(f"robots.txt does not allow fetching {url}")
    delay = robots.crawl_delay(USER_AGENT) or robots.crawl_delay("*")
    if delay:
        time.sleep(min(float(delay), 5.0))


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def parse_foxtons_page(payload: str, source_url: str) -> list[dict[str, object]]:
    next_data = extract_next_data(payload)
    page_data = next_data["props"]["pageProps"]["pageData"]
    listings = page_data["data"]["data"]
    captured_at = datetime.now(timezone.utc).date().isoformat()
    rows: list[dict[str, object]] = []

    for item in listings:
        blob = item.get("propertyBlob") or {}
        location = item.get("location") or {}
        property_ref = clean(item.get("propertyReference"))
        postcode = clean(item.get("postcodeShort"))
        address = make_address(item, blob, postcode)
        price = to_int(item.get("priceFrom") or item.get("priceTo"))
        lat = to_float(location.get("lat"))
        lng = to_float(location.get("lon") or location.get("lng"))
        if not property_ref or not price or lat is None or lng is None:
            continue

        property_type = clean(item.get("typeGroup")) or "Property"
        neighbourhood = (
            clean(blob.get("subregionName"))
            or clean(blob.get("locationName"))
            or infer_neighbourhood(address, postcode)
        )
        neighbourhood = normalise_prime_neighbourhood(neighbourhood, address, postcode)
        status = "under_offer" if item.get("isUnderOffer") else "for_sale"
        relative_path = f"/properties-for-sale/{postcode.lower()}/{property_ref}" if postcode else ""
        detail_url = urllib.parse.urljoin(source_url, relative_path)
        sqft = to_int(blob.get("floorArea"))

        rows.append(
            {
                "source": "foxtons",
                "sourceId": property_ref,
                "address": address,
                "postcode": postcode,
                "neighbourhood": neighbourhood,
                "price": price,
                "bedrooms": to_int(item.get("bedrooms")),
                "bathrooms": to_int(item.get("bathrooms")),
                "sqft": sqft,
                "lat": lat,
                "lng": lng,
                "propertyType": property_type.title(),
                "tenure": clean(blob.get("tenure")),
                "agent": clean(item.get("officeName")) or "Foxtons",
                "status": status,
                "url": detail_url,
                "capturedAt": captured_at,
                "daysOnMarket": "",
                "serviceCharge": to_int(blob.get("serviceCharge")),
                "leaseYears": "",
                "rentEstimate": "",
                "grossYield": "",
                "score": score_listing(price=price, sqft=sqft, status=status),
                "notes": make_notes(item, blob),
            }
        )

    return dedupe(rows)


def extract_next_data(payload: str) -> dict[str, object]:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        payload,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ payload in Foxtons page.")
    return json.loads(html.unescape(match.group(1)))


def make_address(item: dict[str, object], blob: dict[str, object], postcode: str) -> str:
    display = clean(item.get("streetName"))
    line1 = clean(blob.get("addressLine1"))
    town = clean(blob.get("addressTown"))
    parts = [display or line1, town if town and town.lower() != "london" else "", postcode]
    return ", ".join(part for part in parts if part)


def make_notes(item: dict[str, object], blob: dict[str, object]) -> str:
    flags = []
    if item.get("isReduced"):
        flags.append("Reduced")
    if item.get("hasVideo"):
        flags.append("Video")
    if item.get("hasVirtualTour"):
        flags.append("Virtual tour")
    if item.get("hasGarden"):
        flags.append("Garden")
    if item.get("hasBalcony"):
        flags.append("Balcony")
    if item.get("isNewHome"):
        flags.append("New home")
    council = clean(blob.get("councilBand"))
    if council:
        flags.append(f"Council band {council}")
    return " | ".join(flags)


def infer_neighbourhood(address: str, postcode: str) -> str:
    lowered = address.lower()
    if "chelsea" in lowered or postcode in {"SW3", "SW10"}:
        return "Chelsea"
    if "kensington" in lowered or postcode == "SW7":
        return "South Kensington"
    return postcode or "London"


def normalise_prime_neighbourhood(neighbourhood: str, address: str, postcode: str) -> str:
    text = f"{neighbourhood} {address}".lower()
    postcode = postcode.upper()
    if "south kensington" in text or postcode == "SW7":
        return "South Kensington"
    if "chelsea harbour" in text:
        return "Chelsea Harbour"
    if "chelsea" in text or postcode in {"SW3", "SW10"}:
        return "Chelsea"
    return neighbourhood


def score_listing(price: int, sqft: int | None, status: str) -> int:
    score = 65
    if sqft and sqft > 0:
        psf = price / sqft
        if psf < 1100:
            score += 18
        elif psf < 1500:
            score += 10
        elif psf > 2300:
            score -= 10
    if status == "under_offer":
        score -= 6
    return max(0, min(100, score))


def is_london_row(row: dict[str, object]) -> bool:
    lat = to_float(row.get("lat"))
    lng = to_float(row.get("lng"))
    if lat is None or lng is None:
        return False
    return (
        LONDON_BOUNDS["south"] <= lat <= LONDON_BOUNDS["north"]
        and LONDON_BOUNDS["west"] <= lng <= LONDON_BOUNDS["east"]
    )


def dedupe(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, object]] = []
    for row in rows:
        key = (str(row.get("source")), str(row.get("sourceId")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def write_csv(rows: list[dict[str, object]], path: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LISTING_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in LISTING_COLUMNS})


def write_json(rows: list[dict[str, object]], path: str, meta: dict[str, object] | None = None) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "count": len(rows),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "source": "foxtons",
            **(meta or {}),
        },
        "listings": rows,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_js(rows: list[dict[str, object]], path: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(rows, ensure_ascii=False, indent=2)
    destination.write_text(f"window.LIVE_PROPERTIES = {serialised};\n", encoding="utf-8")


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else None


def to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_foxtons_command(args: argparse.Namespace) -> None:
    rows = fetch_foxtons(args.url, args.limit)
    write_csv(rows, args.out)
    if args.json_out:
        write_json(rows, args.json_out, {"mode": "london", "requestedLimit": args.limit, "urls": [args.url]})
    if args.js_out:
        write_js(rows, args.js_out)
    print(f"Collected {len(rows)} Foxtons listings -> {args.out}")
    if args.json_out:
        print(f"Wrote app JSON dataset -> {args.json_out}")
    if args.js_out:
        print(f"Wrote app dataset -> {args.js_out}")


def fetch_foxtons_prime_command(args: argparse.Namespace) -> None:
    rows = fetch_foxtons_prime(args.limit)
    write_csv(rows, args.out)
    if args.json_out:
        write_json(
            rows,
            args.json_out,
            {
                "mode": "chelsea_south_kensington",
                "requestedLimit": args.limit,
                "areas": ["Chelsea", "South Kensington"],
                "urls": FOXTONS_PRIME_URLS,
            },
        )
    if args.js_out:
        write_js(rows, args.js_out)
    print(f"Collected {len(rows)} Foxtons Chelsea/South Kensington listings -> {args.out}")
    if len(rows) < args.limit:
        print(f"Foxtons exposed {len(rows)} unique matching listings, fewer than requested limit {args.limit}.")
    if args.json_out:
        print(f"Wrote app JSON dataset -> {args.json_out}")
    if args.js_out:
        print(f"Wrote app dataset -> {args.js_out}")


def add_listings_parser(subparsers: argparse._SubParsersAction) -> None:
    listings = subparsers.add_parser("listings", help="Collect and export active listings")
    listing_sub = listings.add_subparsers(dest="command", required=True)

    foxtons = listing_sub.add_parser("fetch-foxtons", help="Fetch public Foxtons London sale listings")
    foxtons.add_argument("--url", default=FOXTONS_LONDON_URL)
    foxtons.add_argument("--limit", default=100, type=int)
    foxtons.add_argument("--out", default="data/processed/london-listings.csv")
    foxtons.add_argument("--json-out", default="data/live_properties.json")
    foxtons.add_argument("--js-out", default="data/live_properties.js")

    prime = listing_sub.add_parser(
        "fetch-foxtons-prime",
        help="Fetch public Foxtons Chelsea and South Kensington sale listings",
    )
    prime.add_argument("--limit", default=1000, type=int)
    prime.add_argument("--out", default="data/processed/chelsea-south-kensington-listings.csv")
    prime.add_argument("--json-out", default="data/live_properties.json")
    prime.add_argument("--js-out", default="data/live_properties.js")


def is_prime_row(row: dict[str, object]) -> bool:
    postcode = clean(row.get("postcode")).upper()
    neighbourhood = clean(row.get("neighbourhood")).upper()
    address = clean(row.get("address")).upper()
    if postcode in PRIME_POSTCODES:
        return True
    if neighbourhood in PRIME_AREA_NAMES:
        return True
    return any(name in address for name in PRIME_AREA_NAMES)
