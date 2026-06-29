#!/usr/bin/env python3
"""
CC-Style Proxy for GenericAgent
GA → Proxy(:5678) → cc-switch(:15721) → Upstream API

按 SOP 实现 Claude Code 伪装层，包含 headers、body、CCH、工具名映射。
"""

import os
import sys
import json
import uuid
import hashlib
import platform
import subprocess
import time
from datetime import datetime, timezone

from flask import Flask, request, Response
import requests

# ===================== 配置 =====================
PORT = int(os.environ.get("PORT", "5678"))
UPSTREAM_BASE = os.environ.get("UPSTREAM_BASE", "http://127.0.0.1:15721")
MODEL_OVERRIDE = os.environ.get("MODEL_OVERRIDE", "").strip()
MAX_TOKENS_OVERRIDE = os.environ.get("MAX_TOKENS_OVERRIDE", "").strip()
MODELS_BASE = os.environ.get("MODELS_BASE", UPSTREAM_BASE).rstrip("/")
DRY_RUN = os.environ.get("DRY_RUN", "0").lower() in ("1", "true", "yes", "on")
CAPTURE_DIR = os.environ.get("CAPTURE_DIR", "captures")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CCH_SEED = 0x6E52736AC806831E

# 设备ID：优先用 ~/.config/claude/.metadata.json 的 device_id，否则生成
_DEVICE_ID = None

def _get_device_id() -> str:
    global _DEVICE_ID
    if _DEVICE_ID is not None:
        return _DEVICE_ID
    config_paths = [
        os.path.expanduser("~/.config/claude/.metadata.json"),
        os.path.expanduser("~/.claude/.credentials.json"),
    ]
    for p in config_paths:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    data = json.load(f)
                    # 尝试多个可能的键名
                    for key in ["device_id", "deviceId"]:
                        if key in data:
                            _DEVICE_ID = data[key]
                            return _DEVICE_ID
            except (json.JSONDecodeError, OSError):
                pass
    _DEVICE_ID = str(uuid.uuid4())
    return _DEVICE_ID

# 会话ID：进程启动时生成一次，进程内复用
SESSION_ID = str(uuid.uuid4())

# CC 版本
def _get_cc_version() -> str:
    """尝试通过 claude --version 获取版本。"""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            ver = result.stdout.strip()
            if ver:
                return ver
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "2.3.2"

CC_VERSION = _get_cc_version()

# ===================== 工具名映射 =====================
with open(os.path.join(SCRIPT_DIR, "tool_name_mapping.json"), "r") as f:
    OC_TO_CC = json.load(f)

# CC → OC 反向映射（必须唯一）
CC_TO_OC = {v: k for k, v in OC_TO_CC.items()}

# 历史旧名回程兜底：防止模型输出了旧名
LEGACY_TO_OC = {
    "exec": "code_run",
    "read": "file_read",
    "edit": "file_patch",
    "write": "file_write",
    "sessions_send": "ask_user",
    "sessions_run": "code_run",
    "sessions_list": "file_read",
    "sessions_history": "file_read",
}
CC_TO_OC.update(LEGACY_TO_OC)

# =============== 参数适配器 ===============
CC_PARAM_ADAPTERS = {
    "Bash": lambda params: {
        "type": "powershell",
        "cwd": "./",
        **{k: v for k, v in params.items() if k != "command"},
        **({"script": params["command"]} if "command" in params else {})
    },
    "Read": lambda params: {
        **{k: v for k, v in params.items()
           if k not in ("file_path", "offset", "limit")},
        **({"path": params["file_path"]} if "file_path" in params else {}),
        **({"start": params["offset"]} if "offset" in params else {}),
        **({"count": params["limit"]} if "limit" in params else {}),
    },
    "Edit": lambda params: {
        **{k: v for k, v in params.items()
           if k not in ("file_path", "old_string", "new_string")},
        **({"path": params["file_path"]} if "file_path" in params else {}),
        **({"old_content": params["old_string"]} if "old_string" in params else {}),
        **({"new_content": params["new_string"]} if "new_string" in params else {}),
    },
    "Write": lambda params: {
        **{k: v for k, v in params.items()
           if k not in ("file_path", "content")},
        **({"path": params["file_path"]} if "file_path" in params else {}),
        **({"new_content": params["content"]} if "content" in params else {}),
    },
    "AskUserQuestion": lambda params: {
        **{k: v for k, v in params.items() if k != "question"},
        **({"question": params["question"]} if "question" in params else {}),
    },
    "TodoWrite": lambda params: {
        **{k: v for k, v in params.items() if k != "todos"},
        **({"todos": params["todos"]} if "todos" in params else {}),
    },
    "TaskUpdate": lambda params: {
        **{k: v for k, v in params.items() if k != "content"},
        **({"content": params["content"]} if "content" in params else {}),
    },
    "WebSearch": lambda params: {
        **{k: v for k, v in params.items() if k != "query"},
        **({"query": params["query"]} if "query" in params else {}),
    },
    "WebFetch": lambda params: {
        **{k: v for k, v in params.items() if k != "url"},
        **({"url": params["url"]} if "url" in params else {}),
    },
}

