#!/usr/bin/env python3
"""Dual-engine search: runs Grok + Tavily in parallel threads, merges results.

Rationale: cross-validate a single query with two independent engines. When
both agree on facts and overlap on sources, confidence is high; when they
diverge, the caller should drill deeper before stating anything as fact.

Implementation note: previously spawned two python subprocesses (~600ms cold
overhead each on Windows). Now both calls share this process and the pooled
HTTP sessions in `_http.py`, so latency = max(grok, tavily) instead of
max(grok, tavily) + 2 * spawn cost.

Usage:
    python dual_search.py --query "grok-4.1 vs claude-sonnet-4-6 coding benchmark 2026"

Output: JSON {query, grok{...}, tavily{...}, overlap_urls[], unique_to_*, confidence_hint, elapsed_s}.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import time

from _http import dump_json, log, openai_chat, strip_think, tavily_post

_URL_RE = re.compile(r"https?://[^\s)\]]+")


def _grok(query: str, model: str | None) -> dict:
    sys_prompt = (
        "You are a web research assistant. Answer factually with explicit URL "
        "citations. Cite each non-trivial claim with a markdown link."
    )
    try:
        r = openai_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Question: {query}"}],
            model=model,
        )
    except Exception as e:
        return {"error": str(e)}
    clean, think = strip_think(r["content"])
    seen: set[str] = set()
    citations: list[dict] = []
    for url in _URL_RE.findall(clean):
        url = url.rstrip(".,;:!?\"'")
        if url not in seen:
            seen.add(url)
            citations.append({"url": url, "title": ""})
    return {
        "content": clean,
        "reasoning": r.get("reasoning") or think,
        "model": r["model"],
        "usage": r.get("usage", {}),
        "citations": citations,
        "sources_count": len(citations),
        "elapsed_s": r["elapsed_s"],
    }


def _tavily(query: str, depth: str, max_results: int) -> dict:
    body = {
        "query": query,
        "search_depth": depth,
        "topic": "general",
        "max_results": max_results,
        "include_answer": True,
    }
    t0 = time.time()
    try:
        data = tavily_post("search", body)
    except Exception as e:
        return {"error": str(e)}
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
    return {
        "answer": data.get("answer"),
        "results": results,
        "results_count": len(results),
        "elapsed_s": elapsed,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Parallel Grok + Tavily cross-validation search")
    p.add_argument("--query", required=True)
    p.add_argument("--depth", choices=["basic", "advanced"], default="basic")
    p.add_argument("--max-results", type=int, default=8)
    p.add_argument("--model", default=None, help="Override Grok model")
    args = p.parse_args()

    log("dispatching grok + tavily in parallel (in-process)")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fg = ex.submit(_grok, args.query, args.model)
        ft = ex.submit(_tavily, args.query, args.depth, args.max_results)
        grok = fg.result()
        tavily = ft.result()
    elapsed = round(time.time() - t0, 2)

    grok_urls = {c["url"] for c in grok.get("citations", []) if c.get("url")}
    tavily_urls = {r["url"] for r in tavily.get("results", []) if r.get("url")}
    overlap = sorted(grok_urls & tavily_urls)

    dump_json({
        "query": args.query,
        "grok": grok,
        "tavily": tavily,
        "overlap_urls": overlap,
        "unique_to_grok": sorted(grok_urls - tavily_urls),
        "unique_to_tavily": sorted(tavily_urls - grok_urls),
        "confidence_hint": (
            "high" if overlap else ("medium" if (grok_urls and tavily_urls) else "low")
        ),
        "elapsed_s": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())