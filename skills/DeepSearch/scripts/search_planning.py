#!/usr/bin/env python3
"""Structured search planner: converts a complex question into a search plan JSON.

Invokes Grok to decompose a Level-3 query into intent / sub-queries / strategy /
tool mapping. Run this before launching many searches - it prevents duplicate
work and surfaces verification dependencies.

Usage:
    python search_planning.py --query "2026 \u5e74\u4e3b\u6d41\u5411\u91cf\u6570\u636e\u5e93\u5b8c\u6574\u5bf9\u6bd4"

Output: JSON plan with intent, sub_queries[], strategy, tool_plan, _meta.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from _http import dump_json, openai_chat, strip_think

PROMPT = """You are a search planner. Given a user's research question, produce
a structured plan a search agent can execute directly.

CRITICAL OUTPUT CONTRACT:
- Output ONLY one valid JSON object.
- Do NOT include Markdown fences, prose, explanations, headings, or bullet text outside JSON.
- The first non-whitespace character MUST be `{` and the last non-whitespace character MUST be `}`.
- All strings must be double-quoted JSON strings; no trailing commas.

Schema:

{
  "intent": {
    "core_question": "one-sentence reformulation",
    "query_type": "factual|comparative|exploratory|analytical",
    "time_sensitivity": "realtime|recent|historical|timeless",
    "terms_to_verify": ["term1", "term2"]
  },
  "sub_queries": [
    {"id": 1, "query": "...", "depends_on": [], "rationale": "..."},
    {"id": 2, "query": "...", "depends_on": [1], "rationale": "..."}
  ],
  "strategy": "broad_first|narrow_first|targeted",
  "tool_plan": [
    {"step": 1, "tool": "dual_search|grok_search|tavily_search|web_fetch|web_map",
     "query_id": 1, "parallel_with": [], "notes": "..."}
  ],
  "estimated_searches": 5,
  "expected_sources_per_query": 3
}

Rules:
- 3-7 sub_queries, non-overlapping.
- Sub-queries that verify domain terms go first (depends_on: []).
- Prefer dual_search for cross-validation; tavily_search for structured news;
  grok_search for synthesis; web_fetch for known URLs; web_map for exploration.
- Mark parallelizable steps with shared `parallel_with` list.
"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```\s*$", re.M)


def _extract_json_object(text: str) -> str:
    """Return a parseable JSON object string from model output.

    Models sometimes wrap the object in prose or fenced blocks despite the
    prompt. This scans for the first balanced top-level JSON object while
    respecting quoted strings and escapes.
    """
    text = _FENCE_RE.sub("", text).strip()
    if not text:
        return text
    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    if start < 0:
        return text

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:].strip()


def _parse_plan(content: str) -> dict:
    content, _ = strip_think(content)
    content = _extract_json_object(content)
    return json.loads(content)


def _planner_messages(query: str) -> list[dict]:
    return [
        {"role": "system", "content": PROMPT},
        {
            "role": "user",
            "content": (
                "Create the JSON search plan for the research question delimited below.\n"
                "Do not answer the research question. Do not perform the comparison.\n"
                "Return only the JSON object matching the schema.\n\n"
                "<research_question>\n"
                f"{query}\n"
                "</research_question>"
            ),
        },
    ]


def _repair_messages(bad_output: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You repair malformed planner output. Return ONLY a valid JSON object "
                "matching the search planner schema from the prior instruction. No prose."
            ),
        },
        {
            "role": "user",
            "content": (
                "Convert this planner output into strict JSON only. If it answered the "
                "question instead of planning, infer a valid search plan from it.\n\n"
                "<bad_output>\n"
                f"{bad_output[:6000]}\n"
                "</bad_output>"
            ),
        },
    ]


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a structured search plan")
    p.add_argument("--query", required=True)
    p.add_argument("--model", default=None)
    args = p.parse_args()

    try:
        result = openai_chat(
            _planner_messages(args.query),
            model=args.model,
            temperature=0,
            max_tokens=1600,
            timeout=120,
        )
    except Exception as e:
        dump_json({"error": str(e), "query": args.query})
        return 1

    try:
        plan = _parse_plan(result["content"])
    except json.JSONDecodeError as first_error:
        raw = result.get("content", "")
        try:
            repair = openai_chat(
                _repair_messages(raw),
                model=args.model,
                temperature=0,
                max_tokens=1600,
                timeout=120,
            )
            plan = _parse_plan(repair["content"])
            result = {
                **result,
                "elapsed_s": round(result.get("elapsed_s", 0) + repair.get("elapsed_s", 0), 2),
                "usage": {"initial": result.get("usage", {}), "repair": repair.get("usage", {})},
                "repaired": True,
            }
        except Exception as e:
            dump_json({
                "error": "planner returned non-JSON",
                "detail": str(first_error),
                "repair_detail": str(e),
                "raw": _extract_json_object(raw)[:1500],
            })
            return 1

    plan["_meta"] = {
        "query": args.query,
        "model": result["model"],
        "elapsed_s": result["elapsed_s"],
        "usage": result.get("usage", {}),
        "repaired": result.get("repaired", False),
    }
    dump_json(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())