#!/usr/bin/env python3
"""Tavily structured web search.

Usage:
    python tavily_search.py --query "Python 3.14 release notes"
    python tavily_search.py --query "..." --depth advanced --topic news --time-range week

Output: JSON {query, answer, results[]{title,url,content,score,published_date}, results_count, elapsed_s}.
"""
from __future__ import annotations

import argparse
import sys
import time

from _http import dump_json, tavily_post


def main() -> int:
    p = argparse.ArgumentParser(description="Tavily web search")
    p.add_argument("--query", required=True)
    p.add_argument("--depth", choices=["basic", "advanced"], default="basic")
    p.add_argument("--topic", choices=["general", "news"], default="general")
    p.add_argument("--max-results", type=int, default=8)
    p.add_argument("--time-range", choices=["day", "week", "month", "year"], default=None)
    p.add_argument("--include-domains", nargs="*", default=None)
    p.add_argument("--exclude-domains", nargs="*", default=None)
    args = p.parse_args()

    body = {
        "query": args.query,
        "search_depth": args.depth,
        "topic": args.topic,
        "max_results": args.max_results,
        "include_answer": True,
    }
    if args.time_range:
        body["time_range"] = args.time_range
    if args.include_domains:
        body["include_domains"] = args.include_domains
    if args.exclude_domains:
        body["exclude_domains"] = args.exclude_domains

    t0 = time.time()
    try:
        data = tavily_post("search", body)
    except Exception as e:
        dump_json({"error": str(e), "query": args.query})
        return 1
    elapsed = round(time.time() - t0, 2)

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score"),
            "published_date": r.get("published_date"),
        }
        for r in data.get("results", [])
    ]
    dump_json({
        "query": args.query,
        "answer": data.get("answer"),
        "results": results,
        "results_count": len(results),
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())