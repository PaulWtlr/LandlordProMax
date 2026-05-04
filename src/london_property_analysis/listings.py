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
    "floorLevel",
    "isLowerGround",
    "rentEstimate",
    "grossYield",
    "score",
    "description",
    "notes",
]

FOXTONS_LONDON_URL = "https://www.foxtons.co.uk/properties-for-sale/london"
FOXTONS_PRIME_URLS = [
    "https://www.foxtons.co.uk/properties-for-sale/chelsea",
    "https://www.foxtons.co.uk/properties-for-sale/chelsea-sw3",
    "https://www.foxtons.co.uk/properties-for-sale/chelsea-harbour-sw10",
    "https://www.foxtons.co.uk/properties-for-sale/chelsea-embankment-sw3",
    "https://www.foxtons.co.uk/properties-for-sale/south-kensington",
    "https://www.foxtons.co.uk/properties-for-sale/south-kensington-sw7",
    "https://www.foxtons.co.uk/flats-for-sale/chelsea",
    "https://www.foxtons.co.uk/flats-for-sale/chelsea-sw3",
    "https://www.foxtons.co.uk/flats-for-sale/chelsea-harbour-sw10",
    "https://www.foxtons.co.uk/flats-for-sale/chelsea-embankment-sw3",
    "https://www.foxtons.co.uk/flats-for-sale/south-kensington",
    "https://www.foxtons.co.uk/flats-for-sale/south-kensington-sw7",
    "https://www.foxtons.co.uk/houses-for-sale/chelsea-sw3",
    "https://www.foxtons.co.uk/houses-for-sale/chelsea-harbour-sw10",
    "https://www.foxtons.co.uk/houses-for-sale/south-kensington-sw7",
]
FOXTONS_BEDROOM_URLS = [
    f"https://www.foxtons.co.uk/flats-for-sale/{area}/{beds}-bedroom"
    for area in ("chelsea", "south-kensington")
    for beds in range(1, 6)
]
DEXTERS_PRIME_URLS = [
    "https://www.dexters.co.uk/property-sales/flats-for-sale-in-chelsea",
    "https://www.dexters.co.uk/property-sales/flats-for-sale-in-south-kensington",
]
TARGET_PRICE_MIN = 850_000
TARGET_PRICE_MAX = 1_500_000
USER_AGENT = "LandlordProMax/0.1 local research"
LONDON_BOUNDS = {"south": 51.28, "north": 51.70, "west": -0.55, "east": 0.35}
PRIME_POSTCODES = {"SW3", "SW7", "SW10"}
PRIME_AREA_NAMES = {"CHELSEA", "SOUTH KENSINGTON", "CHELSEA HARBOUR"}
ROBOTS_CACHE: dict[str, robotparser.RobotFileParser] = {}


def fetch_foxtons(url: str = FOXTONS_LONDON_URL, limit: int = 100) -> list[dict[str, object]]:
    ensure_allowed_by_robots(url)
    payload = fetch_text(url)
    rows = parse_foxtons_page(payload, url)
    rows = [row for row in rows if is_london_row(row)]
    return rows[:limit]


