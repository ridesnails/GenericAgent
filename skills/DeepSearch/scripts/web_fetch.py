#!/usr/bin/env python3
"""Fetch a single URL's content as markdown.

Primary path: Tavily /extract (clean, fast, handles most sites).
Fallback: FireCrawl /scrape (better for Cloudflare-protected or JS-heavy pages).

Usage:
    python web_fetch.py --url "https://docs.python.org/3/whatsnew/3.13.html"
    python web_fetch.py --url "..." --force-firecrawl

Output: JSON {url, provider, markdown, length, elapsed_s}. On error: error/last_error.
"""
from __future__ import annotations

import argparse
import sys
import time

from _http import dump_json, firecrawl_post, log, tavily_post


def try_tavily(url: str) -> dict:
    data = tavily_post(
        "extract",
        {"urls": [url], "include_images": False, "extract_depth": "advanced"},
        timeout=60,
    )
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"Tavily returned no results for {url}")
    raw = (results[0].get("raw_content") or "").strip()
    if not raw:
        raise RuntimeError("Tavily returned empty content")
    return {"markdown": raw, "provider": "tavily"}


def try_firecrawl(url: str) -> dict:
    data = firecrawl_post(
        "scrape",
        {"url": url, "formats": ["markdown"], "onlyMainContent": True},
    )
    if not data.get("success", True):
        raise RuntimeError(f"FireCrawl error: {data.get('error')}")
    payload = data.get("data", data)
    md = (payload.get("markdown") or "").strip()
    if not md:
        raise RuntimeError("FireCrawl returned empty markdown")
    return {"markdown": md, "provider": "firecrawl"}


def main() -> int:
    p = argparse.ArgumentParser(description="Single-URL page fetcher")
    p.add_argument("--url", required=True)
    p.add_argument("--force-firecrawl", action="store_true", help="Skip Tavily, go straight to FireCrawl")
    p.add_argument("--max-length", type=int, default=0, help="Truncate markdown to N chars (0 = full)")
    args = p.parse_args()

    providers = []
    if not args.force_firecrawl:
        providers.append(("tavily", try_tavily))
    providers.append(("firecrawl", try_firecrawl))

    t0 = time.time()
    last_err: str | None = None
    result: dict | None = None
    for name, fn in providers:
        try:
            log(f"trying provider: {name}")
            result = fn(args.url)
            break
        except Exception as e:
            last_err = f"{name}: {e}"
            log(f"provider {name} failed - {e}")

    elapsed = round(time.time() - t0, 2)
    if result is None:
        dump_json({"url": args.url, "error": "all providers failed", "last_error": last_err, "elapsed_s": elapsed})
        return 1

    md = result["markdown"]
    full_len = len(md)
    if args.max_length and full_len > args.max_length:
        md = md[: args.max_length] + f"\n\n... [truncated at {args.max_length} chars]"

    dump_json({
        "url": args.url,
        "provider": result["provider"],
        "markdown": md,
        "length": full_len,
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())