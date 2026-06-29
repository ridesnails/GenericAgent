#!/usr/bin/env python3
"""Small Arcane API helper for this skill.

Usage:
  export ARCANE_URL='https://dc.ormz.pro'
  export ARCANE_API_KEY='...'
  python arcane_api.py GET /environments
  python arcane_api.py GET /environments/<envId>/projects --pretty
  python arcane_api.py POST /environments/<envId>/projects/<projectId>/restart '{}'

Safety:
  - API key is read only from ARCANE_API_KEY and never printed.
  - Arcane OpenAPI server is normally `${ARCANE_URL}/api`; OpenAPI paths such as
    `/environments` are automatically sent as `/api/environments` first.
  - If the server returns a frontend HTML fallback, this helper treats it as a
    wrong API path instead of a successful API response.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def build_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def api_first_paths(path: str) -> list[str]:
    """Return candidate paths, preferring the documented Arcane API server /api."""
    p = "/" + path.lstrip("/")
    if p == "/api" or p.startswith("/api/"):
        alt = p[4:] or "/"
        return [p, alt]
    return ["/api" + p, p]


def request(method: str, base: str, key: str, path: str, body: Any | None = None) -> tuple[int, str, str]:
    data = None
    headers = {"X-API-Key": key, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(build_url(base, path), data=data, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            ctype = resp.headers.get("content-type", "")
            if "text/html" in ctype.lower() and "<!doctype html" in raw.lower():
                raise RuntimeError(f"HTML frontend fallback for {path}; use /api OpenAPI path")
            return resp.status, raw, ctype
    except HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} {e.reason} for {path}\n{raw}") from e
    except URLError as e:
        raise RuntimeError(f"Network error for {path}: {e}") from e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE", "get", "post", "put", "patch", "delete"])
    ap.add_argument("path", help="OpenAPI path, with or without /api prefix")
    ap.add_argument("json_body", nargs="?", help="JSON body for POST/PUT/PATCH")
    ap.add_argument("--pretty", action="store_true", help="pretty-print JSON response")
    args = ap.parse_args()

    base = os.environ.get("ARCANE_URL", "https://dc.ormz.pro")
    key = os.environ.get("ARCANE_API_KEY")
    if not key:
        print("ERROR: ARCANE_API_KEY is required", file=sys.stderr)
        return 2

    body = None
    if args.json_body is not None:
        try:
            body = json.loads(args.json_body)
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON body: {e}", file=sys.stderr)
            return 2

    tried = []
    for path in api_first_paths(args.path):
        if not path or path in tried:
            continue
        tried.append(path)
        try:
            status, raw, ctype = request(args.method, base, key, path, body)
            if args.pretty and raw and "json" in ctype.lower():
                print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
            else:
                print(raw)
            print(f"# status={status} path={path}", file=sys.stderr)
            return 0
        except RuntimeError as e:
            msg = str(e)
            retryable_wrong_path = (
                ("HTTP 404" in msg) or
                ("HTML frontend fallback" in msg)
            )
            if retryable_wrong_path and path == tried[0] and len(api_first_paths(args.path)) > 1:
                continue
            print("ERROR:", msg, file=sys.stderr)
            return 1
    print(f"ERROR: no usable path after trying {tried}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
