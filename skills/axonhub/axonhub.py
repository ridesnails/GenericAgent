#!/usr/bin/env python3
"""AxonHub instance management helper for this skill.

Manages an AxonHub AI-Gateway instance (default https://api.198707.xyz) over its
two distinct GraphQL surfaces:

  1) admin link   -> POST /admin/graphql       (full: channels/models/users/status)
       auth: login at POST /admin/auth/signin {email,password} -> JWT bearer.
  2) service link -> POST /openapi/v1/graphql  (limited: LLM API-key lifecycle)
       auth: Authorization: Bearer <service_account ah-key>.

Credentials come ONLY from the local keychain and are never printed:
  - axonhub_admin_user / axonhub_admin_pass  (owner account, scopes=*)
  - axonhub_service_account_key              (ah-... key)

Usage examples:
  python axonhub.py status
  python axonhub.py channels [--limit 100]
  python axonhub.py models   [--limit 100]
  python axonhub.py dashboard
  python axonhub.py graphql '<query/mutation>' '<json-variables>'   # admin link
  python axonhub.py sa-graphql '<query/mutation>' '<json-variables>' # service link
  python axonhub.py create-key <name>           # service link
  python axonhub.py quota --key ah-...          # service link (or --id <keyID>)
  python axonhub.py quota --id <keyID>

Safety:
  - Secrets are read from keychain and used only as headers/body; never logged.
  - The admin JWT is cached in ~/.axonhub_token (mode 600) and refreshed on 401.
  - All commands are read-only by default; only create-key / explicit graphql
    mutations change state.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.environ.get("AXONHUB_URL", "https://api.198707.xyz").rstrip("/")
_TOKEN_CACHE = pathlib.Path.home() / ".axonhub_token"

# Optional local keychain (GenericAgent host). Portable installs use env vars.
_MEM = os.environ.get("GA_MEMORY_DIR", "/Users/qing/code/GenericAgent/memory")
if os.path.isdir(_MEM) and _MEM not in sys.path:
    sys.path.insert(0, _MEM)


def _secret(env_name: str, keychain_name: str) -> str:
    """Resolve a secret: environment variable first, local keychain fallback.

    Portable usage (codex / claude code / any host): set the env vars below.
    Local GenericAgent host: values are pulled from the encrypted keychain.
    Secrets are never printed.
    """
    val = os.environ.get(env_name)
    if val:
        return val.strip()
    try:
        from keychain import keys  # noqa: E402

        return getattr(keys, keychain_name).use()
    except Exception as e:  # ImportError or missing entry
        raise RuntimeError(
            f"missing credential: set ${env_name} "
            f"(or add keychain entry '{keychain_name}'). detail: {e}"
        ) from e


def _http(method: str, path: str, headers: dict[str, str], body: Any | None = None) -> tuple[int, str]:
    data = None
    h = dict(headers)
    h.setdefault("Accept", "application/json")
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = Request(BASE + path, data=data, headers=h, method=method.upper())
    try:
        with urlopen(req, timeout=40) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except URLError as e:
        raise RuntimeError(f"Network error for {path}: {e}") from e


# ---------------------------------------------------------------- admin link
def _login() -> str:
    email = _secret("AXONHUB_ADMIN_USER", "axonhub_admin_user")
    password = _secret("AXONHUB_ADMIN_PASS", "axonhub_admin_pass")
    status, raw = _http(
        "POST", "/admin/auth/signin", {}, {"email": email, "password": password}
    )
    if status != 200:
        raise RuntimeError(f"signin failed: HTTP {status} {raw[:300]}")
    token = json.loads(raw).get("token")
    if not token:
        raise RuntimeError(f"signin returned no token: {raw[:300]}")
    try:
        _TOKEN_CACHE.write_text(token)
        _TOKEN_CACHE.chmod(0o600)
    except OSError:
        pass
    return token


def _cached_token() -> str | None:
    try:
        if _TOKEN_CACHE.exists() and (time.time() - _TOKEN_CACHE.stat().st_mtime) < 3000:
            return _TOKEN_CACHE.read_text().strip() or None
    except OSError:
        pass
    return None


def admin_gql(query: str, variables: dict | None = None) -> dict:
    """Call /admin/graphql with a cached JWT, retrying once on auth failure."""
    body = {"query": query, "variables": variables or {}}
    token = _cached_token()
    for attempt in (1, 2):
        if not token:
            token = _login()
        status, raw = _http(
            "POST", "/admin/graphql", {"Authorization": f"Bearer {token}"}, body
        )
        # auth problems surface as 401 or as a GraphQL error mentioning the key
        if status == 401 or "API key is required" in raw or "unauthorized" in raw.lower():
            token = None
            continue
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(f"admin graphql non-JSON (HTTP {status}): {raw[:300]}")
        if out.get("errors"):
            raise RuntimeError("admin graphql errors: " + json.dumps(out["errors"], ensure_ascii=False))
        return out["data"]
    raise RuntimeError("admin graphql failed after re-login")


# -------------------------------------------------------------- service link
def sa_gql(query: str, variables: dict | None = None) -> dict:
    """Call /openapi/v1/graphql with the service-account key."""
    key = _secret("AXONHUB_SERVICE_KEY", "axonhub_service_account_key")
    status, raw = _http(
        "POST",
        "/openapi/v1/graphql",
        {"Authorization": f"Bearer {key}"},
        {"query": query, "variables": variables or {}},
    )
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"service graphql non-JSON (HTTP {status}): {raw[:300]}")
    if out.get("errors"):
        raise RuntimeError("service graphql errors: " + json.dumps(out["errors"], ensure_ascii=False))
    return out["data"]


# --------------------------------------------------------------- subcommands
def cmd_status(_args) -> dict:
    #免鉴权的系统状态 + 带鉴权的版本信息
    st_code, st_raw = _http("GET", "/admin/system/status", {})
    try:
        system = json.loads(st_raw)
    except json.JSONDecodeError:
        system = {"_raw": st_raw[:200], "_httpStatus": st_code}
    ver = admin_gql("{ systemVersion { version } }").get("systemVersion", {})
    return {"systemStatus": system, "systemVersion": ver}


def cmd_dashboard(_args) -> dict:
    q = """{
      dashboardOverview {
        totalRequests
        failedRequests
        averageResponseTime
        requestStats { date count }
      }
    }"""
    try:
        return admin_gql(q)
    except RuntimeError:
        # requestStats sub-fields vary across builds; fall back to scalars only
        return admin_gql("{ dashboardOverview { totalRequests failedRequests averageResponseTime } }")


def cmd_channels(args) -> dict:
    q = """query($first:Int){
      channels(first:$first){
        totalCount
        edges{ node{ id name type status baseURL defaultTestModel } }
      }
    }"""
    data = admin_gql(q, {"first": args.limit})
    conn = data["channels"]
    return {
        "totalCount": conn.get("totalCount"),
        "channels": [e["node"] for e in conn.get("edges", [])],
    }


def cmd_models(args) -> dict:
    q = """query($first:Int){
      models(first:$first){
        totalCount
        edges{ node{ id modelID name developer status group } }
      }
    }"""
    data = admin_gql(q, {"first": args.limit})
    conn = data["models"]
    return {
        "totalCount": conn.get("totalCount"),
        "models": [e["node"] for e in conn.get("edges", [])],
    }


def cmd_graphql(args) -> dict:
    variables = json.loads(args.variables) if args.variables else {}
    return admin_gql(args.query, variables)


def cmd_sa_graphql(args) -> dict:
    variables = json.loads(args.variables) if args.variables else {}
    return sa_gql(args.query, variables)


def cmd_create_key(args) -> dict:
    q = """mutation($name:String!){
      createLLMAPIKey(name:$name){ id name key scopes }
    }"""
    return sa_gql(q, {"name": args.name})


def cmd_quota(args) -> dict:
    if not args.key and not args.id:
        raise SystemExit("quota requires --key <ah-...> or --id <keyID>")
    var: dict[str, Any] = {}
    sig = ""
    if args.id:
        var["apiKeyId"] = args.id
        sig = "$apiKeyId:ID"
        arg = "apiKeyId:$apiKeyId"
    else:
        var["key"] = args.key
        sig = "$key:String"
        arg = "key:$key"
    q = f"""query({sig}){{
      apiKeyQuotaUsages({arg}){{ requestCount totalTokens totalCost }}
    }}"""
    return sa_gql(q, var)


def main() -> int:
    ap = argparse.ArgumentParser(description="AxonHub instance management")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="system status + version (admin)")
    sub.add_parser("dashboard", help="dashboard overview (admin)")

    p = sub.add_parser("channels", help="list channels (admin)")
    p.add_argument("--limit", type=int, default=100)

    p = sub.add_parser("models", help="list models (admin)")
    p.add_argument("--limit", type=int, default=100)

    p = sub.add_parser("graphql", help="raw admin graphql")
    p.add_argument("query")
    p.add_argument("variables", nargs="?")

    p = sub.add_parser("sa-graphql", help="raw service-account graphql")
    p.add_argument("query")
    p.add_argument("variables", nargs="?")

    p = sub.add_parser("create-key", help="create a downstream LLM API key (service)")
    p.add_argument("name")

    p = sub.add_parser("quota", help="quota usage for a key (service)")
    p.add_argument("--key")
    p.add_argument("--id")

    args = ap.parse_args()
    handlers = {
        "status": cmd_status,
        "dashboard": cmd_dashboard,
        "channels": cmd_channels,
        "models": cmd_models,
        "graphql": cmd_graphql,
        "sa-graphql": cmd_sa_graphql,
        "create-key": cmd_create_key,
        "quota": cmd_quota,
    }
    try:
        result = handlers[args.cmd](args)
    except RuntimeError as e:
        print("ERROR:", e, file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
