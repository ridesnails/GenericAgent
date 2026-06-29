"""Credentials loader for this DeepSearch skill.

Loads credentials from (in priority order):
  1. Environment variables (GROK2API_API_KEY, TAVILY_API_KEY, FIRECRAWL_API_KEY, etc.)
  2. the project's .env file ([LLM_APIS] + [CREDENTIALS] sections)

Keeps .env authoritative — no separate .env file needed.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# scripts/_creds.py → skill 目录下的 .env (self-contained)
DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"

DEFAULTS = {
    "GROK2API_BASE_URL": "https://<openai-compatible-host>/v1",
    "GROK2API_MODEL": "grok-4.20-beta",
    "TAVILY_BASE_URL": "https://api.tavily.com",
    "FIRECRAWL_BASE_URL": "https://api.firecrawl.dev/v2",
}


def _parse_dotenv(text: str) -> dict[str, str]:
    """Extract key:value pairs from .env.

    Format: `KEY: value` or `key: value` (lowercase project convention).
    We map the project's lowercase shorthand names to standard env-var names.
    """
    out: dict[str, str] = {}
    # Generic KEY: value collector (strips inline comments starting with `  #`).
    for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", text, re.M):
        key, val = m.group(1), m.group(2)
        # Strip trailing inline comments (two+ spaces then #).
        val = re.sub(r"\s{2,}#.*$", "", val).strip()
        if val:
            out[key] = val

    # Normalize shorthand -> standard env names (only if not already set).
    # NOTE: dict keys must be unique — use tuples for potential duplicate keys
    aliases = [
        ("legacy_url", "GROK2API_BASE_URL"),
        ("legacy_key", "GROK2API_API_KEY"),
    ]
    for src, dst in aliases:
        if src in out and dst not in out:
            out[dst] = out[src]
    return out


@lru_cache(maxsize=1)
def get_creds() -> dict[str, Any]:
    """Return credentials + endpoints.

    Resolution order: env var > .env > DEFAULTS.
    """
    creds: dict[str, Any] = dict(DEFAULTS)

    if DOTENV_PATH.exists():
        creds.update(_parse_dotenv(DOTENV_PATH.read_text(encoding="utf-8")))

    for k in (
        "GROK2API_API_KEY",
        "GROK2API_BASE_URL",
        "GROK2API_MODEL",
        "TAVILY_API_KEY",
        "TAVILY_BASE_URL",
        "FIRECRAWL_API_KEY",
        "FIRECRAWL_BASE_URL",
    ):
        v = os.environ.get(k)
        if v:
            creds[k] = v

    # Multi-key env support (comma-separated).
    tavily_list = os.environ.get("TAVILY_API_KEYS") or creds.get("TAVILY_API_KEY", "")
    creds["TAVILY_API_KEYS"] = [k.strip() for k in tavily_list.split(",") if k.strip()]

    fc_list = os.environ.get("FIRECRAWL_API_KEYS") or creds.get("FIRECRAWL_API_KEY", "")
    creds["FIRECRAWL_API_KEYS"] = [k.strip() for k in fc_list.split(",") if k.strip()]

    return creds


def require(key: str) -> str:
    v = get_creds().get(key)
    if not v:
        raise RuntimeError(
            f"Missing credential: {key}. Set env var {key} or add to "
            f"{DOTENV_PATH} under [LLM_APIS] / [CREDENTIALS]."
        )
    if isinstance(v, list):
        if not v:
            raise RuntimeError(f"Empty key list: {key}")
        return v[0]
    return str(v)


if __name__ == "__main__":
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows GBK fix
    except Exception:
        pass
    c = get_creds()
    for k, v in list(c.items()):
        if "KEY" in k and v:
            if isinstance(v, list):
                c[k] = [f"{x[:8]}...{x[-4:]}" if len(x) > 12 else "***" for x in v]
            else:
                c[k] = f"{v[:8]}...{v[-4:]}" if len(v) > 12 else "***"
    print(json.dumps(c, indent=2, ensure_ascii=False))