# =============== OC → CC 参数适配（反向）================
OC_PARAM_ADAPTERS = {
    "code_run": lambda params: {
        **{k: v for k, v in params.items() if k != "script"},
        **({"command": params["script"]} if "script" in params else {}),
    },
    "file_read": lambda params: {
        **{k: v for k, v in params.items()
           if k not in ("path", "start", "count")},
        **({"file_path": params["path"]} if "path" in params else {}),
        **({"offset": params["start"]} if "start" in params else {}),
        **({"limit": params["count"]} if "count" in params else {}),
    },
    "file_patch": lambda params: {
        **{k: v for k, v in params.items()
           if k not in ("path", "old_content", "new_content")},
        **({"file_path": params["path"]} if "path" in params else {}),
        **({"old_string": params["old_content"]} if "old_content" in params else {}),
        **({"new_string": params["new_content"]} if "new_content" in params else {}),
    },
    "file_write": lambda params: {
        **{k: v for k, v in params.items()
           if k not in ("path", "new_content")},
        **({"file_path": params["path"]} if "path" in params else {}),
        **({"content": params["new_content"]} if "new_content" in params else {}),
    },
    "ask_user": lambda params: {
        **{k: v for k, v in params.items()},
    },
    "update_working_checkpoint": lambda params: {
        **{k: v for k, v in params.items()},
    },
    "start_long_term_update": lambda params: {
        **{k: v for k, v in params.items()},
    },
    "web_scan": lambda params: {
        **{k: v for k, v in params.items()},
    },
    "web_execute_js": lambda params: {
        **{k: v for k, v in params.items()},
    },
}

# =============== System blocks ===============
# SOP: 读取真 CC capture 中的 system[0:2]，拼接 GA system[2]（附加GA SP）
# 由于上下文限制，这里用空字符串占位，后续可替换为真 capture
CC_DEFAULT_SYSTEM_BLOCKS = [
    {"type": "text", "text": ""},
    {"type": "text", "text": ""},
    {"type": "text", "text": ""},
]


def load_latest_cc_system_blocks():
    """从 captures/ 加载最新的 CC system blocks"""
    import glob
    caps = glob.glob(os.path.join(SCRIPT_DIR, "captures", "*.json"))
    if not caps:
        # 尝试上一级
        caps = glob.glob(os.path.join("..", "captures", "*.json"))
    if not caps:
        return CC_DEFAULT_SYSTEM_BLOCKS.copy()
    caps.sort(key=os.path.getmtime, reverse=True)
    for cap_path in caps[:3]:
        try:
            with open(cap_path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict) and "body" in data:
                    body = data["body"]
                elif isinstance(data, dict) and "request" in data:
                    body = data["request"].get("body", data["request"])
                else:
                    body = data
                if isinstance(body, dict) and "system" in body:
                    sys_blocks = body["system"]
                    if isinstance(sys_blocks, list) and len(sys_blocks) >= 3:
                        blocks = []
                        for blk in sys_blocks[:3]:
                            if isinstance(blk, dict) and "text" in blk:
                                blocks.append({"type": "text", "text": blk["text"]})
                            elif isinstance(blk, dict) and "content" in blk:
                                blocks.append({"type": "text", "text": blk["content"]})
                            elif isinstance(blk, str):
                                blocks.append({"type": "text", "text": blk})
                        if len(blocks) == 3:
                            return blocks
        except (json.JSONDecodeError, OSError):
            continue
    return CC_DEFAULT_SYSTEM_BLOCKS.copy()


