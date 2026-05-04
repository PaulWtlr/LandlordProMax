import argparse

from .listings import add_listings_parser, fetch_foxtons_command, fetch_foxtons_prime_command, fetch_prime_command
from .ppd import fetch_year, filter_london, summarize
from .web import add_serve_parser, serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="london_property_analysis")
    subparsers = parser.add_subparsers(dest="domain", required=True)
    add_serve_parser(subparsers)
    add_listings_parser(subparsers)

    ppd = subparsers.add_parser("ppd", help="HM Land Registry Price Paid Data tools")
    ppd_sub = ppd.add_subparsers(dest="command", required=True)

    fetch = ppd_sub.add_parser("fetch-year", help="Download a yearly Price Paid CSV")
    fetch.add_argument("year", type=int)
    fetch.add_argument("--out", required=True)

    london = ppd_sub.add_parser("filter-london", help="Filter Price Paid CSV to London")
    london.add_argument("input_csv")
    london.add_argument("--out", required=True)

    summary = ppd_sub.add_parser("summary", help="Print basic market summary")
    summary.add_argument("input_csv")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.domain == "serve":
        serve(args.host, args.port)
        return 0

    if args.domain == "listings" and args.command == "fetch-foxtons":
        fetch_foxtons_command(args)
        return 0

    if args.domain == "listings" and args.command == "fetch-foxtons-prime":
        fetch_foxtons_prime_command(args)
        return 0

    if args.domain == "listings" and args.command == "fetch-prime":
        fetch_prime_command(args)
        return 0

    if args.domain == "ppd" and args.command == "fetch-year":
        fetch_year(args.year, args.out)
        return 0

    if args.domain == "ppd" and args.command == "filter-london":
        filter_london(args.input_csv, args.out)
        return 0

    if args.domain == "ppd" and args.command == "summary":
        summarize(args.input_csv)
        return 0

    raise ValueError(f"Unsupported command: {args}")
