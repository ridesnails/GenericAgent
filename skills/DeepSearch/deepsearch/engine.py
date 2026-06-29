"""DeepSearch 编排引擎：scope → search → fetch → verify → synthesize。

调用策略：引擎通过 subprocess 调用已有的 scripts/*.py 脚本，
复用其 key rotation、provider 降级等能力，不重复造 HTTP 轮子。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import re
from pathlib import Path
from typing import Any

# scripts/ 目录路径 — 支持开发模式（相对路径）和已安装模式（import 定位）
_dev_scripts = Path(__file__).resolve().parents[1] / "scripts"
if _dev_scripts.is_dir():
    SCRIPTS_DIR = _dev_scripts
else:
    import importlib.util as _util
    _spec = _util.find_spec("scripts")
    if _spec and _spec.submodule_search_locations:
        SCRIPTS_DIR = Path(list(_spec.submodule_search_locations)[0])
    else:
        SCRIPTS_DIR = _dev_scripts  # fallback

# ---------- utility ----------

def _run_script(script: str, *args: str) -> dict:
    """Run a script in scripts/ and return parsed JSON from stdout."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script)] + list(args)
    timeout = 180 if script in ("dual_search.py", "grok_search.py") else 120
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(SCRIPTS_DIR),  # 保证 _http.py 的相对导入正确
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout: {script} {' '.join(args)}"}
    if r.returncode != 0:
        return {"error": r.stderr.strip() or f"exit code {r.returncode}"}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": r.stdout[:500]}


# ---------- 阶段 1：Scope ----------

def scope(question: str) -> dict:
    """将复杂问题分解为 3-7 个子查询 + 策略。

    调用 search_planning.py 生成搜索计划。
    """
    r = _run_script("search_planning.py", "--query", question)
    if "error" in r:
        # fallback：返回一个简单计划
        return {
            "core_question": question,
            "strategy": "broad_first",
            "sub_queries": [
                {"id": 1, "query": question, "depends_on": [], "rationale": "单一查询兜底"}
            ],
            "tool_plan": [
                {"step": 1, "tool": "dual_search", "query_id": 1, "parallel_with": []}
            ],
            "estimated_searches": 1,
        }
    return r


# ---------- 阶段 2：Search ----------

def _search_sub_query(tool: str, query: str) -> dict:
    """针对单个子查询执行搜索。"""
    q = query
    if tool == "tavily_search":
        return _run_script("tavily_search.py", "--query", q, "--depth", "basic", "--max-results", "8")
    if tool == "grok_search":
        return _run_script("grok_search.py", "--query", q)
    # default: dual_search
    return _run_script("dual_search.py", "--query", q, "--max-results", "8")


def search(sub_queries: list[dict], tool_plan: list[dict] | None = None) -> list[dict]:
    """对每个子查询执行搜索。返回搜索结果列表。

    通过 tool_plan 确定每个子查询的工具选择。
    简单的同步执行（后续可升级为 ThreadPoolExecutor 并行）。
    """
    # 建立 query_id → tool 映射（从 tool_plan 来）
    tool_map: dict = {}
    if tool_plan:
        for step in tool_plan:
            qid = step.get("query_id")
            tool = step.get("tool", "dual_search")
            if qid is not None:
                tool_map[qid] = tool

    results = []
    for sq in sub_queries:
        qid = sq.get("id")
        # 优先级: tool_plan 映射 > sub_query 自带的 tool > 默认 dual_search
        tool = tool_map.get(qid) or sq.get("tool", "dual_search")
        print(f"  [search] #{sq.get('id', '?')} [{tool}]: {sq['query'][:60]}...", file=sys.stderr)
        result = _search_sub_query(tool, sq["query"])
        result["query_id"] = qid
        result["query"] = sq["query"]
        result["tool_used"] = tool
        results.append(result)
    return results


# ---------- 阶段 3：Fetch ----------