CC_SYSTEM_BLOCKS = load_latest_cc_system_blocks()


def compute_cch(body_bytes: bytes) -> str:
    """
    计算 x-claude-code-client-sha256 (CCH)。
    ALGO: 基于 SOP 关键提示与 seed 派生实现。
    最终 bytes 格式：seed(LE u64) + body_bytes → SHA-256 → hex
    """
    seed_bytes = CCH_SEED.to_bytes(8, "little")
    h = hashlib.sha256()
    h.update(seed_bytes)
    h.update(body_bytes)
    return h.hexdigest()


# =============== Flask App ===============
app = Flask(__name__)


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def build_headers() -> dict:
    """构建 CC 风格的请求头"""
    cc_ver = CC_VERSION
    device = _get_device_id()
    session = SESSION_ID
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system in ("darwin", "macos", "mac"):
        os_name = "macos"
    elif system == "linux":
        os_name = "linux"
    elif system == "windows":
        os_name = "windows"
    else:
        os_name = system or "linux"
    arch = machine if machine else "arm64"
    if "x86_64" in arch or "amd64" in arch:
        arch = "x64"
    elif "arm64" in arch or "aarch64" in arch:
        arch = "arm64"

    headers = {
        "user-agent": f"claude-cli/{cc_ver} ({os_name}; {arch})",
        "x-app": "cli",
        "anthropic-dangerous-direct-browser-access": "true",
        "anthropic-version": "2023-06-01",
        "X-Stainless-Lang": "js",
        "X-Stainless-OS": os_name,
        "X-Stainless-Arch": arch,
        "X-Stainless-Runtime": "node",
        "X-Stainless-Package-Version": f"anthropic@{cc_ver}",
        "X-Stainless-Runtime-Version": "v20.18.1",
        "anthropic-beta": (
            "claude-code-20250219,"
            "oauth-2025-04-20,"
            "interleaved-thinking-2025-05-14,"
            "context-management-2025-06-27,"
            "prompt-caching-scope-2026-01-05,"
            "effort-2025-11-24"
        ),
        "X-Claude-Code-Session-Id": session,
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "Accept-Encoding": "gzip, deflate, br",
    }
    return headers


def sync_metadata_session(body: dict, session_id: str) -> None:
    """同步 metadata.user_id.session_id 到 header session"""
    if "metadata" not in body:
        body["metadata"] = {}
    user_id = body["metadata"].get("user_id")
    if isinstance(user_id, str):
        try:
            user_id = json.loads(user_id)
        except json.JSONDecodeError:
            user_id = {}
    if not isinstance(user_id, dict):
        user_id = {}
    user_id["session_id"] = session_id
    body["metadata"]["user_id"] = user_id


