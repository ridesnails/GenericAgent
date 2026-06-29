"""DeepSearch CLI — 终端入口。

用法:
    deepsearch --query "..."                     # 默认 standard 模式深度调研
    deepsearch --query "..." --mode quick        # L1 快速双引擎搜索
    deepsearch fetch --url "..."                 # 抓取单个页面
    deepsearch serve                             # 启动 MCP Server
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口。

    Returns: exit code (0 = success).
    """
    import argparse

    p = argparse.ArgumentParser(
        prog="deepsearch",
        description="多源交叉验证深度搜索引擎 — 双引擎（Grok + Tavily）+ 证据约束",
    )
    p.add_argument("--query", "-q", help="搜索问题（作为顶层参数时自动走 search 模式）")
    p.add_argument("--mode", choices=["standard", "quick"], default=None,
                   help="搜索模式: standard=完整5阶段, quick=仅双引擎搜索")
    p.add_argument("--max-results", type=int, default=8, help="每引擎最大结果数")
    p.add_argument("--pretty", action="store_true", help="格式化输出 JSON")
    sub = p.add_subparsers(dest="command", help="子命令")

    # search 子命令
    search_p = sub.add_parser("search", help="执行深度搜索（也可用顶层 --query）")
    search_p.add_argument("--query", "-q", required=True, help="搜索问题")
    search_p.add_argument("--mode", choices=["standard", "quick"], default="standard",
                          help="搜索模式: standard=完整5阶段, quick=仅双引擎搜索")
    search_p.add_argument("--max-results", type=int, default=8, help="每引擎最大结果数")
    search_p.add_argument("--pretty", action="store_true", help="格式化输出 JSON")

    # fetch 子命令
    fetch_p = sub.add_parser("fetch", help="抓取单个页面")
    fetch_p.add_argument("--url", required=True, help="目标 URL")
    fetch_p.add_argument("--force-firecrawl", action="store_true",
                         help="跳过 Tavily 直走 FireCrawl")
    fetch_p.add_argument("--pretty", action="store_true", help="格式化输出 JSON")

    # serve 子命令
    serve_p = sub.add_parser("serve", help="启动 MCP Server")
    serve_p.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio",
                         help="传输模式 (默认 stdio)")
    serve_p.add_argument("--port", type=int, default=8000, help="HTTP 传输端口")

    args = p.parse_args(argv)

    try:
        # 顶层 --query 自动走 search 模式
        if args.command is None and args.query:
            args.command = "search"
        if args.command == "fetch":
            return _cmd_fetch(args)
        if args.command == "serve":
            return _cmd_serve(args)

        # search 模式（包括顶层 --query）
        mode = args.mode or "standard"
        return _cmd_search(args, mode=mode)

    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1


def _cmd_search(args, mode: str | None = None) -> int:
    from deepsearch.engine import deep_search

    result = deep_search(
        question=args.query,
        mode=mode or args.mode or "standard",
        max_results=args.max_results,
    )
    _print_result(result, args.pretty)
    return 0


def _cmd_fetch(args) -> int:
    from deepsearch.engine import _run_script

    extra = ["--force-firecrawl"] if args.force_firecrawl else []
    result = _run_script("web_fetch.py", "--url", args.url, *extra)
    if "error" in result:
        print(json.dumps(result, ensure_ascii=False))
        return 1
    _print_result(result, args.pretty)
    return 0


def _cmd_serve(args) -> int:
    from deepsearch.server import serve
    serve(transport=args.transport, port=args.port)
    return 0


def _print_result(data: dict, pretty: bool) -> None:
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