def _collect_urls(search_results: list[dict], max_urls: int = 15) -> list[str]:
    """从搜索结果中收集 URLs，去重。"""
    seen: set[str] = set()
    urls: list[str] = []
    for sr in search_results:
        # 从 grok 结果拿
        for cite in sr.get("grok", {}).get("citations", []):
            u = cite.get("url", "")
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        # 从 tavily 结果拿
        for res in sr.get("tavily", {}).get("results", []):
            u = res.get("url", "")
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        if len(urls) >= max_urls:
            break
    return urls[:max_urls]


def _fetch_url(url: str) -> dict:
    """获取单个 URL 内容。"""
    r = _run_script("web_fetch.py", "--url", url, "--max-length", "8000")
    r["url"] = url
    return r


def fetch(urls: list[str]) -> list[dict]:
    """抓取 URLs 内容。"""
    pages = []
    for url in urls:
        print(f"  [fetch] {url[:70]}...", file=sys.stderr)
        page = _fetch_url(url)
        if "error" not in page and page.get("markdown"):
            pages.append(page)
    return pages


# ---------- 阶段 4：Verify ----------

_WHITELIST_DOMAINS = [
    "docs.", ".github.io", "github.com", "pypi.org", "npmjs.com",
    "arxiv.org", "wikipedia.org", "stackoverflow.com",
    "reddit.com", "news.ycombinator.com",
]
_BLACKLIST_KEYWORDS = ["seo", "content-farm", "advertorial", "sponsored"]


def _rate_source(url: str) -> str:
    """评级来源质量: high / medium / low。"""
    url_lower = url.lower()
    if any(d in url_lower for d in ["docs.", "pypi.org", "arxiv.org", "github.com"]):
        return "high"
    if any(d in url_lower for d in ["wikipedia.org", "stackoverflow.com", "reddit.com", "news.ycombinator.com"]):
        return "medium"
    return "low"


def verify(pages: list[dict], search_results: list[dict]) -> dict:
    """交叉验证 + 置信度标注。

    输出结构化的验证结果：声明列表（claim / confidence / sources）。
    """
    # 收集所有出现的 URL
    all_urls: list[str] = []
    for p in pages:
        if p.get("url"):
            all_urls.append(p["url"])
    for sr in search_results:
        for cite in sr.get("grok", {}).get("citations", []):
            u = cite.get("url", "")
            if u and u not in all_urls:
                all_urls.append(u)
        for res in sr.get("tavily", {}).get("results", []):
            u = res.get("url", "")
            if u and u not in all_urls:
                all_urls.append(u)

    # 来源评级
    sources = []
    for u in all_urls[:20]:
        sources.append({"url": u, "quality": _rate_source(u)})

    # 置信度估算
    high_count = sum(1 for s in sources if s["quality"] == "high")
    medium_count = sum(1 for s in sources if s["quality"] == "medium")
    total_count = len(sources)

    if total_count >= 3 and high_count >= 1:
        overall_confidence = "High"
    elif total_count >= 2:
        overall_confidence = "Medium"
    else:
        overall_confidence = "Low"

    # 从搜索结果中提取关键声明（简化实现）
    claims = []
    for sr in search_results:
        # 从 grok.content 提取关键句子
        content = sr.get("grok", {}).get("content", "")
        if content:
            # 按句号分割，取前 3 个句子作为声明
            sentences = [s.strip() for s in content.replace("\n", " ").split("。") if s.strip()][:3]
            for s in sentences:
                claims.append({
                    "claim": s[:120],
                    "confidence": "High" if sr.get("overlap_urls") else "Medium",
                    "sources": [cite["url"] for cite in sr.get("grok", {}).get("citations", [])[:3]],
                })

    return {
        "overall_confidence": overall_confidence,
        "sources": sources,
        "claims": claims[:10],
        "source_count": total_count,
        "high_quality_count": high_count,
    }


# ---------- 阶段 5：Synthesize ----------

