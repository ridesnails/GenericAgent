import os
import re
from pathlib import Path
from functools import lru_cache
from typing import Any

DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"

DEFAULTS: dict[str, str] = {
    "GROK2API_BASE_URL": "https://api.198707.xyz/v1",
    "GROK2API_MODEL": "grok-4.20-beta",
    "TAVILY_BASE_URL": "https://tavily.ivanli.cc/api/tavily",
    "FIRECRAWL_BASE_URL": "https://api.firecrawl.dev/v2",
}


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse .env-style file. Supports KEY: value format."""
    out: dict[str, str] = {}
    for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$", text, re.M):
        key, val = m.group(1), m.group(2)
        val = re.sub(r"\s{2,}#.*$", "", val).strip()
        if val:
            out[key] = val
    alias = {"legacy_url": "GROK2API_BASE_URL", "legacy_key": "GROK2API_API_KEY"}
    for src, dst in alias.items():
        if src in out and dst not in out:
            out[dst] = out[src]
    return out


@lru_cache(maxsize=1)
def get_creds() -> dict[str, Any]:
    """Load credentials: env var > .env > defaults."""
    creds: dict[str, Any] = dict(DEFAULTS)

    if DOTENV_PATH.exists():
        creds.update(_parse_dotenv(DOTENV_PATH.read_text(encoding="utf-8")))

    env_map = {
        "GROK2API_API_KEY": "GROK2API_API_KEY",
        "GROK2API_BASE_URL": "GROK2API_BASE_URL",
        "GROK2API_MODEL": "GROK2API_MODEL",
        "TAVILY_API_KEY": "TAVILY_API_KEY",
        "TAVILY_BASE_URL": "TAVILY_BASE_URL",
        "FIRECRAWL_API_KEY": "FIRECRAWL_API_KEY",
        "FIRECRAWL_BASE_URL": "FIRECRAWL_BASE_URL",
    }
    for env_key, cred_key in env_map.items():
        v = os.environ.get(env_key)
        if v:
            creds[cred_key] = v

    # Multi-key support
    tavily_list = os.environ.get("TAVILY_API_KEYS") or creds.get("TAVILY_API_KEY", "")
    creds["TAVILY_API_KEYS"] = [k.strip() for k in tavily_list.split(",") if k.strip()]

    fc_list = os.environ.get("FIRECRAWL_API_KEYS") or creds.get("FIRECRAWL_API_KEY", "")
    creds["FIRECRAWL_API_KEYS"] = [k.strip() for k in fc_list.split(",") if k.strip()]

    return creds


def require(key: str) -> str:
    """Get a required credential or raise."""
    v = get_creds().get(key)
    if not v:
        raise RuntimeError(
            f"Missing credential: {key}. Set env var or add to {DOTENV_PATH}"
        )
    if isinstance(v, list):
        if not v:
            raise RuntimeError(f"Empty key list: {key}")
        return v[0]
    return str(v)
