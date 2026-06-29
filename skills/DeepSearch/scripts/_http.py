"""Shared HTTP utilities: pooled sessions, key-rotation, OpenAI/Tavily helpers.

Design rationale
----------------
* **One Session per backend.** Module-level lazy sessions (GROK2API, Tavily,
  FireCrawl) reuse TCP/TLS connections — material speedup when ``dual_search``
  fans out in-process.
* **Sticky key rotation.** Stay on the current key until 401/403/429, then hop
  forward. 5xx triggers exponential backoff retry on the same key. Honors
  ``Retry-After`` if upstream sends it.
* **One SSE/JSON parser.** GROK2API returns SSE even for non-streamed requests;
  callers must not re-implement chunk assembly.
* **One openai_chat / tavily_post.** Three scripts call GROK2API and three call
  Tavily — one helper each kills the duplication.

Public API
----------
``log``, ``dump_json``, ``KeyRotationFailed``,
``session``, ``call_with_key_rotation``,
``parse_openai_response``, ``strip_think``,
``openai_chat``, ``tavily_post``, ``firecrawl_post``.
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from typing import Any, Callable, Iterable

import requests
from requests.adapters import HTTPAdapter

from _creds import get_creds

# --------------------------------- stdio ---------------------------------

_STDOUT_CONFIGURED = False


def log(msg: str) -> None:
    """Debug -> stderr; stdout stays a clean JSON channel."""
    print(f"[deepsearch] {msg}", file=sys.stderr, flush=True)


def dump_json(obj: Any) -> None:
    """Print JSON to stdout, forcing UTF-8 once on Windows (cp936 chokes)."""
    global _STDOUT_CONFIGURED
    if not _STDOUT_CONFIGURED:
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # py3.7+
        except Exception:
            pass
        _STDOUT_CONFIGURED = True
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ------------------------------ pooled sessions ------------------------------

class KeyRotationFailed(RuntimeError):
    """All API keys exhausted."""


def _make_session(timeout: int, pool: int = 8) -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    _orig = s.request

    def _req(method, url, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return _orig(method, url, **kwargs)

    s.request = _req  # type: ignore[method-assign]
    return s


def session(timeout: int = 30) -> requests.Session:
    """Back-compat factory; new code prefers the module-level pooled sessions."""
    return _make_session(timeout)


_GROK2_SESSION: requests.Session | None = None
_TAVILY_SESSION: requests.Session | None = None
_FIRECRAWL_SESSION: requests.Session | None = None


def _grok2() -> requests.Session:
    global _GROK2_SESSION
    if _GROK2_SESSION is None:
        _GROK2_SESSION = _make_session(timeout=90)
    return _GROK2_SESSION


def _tavily() -> requests.Session:
    global _TAVILY_SESSION
    if _TAVILY_SESSION is None:
        _TAVILY_SESSION = _make_session(timeout=60)
    return _TAVILY_SESSION


def _firecrawl() -> requests.Session:
    global _FIRECRAWL_SESSION
    if _FIRECRAWL_SESSION is None:
        _FIRECRAWL_SESSION = _make_session(timeout=90)
    return _FIRECRAWL_SESSION


# ---------------------------- key rotation core ----------------------------

def call_with_key_rotation(
    keys: Iterable[str],
    do_request: Callable[[str], requests.Response],
    *,
    max_attempts_per_key: int = 2,
    backoff_base: float = 1.0,
) -> requests.Response:
    """Try each key; rotate on 401/403/429; retry on 5xx with exp backoff."""
    keys = [k for k in keys if k]
    if not keys:
        raise KeyRotationFailed("No API keys configured")

    last_err: str | None = None
    for idx, key in enumerate(keys):
        for attempt in range(max_attempts_per_key):
            try:
                resp = do_request(key)
            except requests.RequestException as e:
                last_err = f"network error on key #{idx + 1}: {e}"
                log(last_err)
                time.sleep(backoff_base * (2 ** attempt) + random.random() * 0.3)
                continue

            sc = resp.status_code
            if 200 <= sc < 300:
                return resp
            if sc in (401, 403, 429):
                last_err = f"key #{idx + 1} -> HTTP {sc}: {resp.text[:200]}"
                log(last_err + " (rotating)")
                ra = resp.headers.get("Retry-After")
                if sc == 429 and ra:
                    try:
                        time.sleep(min(float(ra), 5.0))
                    except ValueError:
                        pass
                break
            if 500 <= sc < 600:
                last_err = f"HTTP {sc} on key #{idx + 1} attempt {attempt + 1}"
                log(last_err)
                time.sleep(backoff_base * (2 ** attempt))
                continue
            resp.raise_for_status()

    raise KeyRotationFailed(f"All {len(keys)} key(s) exhausted. Last error: {last_err}")


# ------------------------ OpenAI-compatible helpers ------------------------

def parse_openai_response(text: str) -> dict:
    """Accept standard JSON or SSE stream; return canonical chat-completion shape.

    ``{"choices": [{"message": {"content", "reasoning_content"},
                    "finish_reason"}], "model": str|None, "usage": dict}``
    """
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    content: list[str] = []
    reasoning: list[str] = []
    model: str | None = None
    usage: dict = {}
    finish_reason: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        model = chunk.get("model") or model
        if chunk.get("usage"):
            usage = chunk["usage"]
        for ch in chunk.get("choices", []):
            delta = ch.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            if ch.get("finish_reason"):
                finish_reason = ch["finish_reason"]

    return {
        "choices": [{
            "message": {
                "content": "".join(content),
                "reasoning_content": "".join(reasoning) or None,
            },
            "finish_reason": finish_reason,
        }],
        "model": model,
        "usage": usage,
    }


_THINK_RE = re.compile(r"<think>(.*?)</think>", re.S)


def strip_think(content: str) -> tuple[str, str | None]:
    """Strip Grok-4.x ``<think>...</think>`` blocks. Returns (clean, joined_thoughts)."""
    blocks = _THINK_RE.findall(content)
    clean = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.S).strip()
    joined = "\n\n".join(b.strip() for b in blocks).strip()
    return clean, (joined or None)


def openai_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 90,
) -> dict:
    """Single-call GROK2API chat helper. Returns dict with content/reasoning/model/usage/elapsed_s."""
    creds = get_creds()
    keys = creds.get("GROK2API_API_KEYS") or ([creds["GROK2API_API_KEY"]] if creds.get("GROK2API_API_KEY") else [])
    if not keys:
        raise RuntimeError("GROK2API_API_KEY not configured")
    base = creds["GROK2API_BASE_URL"].rstrip("/")
    url = f"{base}/chat/completions"
    body = {
        "model": model or creds.get("GROK2API_MODEL", "grok-4.20-beta"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    s = _grok2()

    def do(key: str) -> requests.Response:
        return s.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    log(f"POST {url} model={body['model']}")
    t0 = time.time()
    resp = call_with_key_rotation(keys, do)
    elapsed = round(time.time() - t0, 2)

    parsed = parse_openai_response(resp.text)
    msg = parsed["choices"][0]["message"]
    return {
        "content": msg.get("content", ""),
        "reasoning": msg.get("reasoning_content"),
        "model": parsed.get("model") or body["model"],
        "usage": parsed.get("usage", {}),
        "elapsed_s": elapsed,
    }


# ------------------------------ Tavily helper ------------------------------

def tavily_post(path: str, body: dict, *, timeout: int = 45) -> dict:
    """POST to a Tavily endpoint with key rotation; return parsed JSON."""
    creds = get_creds()
    keys = creds["TAVILY_API_KEYS"]
    base = creds["TAVILY_BASE_URL"].rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    s = _tavily()

    def do(key: str) -> requests.Response:
        return s.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)

    log(f"POST {url}")
    return call_with_key_rotation(keys, do).json()


def firecrawl_post(path: str, body: dict, *, timeout: int = 90) -> dict:
    """POST to a FireCrawl endpoint with key rotation; return parsed JSON."""
    creds = get_creds()
    keys = creds.get("FIRECRAWL_API_KEYS") or []
    if not keys:
        raise RuntimeError("FIRECRAWL_API_KEY not configured")
    base = creds["FIRECRAWL_BASE_URL"].rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    s = _firecrawl()

    def do(key: str) -> requests.Response:
        return s.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)

    log(f"POST {url}")
    return call_with_key_rotation(keys, do).json()