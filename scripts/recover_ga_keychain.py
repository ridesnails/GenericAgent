#!/usr/bin/env python3
"""Read-only recovery helper for ~/ga_keychain.enc.

Tries candidate username-derived XOR masks used by memory/keychain.py and
prints only recovered key names plus masked previews. It never modifies files.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable


def _mask_preview(value: str) -> str:
    n = len(value)
    if n <= 4:
        return "***"
    if n <= 16:
        return f"{value[:3]}···{value[-3:]}"
    if n <= 40:
        return f"{value[:6]}···{value[-6:]} len={n}"
    return f"{value[:10]}···{value[-6:]} len={n}"


def _xor_with_user(data: bytes, user_name: str) -> bytes:
    mask = hashlib.sha256(f"{user_name}@ga_keychain".encode()).digest()
    return bytes(b ^ mask[i % len(mask)] for i, b in enumerate(data))


def _candidate_users() -> list[str]:
    values: list[str] = []
    for getter in (
        lambda: os.getlogin(),
        lambda: getpass.getuser(),
        lambda: os.getenv("USER", ""),
        lambda: os.getenv("LOGNAME", ""),
        lambda: os.getenv("SUDO_USER", ""),
    ):
        try:
            value = (getter() or "").strip()
        except Exception:
            value = ""
        if value and value not in values:
            values.append(value)
    return values


def _load_candidates(path: Path, users: Iterable[str]) -> list[tuple[str, dict[str, str]]]:
    raw = path.read_bytes()
    hits: list[tuple[str, dict[str, str]]] = []
    for user_name in users:
        try:
            decoded = _xor_with_user(raw, user_name)
            payload = json.loads(decoded)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in payload.items()):
            continue
        hits.append((user_name, payload))
    return hits


def main() -> int:
    path = Path(os.path.expanduser(os.getenv("GA_KEYCHAIN_PATH", "~/ga_keychain.enc")))
    if not path.exists():
        print(f"[recover] not found: {path}")
        return 1

    users = _candidate_users()
    print(f"[recover] target={path}")
    print(f"[recover] trying users={users}")

    hits = _load_candidates(path, users)
    if not hits:
        print("[recover] no valid decode using built-in candidates")
        return 2

    print(f"[recover] successful decodes={len(hits)}")
    for user_name, payload in hits:
        print(f"\n[user] {user_name}")
        for key in sorted(payload):
            print(f"  - {key}: {_mask_preview(payload[key])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
