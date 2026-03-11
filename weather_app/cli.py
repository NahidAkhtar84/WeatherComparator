from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from constants import DEFAULT_CITY, DEFAULT_INTERVAL_SECONDS
from weather_app.services import fetch_all_sources, format_result, geocode_city


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Periodically fetch and compare weather data from multiple sources in parallel."
    )
    parser.add_argument("--city", default=DEFAULT_CITY, help=f"City name (default: {DEFAULT_CITY})")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Seconds between fetch cycles (default: {DEFAULT_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="How many cycles to run. 0 means run forever (default: 0).",
    )
    return parser.parse_args()


def run_once(city: str) -> None:
    location = geocode_city(city)
    print(f"\n=== Weather fetch @ {datetime.now().isoformat(timespec='seconds')} ===")
    results, stats = fetch_all_sources(location)
    
    # Display stats
    print(f"Stats: Min={stats['min_temp']}°C Max={stats['max_temp']}°C Avg={stats['avg_temp']}°C")
    
    # Display individual results
    for result in results:
        print(format_result(result))


def main() -> int:
    args = parse_args()

    if args.interval <= 0:
        print("--interval must be a positive integer", file=sys.stderr)
        return 2
    if args.iterations < 0:
        print("--iterations cannot be negative", file=sys.stderr)
        return 2

    try:
        geocode_city(args.city)
    except Exception as exc:
        print(f"Failed to resolve city '{args.city}': {exc}", file=sys.stderr)
        return 1

    cycle = 0
    while True:
        cycle += 1
        run_once(args.city)

        if args.iterations and cycle >= args.iterations:
            break

        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