def inject_system_and_cch(body: dict) -> dict:
    """
    注入 system blocks 并设置顶层参数、CCH。
    返回修改后的 body 副本（不修改入站原对象）。
    """
    import copy
    body = copy.deepcopy(body)

    # 1. 归一化顶层参数。默认保留 GA/mykey.py 入站值，只在环境变量显式指定时覆盖。
    if MODEL_OVERRIDE:
        body["model"] = MODEL_OVERRIDE
    if MAX_TOKENS_OVERRIDE:
        try:
            body["max_tokens"] = int(MAX_TOKENS_OVERRIDE)
        except ValueError:
            log(f"Invalid MAX_TOKENS_OVERRIDE={MAX_TOKENS_OVERRIDE!r}, ignored")
    body.setdefault("thinking", {"type": "adaptive"})
    body.setdefault("context_management", {
        "edits": [{"type": "clear_thinking_20251015", "keep": "all"}]
    })
    body.setdefault("output_config", {"effort": "max"})

    # 2. system blocks
    # 从 inbound body 提取 GA system prompt
    ga_system_text = ""
    if "system" in body:
        orig_system = body["system"]
        if isinstance(orig_system, str):
            ga_system_text = orig_system
            body["system"] = []
        elif isinstance(orig_system, list) and len(orig_system) > 0:
            texts = []
            for entry in orig_system:
                if isinstance(entry, dict):
                    t = entry.get("text", "")
                    if t:
                        texts.append(t)
                elif isinstance(entry, str):
                    texts.append(entry)
            ga_system_text = "\n\n".join(texts)
            body["system"] = []
        else:
            body["system"] = []
    else:
        body["system"] = []

    # 构建三段 system
    blocks = [
        {"type": "text", "text": CC_SYSTEM_BLOCKS[0]["text"]},
        {"type": "text", "text": CC_SYSTEM_BLOCKS[1]["text"]},
    ]
    # system[2] = CC system[2] 前缀 + GA system text
    s2 = CC_SYSTEM_BLOCKS[2]["text"]
    if ga_system_text:
        if s2 and not s2.endswith("\n"):
            s2 += "\n\n"
        s2 += ga_system_text
    blocks.append({"type": "text", "text": s2})

    body["system"] = blocks

    # 3. tools 映射：OC name → CC name
    tools = body.get("tools", [])
    if isinstance(tools, list):
        for tool in tools:
            # 支持两种 schema 形态
            name = None
            if isinstance(tool, dict):
                if "name" in tool:
                    name = tool["name"]
                elif "function" in tool and isinstance(tool["function"], dict) and "name" in tool["function"]:
                    name = tool["function"]["name"]
                if name and name in OC_TO_CC:
                    cc_name = OC_TO_CC[name]
                    # 提取描述（从任意层级）
                    desc = None
                    if "description" in tool:
                        desc = tool["description"]
                    elif "function" in tool and isinstance(tool["function"], dict):
                        desc = tool["function"].get("description")
                    # 适配参数 schema：GA 的是 "parameters"，CC 要的是 "input_schema"
                    params = {}
                    if "function" in tool and isinstance(tool["function"], dict):
                        params = tool["function"].get("parameters", tool["function"].get("input_schema", {}))
                    else:
                        params = tool.get("parameters", tool.get("input_schema", {}))
                    if name in OC_PARAM_ADAPTERS:
                        params = OC_PARAM_ADAPTERS[name](params)
                    # 重建 CC 风格自定义工具结构
                    cc_tool = {
                        "type": "custom",
                        "name": cc_name,
                        "input_schema": params,
                    }
                    if desc:
                        cc_tool["description"] = desc
                    # 清空原tool并用cc_tool重建
                    tool.clear()
                    tool.update(cc_tool)

    # 4. metadata session 同步
    sync_metadata_session(body, SESSION_ID)

    # metadata.user_id.device_id
    body["metadata"]["user_id"]["device_id"] = _get_device_id()

    # account_uuid 保留入站原值
    if "account_uuid" not in body.get("metadata", {}).get("user_id", {}):
        body["metadata"]["user_id"]["account_uuid"] = "00000000-0000-0000-0000-000000000000"

    # 5. 计算 CCH
    body_bytes = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    cch = compute_cch(body_bytes)
    body["_cch"] = cch  # 用于 headers，之后会移到外面

    return body


