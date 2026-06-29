#!/usr/bin/env python3
"""Map a website's URL structure via Tavily /map.

Use when you need to discover what's in a docs site / knowledge base before
choosing specific pages to fetch.

Usage:
    python web_map.py --url "https://docs.tavily.com"
    python web_map.py --url "..." --depth 2 --instructions "find API reference"

Output: JSON {url, urls[], urls_count, elapsed_s}.
"""
from __future__ import annotations

import argparse
import sys
import time

from _http import dump_json, tavily_post


def main() -> int:
    p = argparse.ArgumentParser(description="Site structure mapping via Tavily")
    p.add_argument("--url", required=True)
    p.add_argument("--depth", type=int, default=1, choices=[1, 2, 3, 4, 5])
    p.add_argument("--breadth", type=int, default=20, help="Max links per page (1-500)")
    p.add_argument("--limit", type=int, default=50, help="Total URL cap (1-500)")
    p.add_argument("--instructions", default="", help="Natural language filter")
    args = p.parse_args()

    body = {
        "url": args.url,
        "max_depth": args.depth,
        "max_breadth": args.breadth,
        "limit": args.limit,
    }
    if args.instructions:
        body["instructions"] = args.instructions

    t0 = time.time()
    try:
        data = tavily_post("map", body, timeout=150)
    except Exception as e:
        dump_json({"error": str(e), "url": args.url})
        return 1
    elapsed = round(time.time() - t0, 2)

    urls = data.get("results", [])
    dump_json({
        "url": args.url,
        "urls": urls,
        "urls_count": len(urls),
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())