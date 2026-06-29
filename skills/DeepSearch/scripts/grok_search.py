#!/usr/bin/env python3
"""Grok AI search via GROK2API (OpenAI-compatible chat completion).

Usage:
    python grok_search.py --query "FastAPI 0.200 release date"
    python grok_search.py --query "..." --model grok-4.1-fast --platform "GitHub"

Output: JSON {content, reasoning, model, usage, citations[], sources_count, elapsed_s}.
"""
from __future__ import annotations

import argparse
import re
import sys

from _http import dump_json, openai_chat, strip_think

_URL_RE = re.compile(r"https?://[^\s)\]]+")


def extract_citations(text: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for url in _URL_RE.findall(text):
        url = url.rstrip(".,;:!?\"'")
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "title": ""})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Grok web search via GROK2API")
    p.add_argument("--query", required=True)
    p.add_argument("--model", default=None, help="Override default model (e.g. grok-4.1-fast)")
    p.add_argument("--platform", default="", help="Optional source-platform hint passed to model")
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--max-tokens", type=int, default=4096)
    args = p.parse_args()

    sys_prompt = (
        "You are a web research assistant. Answer factually with explicit URL citations. "
        "Cite each non-trivial claim with a markdown link. If unsure, say so."
    )
    user = f"Question: {args.query}"
    if args.platform:
        user += f"\nPrefer sources from: {args.platform}"

    try:
        result = openai_chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
    except Exception as e:
        dump_json({"error": str(e), "query": args.query})
        return 1

    clean, think = strip_think(result["content"])
    citations = extract_citations(clean)
    dump_json({
        "query": args.query,
        "content": clean,
        "reasoning": result.get("reasoning") or think,
        "model": result["model"],
        "usage": result.get("usage", {}),
        "citations": citations,
        "sources_count": len(citations),
        "elapsed_s": result["elapsed_s"],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())