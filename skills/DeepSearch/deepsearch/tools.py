"""DeepSearch MCP Tools — 基于 FastMCP 暴露的 AI agent tools。"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP

from deepsearch.engine import deep_search, _run_script

# MCP Server 实例
mcp = FastMCP(
    "deepsearch",
    instructions="""
多源交叉验证深度搜索引擎 — 双引擎（Grok + Tavily）+ 证据约束。

提供三个工具：
1. deep_search — 完整 5 阶段深度调研（scope → search → fetch → verify → synthesize）
2. quick_search — L1 快速双引擎搜索（仅 scope + search）
3. fetch_page — 获取指定 URL 的正文内容

所有结果均遵循 DeepSearch SOP 的证据标准：
- 置信度 High（≥2 独立来源）/ Medium（有分歧）/ Low（单源）
- 所有引用附带真实 URL
- 来源质量评级: high（官方文档）/ medium（社区）/ low（含 SEO 农场风险）
""",
)


@mcp.tool(
    name="deep_search",
    description="""完整深度调研：将问题拆解为 3-7 个子查询 → 双引擎并行搜索 →
抓取关键来源 → 交叉验证 → 合成带置信度标注和引用来源的最终报告。
适用于复杂问题、多源交叉核实场景。""",
)
async def deep_search_tool(
    query: Annotated[str, "搜索问题，越具体越好，如：'2026 年 Claude Code 在 agentic coding 方面有哪些新功能？'"],
) -> str:
    """完整 5 阶段深度调研。"""
    import json
    result = deep_search(question=query, mode="standard")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool(
    name="quick_search",
    description="""快速双引擎搜索：Grok + Tavily 并行，返回双引擎结果和 URL 重叠率。
适用于单一事实查证、快速概览。通过 overlap_urls 判断双引擎一致性。""",
)
async def quick_search_tool(
    query: Annotated[str, "搜索查询，简明确切，如：'FastAPI 最新稳定版本'"],
) -> str:
    """快速双引擎搜索（L1 级别）。"""
    import json
    result = deep_search(question=query, mode="quick")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool(
    name="fetch_page",
    description="""获取单个网页正文内容（Markdown 格式）。
使用 Tavily Extract → FireCrawl Scrape 两级降级链。
适用于需要查看特定 URL 原文的场景。""",
)
async def fetch_page_tool(
    url: Annotated[str, "目标网页的完整 URL，如 'https://docs.python.org/3/whatsnew/3.14.html'"],
) -> str:
    """获取指定 URL 的 Markdown 内容。"""
    import json
    result = _run_script("web_fetch.py", "--url", url)
    return json.dumps(result, ensure_ascii=False, indent=2)