def synthesize(
    question: str,
    search_results: list[dict],
    pages: list[dict],
    verification: dict,
) -> dict:
    """把各阶段结果合成为最终报告。"""
    # 从双引擎取答案摘要
    grok_contents = []
    tavily_answers = []
    for sr in search_results:
        grok_contents.append(sr.get("grok", {}).get("content", ""))
        tavily_answers.append(sr.get("tavily", {}).get("answer", ""))

    # 构建最终报告
    report = {
        "question": question,
        "summary": "",
        "findings": [],
        "evidence_grading": verification.get("overall_confidence", "Low"),
        "sources": [],
        "caveats": [],
        "open_questions": [],
        "_meta": {
            "elapsed_s": 0,
            "models_used": [],
        },
    }

    # 填充来源
    seen_urls: set[str] = set()
    for s in verification.get("sources", []):
        u = s["url"]
        if u not in seen_urls:
            seen_urls.add(u)
            report["sources"].append({"url": u, "quality": s["quality"]})

    # 填充发现
    for claim in verification.get("claims", []):
        report["findings"].append({
            "statement": claim["claim"],
            "confidence": claim["confidence"],
            "sources": claim["sources"],
        })

    # 填充摘要
    summary_parts = []
    for gc in grok_contents:
        if gc:
            first_line = gc.strip().split("\n")[0][:200]
            summary_parts.append(first_line)
    report["summary"] = "; ".join(summary_parts[:3]) or f"已完成对「{question}」的深度调研"

    # 注意事项
    if verification.get("source_count", 0) < 2:
        report["caveats"].append("来源不足 2 个，建议降低置信度")
    if verification.get("overall_confidence") == "Low":
        report["caveats"].append("整体置信度低，建议手动核实")

    return report


# ---------- 完整流水线 ----------

def deep_search(
    question: str,
    mode: str = "standard",
    max_results: int = 8,
) -> dict:
    """完整深度搜索流水线。

    Args:
        question: 搜索问题
        mode: "standard"（5 阶段完整流程）或 "quick"（仅搜索阶段）
        max_results: 每个引擎最大结果数
    """
    t0 = time.time()
    print(f"[DeepSearch] 开始: {question}", file=sys.stderr)

    # 阶段 1：Scope
    print("[DeepSearch] 阶段 1/5: 规划...", file=sys.stderr)
    plan = scope(question)

    # quick mode = 只做搜索，不做 fetch/verify/synthesize
    if mode == "quick":
        sub_queries = plan.get("sub_queries", [{"id": 1, "query": question}])
        tool_plan = plan.get("tool_plan", [])
        print("[DeepSearch] 阶段 2/5: 快速搜索...", file=sys.stderr)
        search_results = search(sub_queries, tool_plan)
        elapsed = round(time.time() - t0, 2)
        return {
            "question": question,
            "mode": "quick",
            "plan": plan,
            "search_results": search_results,
            "elapsed_s": elapsed,
        }

    # 标准流程
    # 阶段 2：Search
    print("[DeepSearch] 阶段 2/5: 搜索...", file=sys.stderr)
    sub_queries = plan.get("sub_queries", [{"id": 1, "query": question}])
    tool_plan = plan.get("tool_plan", [])
    search_results = search(sub_queries, tool_plan)

    # 阶段 3：Fetch
    print("[DeepSearch] 阶段 3/5: 抓取...", file=sys.stderr)
    urls = _collect_urls(search_results)
    pages = fetch(urls)

    # 阶段 4：Verify
    print("[DeepSearch] 阶段 4/5: 验证...", file=sys.stderr)
    verification = verify(pages, search_results)

    # 阶段 5：Synthesize
    print("[DeepSearch] 阶段 5/5: 合成报告...", file=sys.stderr)
    report = synthesize(question, search_results, pages, verification)

    elapsed = round(time.time() - t0, 2)
    report["_meta"]["elapsed_s"] = elapsed
    return report
