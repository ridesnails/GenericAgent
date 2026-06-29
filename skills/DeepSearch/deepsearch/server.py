"""DeepSearch MCP Server — 启动入口。"""

from __future__ import annotations

from deepsearch.tools import mcp


def serve(transport: str = "stdio", port: int = 8000) -> None:
    """启动 MCP Server。

    Args:
        transport: "stdio"（默认，用于 Claude Code 等本地集成）
                   "streamable-http"（HTTP 模式，用于远程集成）
        port: HTTP 传输模式下的监听端口
    """
    if transport == "streamable-http":
        import uvicorn
        uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=port)
    else:
        mcp.run(transport="stdio")