def fetch_foxtons_prime(limit: int = 1000, urls: list[str] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for url in urls or [*FOXTONS_PRIME_URLS, *FOXTONS_BEDROOM_URLS]:
        print(f"Fetching {url}")
        try:
            rows.extend(fetch_foxtons(url, limit=limit))
        except Exception as exc:
            print(f"Skipped {url}: {exc}")
    rows = [row for row in dedupe(rows) if is_prime_row(row)]
    enrich_foxtons_details(rows, max_details=min(limit, 120))
    rows.sort(key=lambda row: (-(to_int(row.get("price")) or 0), str(row.get("address") or "")))
    return rows[:limit]


def fetch_prime_listings(limit: int = 1000) -> list[dict[str, object]]:
    rows = fetch_foxtons_prime(limit=limit)
    try:
        rows.extend(fetch_dexters_prime(min_price=TARGET_PRICE_MIN, max_price=TARGET_PRICE_MAX, limit=250))
    except Exception as exc:
        print(f"Skipped Dexters collector: {exc}")
    rows = dedupe(rows)
    rows.sort(key=lambda row: (target_price_rank(row), str(row.get("source") or ""), str(row.get("address") or "")))
    return rows[:limit]


def target_price_rank(row: dict[str, object]) -> tuple[int, int]:
    price = to_int(row.get("price")) or 0
    in_target = TARGET_PRICE_MIN <= price <= TARGET_PRICE_MAX
    distance = 0 if in_target else min(abs(price - TARGET_PRICE_MIN), abs(price - TARGET_PRICE_MAX))
    return (0 if in_target else 1, distance)


def ensure_allowed_by_robots(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    robots_root = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{robots_root}/robots.txt"
    robots = ROBOTS_CACHE.get(robots_root)
    if robots is None:
        robots = robotparser.RobotFileParser()
        robots.set_url(robots_url)
        robots.read()
        ROBOTS_CACHE[robots_root] = robots
    if not robots.can_fetch(USER_AGENT, url):
        raise PermissionError(f"robots.txt does not allow fetching {url}")
    delay = robots.crawl_delay(USER_AGENT) or robots.crawl_delay("*")
    if delay:
        time.sleep(min(float(delay), 5.0))


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
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
                "floorLevel": clean(blob.get("entranceFloor")),
                "isLowerGround": is_lower_ground_text(clean(blob.get("entranceFloor")), make_notes(item, blob)),
                "rentEstimate": "",
                "grossYield": "",
                "score": score_listing(price=price, sqft=sqft, status=status),
                "description": clean(blob.get("descriptionShort")) or clean(blob.get("description")),
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


def enrich_foxtons_details(rows: list[dict[str, object]], max_details: int = 250) -> None:
    detail_rows = [row for row in rows if row.get("url") and row.get("source") == "foxtons"]
    target_first = sorted(
        detail_rows,
        key=lambda row: target_price_rank(row),
    )
    for index, row in enumerate(target_first[:max_details], start=1):
        try:
            payload = fetch_text(str(row["url"]))
            detail = extract_next_data(payload)["props"]["pageProps"].get("propertyDetail") or {}
            blob = detail.get("propertyBlob") or {}
        except Exception as exc:
            print(f"Skipped Foxtons detail {row.get('sourceId')}: {exc}")
            continue

        floor = clean(blob.get("entranceFloor"))
        description = clean(blob.get("descriptionShort")) or clean(blob.get("description"))
        bullet_points = blob.get("bulletPoints") if isinstance(blob.get("bulletPoints"), list) else []
        if floor:
            row["floorLevel"] = floor
        if description:
            row["description"] = description
        if bullet_points:
            row["notes"] = " | ".join(clean(point) for point in bullet_points[:5] if clean(point))
        row["isLowerGround"] = is_lower_ground_text(
            clean(row.get("floorLevel")),
            clean(row.get("description")),
            clean(row.get("notes")),
        )
        if index % 50 == 0:
            print(f"Enriched {index} Foxtons detail pages")


def fetch_dexters_prime(
    min_price: int = TARGET_PRICE_MIN,
    max_price: int = TARGET_PRICE_MAX,
    limit: int = 250,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for seed_url in DEXTERS_PRIME_URLS:
        for url in discover_dexters_pages(seed_url):
            print(f"Fetching {url}")
            try:
                rows.extend(parse_dexters_page(fetch_text(url), url, min_price=min_price, max_price=max_price))
            except Exception as exc:
                print(f"Skipped {url}: {exc}")
            if len(rows) >= limit:
                break
    rows = [row for row in dedupe(rows) if is_prime_row(row) and is_london_row(row)]
    return rows[:limit]


def discover_dexters_pages(seed_url: str) -> list[str]:
    ensure_allowed_by_robots(seed_url)
    payload = fetch_text(seed_url)
    pages = {seed_url}
    for href in re.findall(r'href="([^"]*/page-\d+)"', payload):
        pages.add(urllib.parse.urljoin(seed_url, href))
    return sorted(pages, key=lambda value: (page_number(value), value))


def page_number(url: str) -> int:
    match = re.search(r"/page-(\d+)", url)
    return int(match.group(1)) if match else 1


def parse_dexters_page(payload: str, source_url: str, min_price: int, max_price: int) -> list[dict[str, object]]:
    blocks = re.split(r'(?=<li class="result item )', payload)
    rows: list[dict[str, object]] = []
    captured_at = datetime.now(timezone.utc).date().isoformat()
    for block in blocks:
        if 'class="result item' not in block or "data-property-id" not in block:
            continue
        class_match = re.search(r'<li class="result item ([^"]+)" data-property-id="([^"]+)"', block)
        if not class_match:
            continue
        status_class, property_id = class_match.groups()
        if "sold" in status_class or "under-offer" in status_class:
            continue
        link_match = re.search(r'<h2><a href="([^"]+)">(.*?)</a></h2>', block, flags=re.DOTALL)
        price_match = re.search(r'data-price="([^"]+)"', block)
        if not link_match or not price_match:
            continue
        price = to_int(price_match.group(1))
        if not price or price < min_price or price > max_price:
            continue

        detail_url = urllib.parse.urljoin(source_url, link_match.group(1))
        heading_html = link_match.group(2)
        address = dexters_address(heading_html)
        postcode = extract_postcode(address)
        info_text = strip_tags(block)
        bedrooms = to_int(first_regex(r"(\d+)\s+Bedrooms?", info_text))
        bathrooms = to_int(first_regex(r"(\d+)\s+Bathrooms?", info_text))
        description = clean(strip_tags(first_regex(r'<div class="result-entry"><p>(.*?)</p>', block, flags=re.DOTALL)))
        sqft = to_int(first_regex(r"approximately\s+([0-9,]+)\s*sqft|([0-9,]+)\s*sqft", description, flags=re.I))
        floor_level = infer_floor_level(description, address)
        detail = fetch_dexters_detail(detail_url)
        if detail:
            floor_level = detail.get("floorLevel") or floor_level
            description = detail.get("description") or description
            sqft = to_int(detail.get("sqft")) or sqft
        lat = to_float(detail.get("lat") if detail else None)
        lng = to_float(detail.get("lng") if detail else None)
        if lat is None or lng is None:
            continue

        rows.append(
            {
                "source": "dexters",
                "sourceId": property_id,
                "address": address,
                "postcode": postcode,
                "neighbourhood": infer_neighbourhood(address, postcode),
                "price": price,
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "sqft": sqft,
                "lat": lat,
                "lng": lng,
                "propertyType": "Flat",
                "tenure": "",
                "agent": "Dexters",
                "status": "for_sale",
                "url": detail_url,
                "capturedAt": captured_at,
                "daysOnMarket": "",
                "serviceCharge": "",
                "leaseYears": "",
                "floorLevel": floor_level,
                "isLowerGround": is_lower_ground_text(floor_level, description),
                "rentEstimate": "",
                "grossYield": "",
                "score": score_listing(price=price, sqft=sqft, status="for_sale"),
                "description": description,
                "notes": "Dexters targeted 850k-1.5m flat",
            }
        )
    return rows


def fetch_dexters_detail(url: str) -> dict[str, object]:
    ensure_allowed_by_robots(url)
    payload = fetch_text(url)
    lat = first_regex(r"lat:\s*([0-9.-]+)", payload)
    lng = first_regex(r"lng:\s*([0-9.-]+)", payload)
    description = clean(strip_tags(first_regex(r'<div class="description[^"]*">(.*?)</div>', payload, flags=re.DOTALL)))
    if not description:
        description = clean(strip_tags(first_regex(r'"description"\s*:\s*"([^"]+)"', payload)))
    floor_level = infer_floor_level(payload[:80_000], description)
    sqft = to_int(first_regex(r"([0-9,]+)\s*sqft", payload, flags=re.I))
    return {"lat": lat, "lng": lng, "description": description, "floorLevel": floor_level, "sqft": sqft}


def dexters_address(heading_html: str) -> str:
    area_match = re.search(r'<span class="address-area-post">(.*?)</span>', heading_html, flags=re.DOTALL)
    area = clean(strip_tags(area_match.group(1))) if area_match else ""
    street = clean(strip_tags(re.sub(r'<span class="address-area-post">.*?</span>', "", heading_html, flags=re.DOTALL)))
    return ", ".join(part for part in [street, area] if part)


def strip_tags(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def first_regex(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text or "", flags=flags)
    if not match:
        return ""
    for group in match.groups():
        if group:
            return group
    return match.group(0)


def extract_postcode(text: str) -> str:
    match = re.search(r"\b(SW(?:3|7|10)|SW1X|SW5)\b", text.upper())
    return match.group(1) if match else ""


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


def is_lower_ground_text(*values: str) -> bool:
    text = " ".join(value for value in values if value).lower()
    return bool(re.search(r"lower[-\s]?ground|basement|garden\s+level", text))


def infer_floor_level(*values: str) -> str:
    text = " ".join(value for value in values if value)
    lowered = text.lower()
    if "lower ground" in lowered or "lower-ground" in lowered:
        return "Lower Ground"
    if "raised ground" in lowered:
        return "Raised Ground"
    if "ground floor" in lowered or "ground-floor" in lowered:
        return "Ground"
    floor_patterns = [
        (r"\bfirst floor\b|\b1st floor\b", "1st"),
        (r"\bsecond floor\b|\b2nd floor\b", "2nd"),
        (r"\bthird floor\b|\b3rd floor\b", "3rd"),
        (r"\bfourth floor\b|\b4th floor\b", "4th"),
        (r"\bfifth floor\b|\b5th floor\b", "5th"),
        (r"\bsixth floor\b|\b6th floor\b", "6th"),
    ]
    for pattern, label in floor_patterns:
        if re.search(pattern, lowered):
            return label
    return ""


def infer_neighbourhood(address: str, postcode: str) -> str:
    lowered = address.lower()
    if "chelsea" in lowered or postcode in {"SW3", "SW10"}:
        return "Chelsea"
    if "south kensington" in lowered or postcode == "SW7":
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
                "urls": [*FOXTONS_PRIME_URLS, *FOXTONS_BEDROOM_URLS],
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


def fetch_prime_command(args: argparse.Namespace) -> None:
    rows = fetch_prime_listings(args.limit)
    write_csv(rows, args.out)
    meta = {
        "mode": "chelsea_south_kensington",
        "requestedLimit": args.limit,
        "areas": ["Chelsea", "South Kensington"],
        "source": "multi_agency",
        "sources": sorted({str(row.get("source")).title() for row in rows if row.get("source")}),
        "targetPriceMin": TARGET_PRICE_MIN,
        "targetPriceMax": TARGET_PRICE_MAX,
        "urls": [*FOXTONS_PRIME_URLS, *FOXTONS_BEDROOM_URLS, *DEXTERS_PRIME_URLS],
    }
    if args.json_out:
        write_json(rows, args.json_out, meta)
    if args.js_out:
        write_js(rows, args.js_out)
    print(f"Collected {len(rows)} multi-agency Chelsea/South Kensington listings -> {args.out}")
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

    multi = listing_sub.add_parser(
        "fetch-prime",
        help="Fetch public multi-agency Chelsea and South Kensington sale listings",
    )
    multi.add_argument("--limit", default=1000, type=int)
    multi.add_argument("--out", default="data/processed/chelsea-south-kensington-listings.csv")
    multi.add_argument("--json-out", default="data/live_properties.json")
    multi.add_argument("--js-out", default="data/live_properties.js")


def is_prime_row(row: dict[str, object]) -> bool:
    postcode = clean(row.get("postcode")).upper()
    neighbourhood = clean(row.get("neighbourhood")).upper()
    address = clean(row.get("address")).upper()
    if postcode in PRIME_POSTCODES:
        return True
    if neighbourhood in PRIME_AREA_NAMES:
        return True
    return any(name in address for name in PRIME_AREA_NAMES)