def remap_response(response_text: str) -> str:
    """
    回程映射：CC tool name → GA tool name，参数恢复。
    处理普通 JSON 和 SSE chunk 两种形态。
    """
    if not response_text:
        return response_text
    try:
        data = json.loads(response_text)
        if "content" in data and isinstance(data["content"], list):
            for block in data["content"]:
                if block.get("type") == "tool_use":
                    cc_name = block.get("name", "")
                    if cc_name in CC_TO_OC:
                        ga_name = CC_TO_OC[cc_name]
                        block["name"] = ga_name
                        # 参数恢复
                        if "input" in block:
                            in_params = block["input"]
                            if ga_name in OC_PARAM_ADAPTERS:
                                block["input"] = OC_PARAM_ADAPTERS[ga_name](in_params)
        # 最外层也可能有 tool_use
        if isinstance(data.get("tool_calls"), list):
            for tc in data["tool_calls"]:
                if "function" in tc:
                    cc_fn = tc["function"].get("name", "")
                    if cc_fn in CC_TO_OC:
                        tc["function"]["name"] = CC_TO_OC[cc_fn]
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    except json.JSONDecodeError:
        # SSE line: 可能是 data: {...}
        prefix = ""
        if response_text.startswith("data: "):
            prefix = "data: "
            payload = response_text[6:]
        elif response_text.startswith(":"):
            return response_text  # keep-alive
        else:
            payload = response_text
        try:
            data = json.loads(payload)
            if "content" in data and isinstance(data["content"], list):
                for block in data["content"]:
                    if block.get("type") == "tool_use":
                        cc_name = block.get("name", "")
                        if cc_name in CC_TO_OC:
                            block["name"] = CC_TO_OC[cc_name]
            elif "type" in data and data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "tool_use":
                    cc_name = delta.get("name", "")
                    if cc_name in CC_TO_OC:
                        delta["name"] = CC_TO_OC[cc_name]
            return prefix + json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        except json.JSONDecodeError:
            # 全文替换兜底（字符串级回退）
            for cc_name, ga_name in CC_TO_OC.items():
                response_text = response_text.replace(f'"name":"{cc_name}"', f'"name":"{ga_name}"')
                response_text = response_text.replace(f'"name": "{cc_name}"', f'"name": "{ga_name}"')
            return response_text


@app.route("/", methods=["GET"])
def index():
    return json.dumps({
        "status": "ok",
        "proxy": "cc-style-ga-proxy",
        "port": PORT,
        "upstream": UPSTREAM_BASE,
        "session_id": SESSION_ID,
        "dry_run": DRY_RUN,
    })


@app.route("/health", methods=["GET"])
def health():
    return json.dumps({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": SESSION_ID,
    })


@app.route("/v1/models", methods=["GET"])
def models():
    """
    透传 models 请求到 upstream。
    cc-switch 的 Anthropic 兼容端点不一定支持 /v1/models；失败时返回当前配置模型，
    避免为了模型列表在代码里硬编码第三方网关和密钥。
    """
    upstream_url = f"{MODELS_BASE}/v1/models"
    auth_header = request.headers.get("Authorization") or request.headers.get("x-api-key")
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header if auth_header.startswith("Bearer ") else f"Bearer {auth_header}"
    try:
        r = requests.get(
            upstream_url, headers=headers, params=dict(request.args), timeout=10,
        )
        if r.status_code < 400:
            return Response(r.content, status=r.status_code,
                            content_type=r.headers.get("content-type", "application/json"))
    except requests.RequestException as e:
        log(f"models passthrough failed: {e}")

    model = MODEL_OVERRIDE or os.environ.get("DEFAULT_MODEL", "claude-opus-4-8")
    return Response(json.dumps({"object": "list", "data": [{"id": model, "object": "model"}]}),
                    status=200, content_type="application/json")


