#!/usr/bin/env python3
"""Read published Univerus marketplace orders without external dependencies."""

import argparse
import json
import os
import sys
from datetime import datetime, time, timedelta
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_BASE_URL = "https://univerus.ai"
API_PATH = "/api/v1/marketplace"


class NoRedirects(HTTPRedirectHandler):
    """Do not forward the API key to a redirect destination."""

    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def request_json(path: str, params: dict[str, object] | None = None) -> object:
    key = os.environ.get("UNIVERUS_API_KEY", "")
    if not key:
        raise ValueError("Set UNIVERUS_API_KEY in your environment")
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise ValueError("UNIVERUS_API_KEY contains invalid characters; check secure storage")
    base_url = os.environ.get("UNIVERUS_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    parsed_url = urlsplit(base_url)
    if (
        not parsed_url.hostname or parsed_url.username or parsed_url.password
        or parsed_url.query or parsed_url.fragment or parsed_url.path
        or not (parsed_url.scheme == "https" or (
            parsed_url.scheme == "http" and parsed_url.hostname == "localhost"
            and parsed_url.port is not None
        ))
    ):
        raise ValueError("UNIVERUS_API_BASE_URL must be an HTTPS origin (or localhost with port)")
    query = f"?{urlencode(params)}" if params else ""
    api_path = path if path == "/api/v1/account/access" else API_PATH + path
    request = Request(
        f"{base_url}{api_path}{query}",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with build_opener(NoRedirects).open(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        raise ValueError(f"Univerus API returned HTTP {error.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("Could not reach Univerus API; check connection and retry later") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Univerus API returned invalid JSON") from None


def iso_offset(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use an ISO 8601 date and time") from error
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("Include a UTC offset, such as +03:00")
    return parsed.isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("access", help="Check current account scopes")
    commands.add_parser("categories", help="List active categories")
    order = commands.add_parser("order", help="Get one published order")
    order.add_argument("id")
    orders = commands.add_parser("orders", help="Search published orders")
    orders.add_argument("--category-id")
    orders.add_argument("--search")
    orders.add_argument("--today", action="store_true")
    orders.add_argument("--timezone", default="Europe/Moscow")
    orders.add_argument("--from-at", type=iso_offset)
    orders.add_argument("--before-at", type=iso_offset)
    orders.add_argument("--date-field", choices=("message", "discovered"), default="message")
    orders.add_argument("--sort", choices=("newest", "oldest"), default="newest")
    orders.add_argument("--page", type=int, default=1)
    orders.add_argument("--per-page", type=int, default=20)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "access":
            result = request_json("/api/v1/account/access")
        elif args.command == "categories":
            result = request_json("/categories")
        elif args.command == "order":
            try:
                order_id = UUID(args.id)
            except ValueError:
                parser.error("Order ID must be a UUID")
            result = request_json(f"/orders/{order_id}")
        else:
            if args.page < 1 or not 1 <= args.per_page <= 100:
                parser.error("--page must be positive and --per-page must be 1–100")
            if args.today and (args.from_at or args.before_at):
                parser.error("--today cannot be combined with explicit date bounds")
            from_at, before_at = args.from_at, args.before_at
            if args.today:
                try:
                    zone = ZoneInfo(args.timezone)
                except ZoneInfoNotFoundError:
                    parser.error("Unknown --timezone")
                start = datetime.combine(datetime.now(zone).date(), time.min, zone)
                end = datetime.combine(start.date() + timedelta(days=1), time.min, zone)
                from_at, before_at = start.isoformat(), end.isoformat()
            if from_at and before_at and datetime.fromisoformat(from_at) >= datetime.fromisoformat(before_at):
                parser.error("--from-at must be earlier than --before-at")
            if args.search is not None:
                args.search = args.search.strip()
                if not 2 <= len(args.search) <= 120:
                    parser.error("--search must contain 2–120 characters")
            if args.category_id is not None:
                try:
                    args.category_id = str(UUID(args.category_id))
                except ValueError:
                    parser.error("--category-id must be a UUID")
            params = {
                "date_field": args.date_field,
                "sort": args.sort,
                "page": args.page,
                "per_page": args.per_page,
            }
            for name, value in (
                ("category_id", args.category_id),
                ("search", args.search),
                ("from_at", from_at),
                ("before_at", before_at),
            ):
                if value is not None:
                    params[name] = value
            result = request_json("/orders", params)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