@app.route("/v1/messages", methods=["POST"])
def messages():
    """Anthropic /v1/messages 主入口"""
    inbound_raw = request.get_data()
    try:
        body = json.loads(inbound_raw)
    except json.JSONDecodeError as e:
        return Response(json.dumps({"error": f"Invalid JSON: {e}"}), status=400)

    # 注入 CC 伪装
    cc_body = inject_system_and_cch(body)
    cch = cc_body.pop("_cch", None)

    # Headers
    headers = build_headers()
    inbound_beta = request.headers.get("anthropic-beta")
    if inbound_beta:
        merged_beta = list(dict.fromkeys(
            [p.strip() for p in headers["anthropic-beta"].split(",") if p.strip()] +
            [p.strip() for p in inbound_beta.split(",") if p.strip()]
        ))
        headers["anthropic-beta"] = ",".join(merged_beta)
    if cch:
        headers["x-claude-code-client-sha256"] = cch

    # 提取 auth（如果有）
    auth_header = request.headers.get("Authorization") or request.headers.get("x-api-key")
    if auth_header:
        headers["Authorization"] = auth_header

    # dry-run
    if DRY_RUN:
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        cap_path = os.path.join(CAPTURE_DIR, f"dryrun_{int(time.time()*1000)}.json")
        with open(cap_path, "w") as f:
            json.dump({
                "ts": datetime.now(timezone.utc).isoformat(),
                "headers": {k: "***" if k.lower() in ("authorization", "x-api-key") else v for k, v in headers.items()},
                "body": cc_body,
            }, f, indent=2, ensure_ascii=False)
        log(f"DRY_RUN saved to {cap_path}")
        return Response(json.dumps({"dry_run": True, "captured": cap_path}), status=200)

    # 转发到 upstream
    upstream_url = f"{UPSTREAM_BASE}/v1/messages"
    log(f"→ {upstream_url} | model={cc_body.get('model')} | session={SESSION_ID[:8]}...")

    try:
        resp = requests.post(
            upstream_url,
            headers=headers,
            json=cc_body,
            timeout=180,
            stream=cc_body.get("stream", False),
        )
    except requests.Timeout:
        return Response(json.dumps({"error": "Upstream timeout"}), status=504)
    except requests.ConnectionError as e:
        return Response(json.dumps({"error": f"Upstream unreachable: {e}"}), status=502)

    if resp.status_code >= 400:
        log(f"Upstream error {resp.status_code}: {resp.text[:200]}")
        return Response(resp.content, status=resp.status_code, content_type=resp.headers.get("content-type", "application/json"))

    # 响应回程映射
    if not cc_body.get("stream", False):
        remapped = remap_response(resp.text)
        return Response(remapped, status=resp.status_code, content_type="application/json")

    # SSE streaming: 逐 line 处理
    def stream_generator():
        for line in resp.iter_lines():
            if not line:
                yield b"\n"
                continue
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                yield line + b"\n"
                continue
            if text.startswith(":") or text.startswith("event:"):
                yield (text + "\n").encode("utf-8")
                continue
            remapped = remap_response(text)
            yield (remapped + "\n").encode("utf-8")

    return Response(stream_generator(), status=resp.status_code, content_type="text/event-stream")


# 额外支持 OpenAI 风格 /v1/chat/completions（常见代理入口）
@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    """如果 upstream 用 OpenAI 风格端点，透传"""
    inbound_raw = request.get_data()
    try:
        body = json.loads(inbound_raw)
    except json.JSONDecodeError as e:
        return Response(json.dumps({"error": f"Invalid JSON: {e}"}), status=400)

    cc_body = inject_system_and_cch(body)
    cch = cc_body.pop("_cch", None)

    headers = build_headers()
    if cch:
        headers["x-claude-code-client-sha256"] = cch

    auth_header = request.headers.get("Authorization") or request.headers.get("x-api-key")
    if auth_header:
        headers["Authorization"] = auth_header

    upstream_url = f"{UPSTREAM_BASE}/v1/chat/completions"
    log(f"→ {upstream_url} (chat_completions) | session={SESSION_ID[:8]}...")

    if DRY_RUN:
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        cap_path = os.path.join(CAPTURE_DIR, f"dryrun_chat_{int(time.time()*1000)}.json")
        with open(cap_path, "w") as f:
            json.dump({"headers": {k: "***" if k.lower() in ("authorization",) else v for k, v in headers.items()}, "body": cc_body}, f, indent=2)
        return Response(json.dumps({"dry_run": True}), status=200)

    try:
        resp = requests.post(
            upstream_url,
            headers=headers,
            json=cc_body,
            timeout=180,
            stream=cc_body.get("stream", False),
        )
    except requests.RequestException as e:
        return Response(json.dumps({"error": str(e)}), status=502)

    if not cc_body.get("stream", False):
        remapped = remap_response(resp.text)
        return Response(remapped, status=resp.status_code, content_type="application/json")

    def stream_gen():
        for line in resp.iter_lines():
            if not line:
                yield b"\n"
                continue
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                yield line + b"\n"
                continue
            remapped = remap_response(text)
            yield (remapped + "\n").encode("utf-8")

    return Response(stream_gen(), status=resp.status_code, content_type="text/event-stream")


if __name__ == "__main__":
    log(f"Starting CC-Style Proxy on port {PORT}")
    log(f"Upstream: {UPSTREAM_BASE}")
    log(f"Session: {SESSION_ID}")
    log(f"DRY_RUN: {DRY_RUN}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
