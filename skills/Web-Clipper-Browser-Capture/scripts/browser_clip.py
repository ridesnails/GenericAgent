#!/usr/bin/env python3
"""Open URL in host Chrome (CDP), dump rendered HTML, POST to web-clipper /upload-html.

Never prints API keys. Key source order:
  1) --api-key / env WEB_CLIPPER_API_KEY / env API_KEY
  2) keychain web_clipper_api_key (memory/keychain.py)
  3) clip project .dev.vars API_KEY (local only)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import websockets
except ImportError as e:  # pragma: no cover
    print("missing dependency: websockets", file=sys.stderr)
    raise SystemExit(2) from e

DEFAULT_BASE = "https://c.yi.uy"
DEFAULT_CDP = "http://127.0.0.1:9222"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HARD_HTML_CAP = 9 * 1024 * 1024  # leave headroom for multipart
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

HARD_HOSTS = (
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "zhuanlan.zhihu.com",
    "www.zhihu.com",
    "zhihu.com",
    "www.xiaohongshu.com",
    "xiaohongshu.com",
    "www.bilibili.com",
    "bilibili.com",
)


def eprint(*args):
    print(*args, file=sys.stderr)


def load_api_key(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    for env_name in ("WEB_CLIPPER_API_KEY", "API_KEY"):
        v = os.environ.get(env_name)
        if v:
            return v.strip()
    # keychain
    try:
        root = Path(__file__).resolve().parents[3]  # .../GenericAgent
        mem = root / "memory"
        for p in (str(root), str(mem)):
            if p not in sys.path:
                sys.path.insert(0, p)
        from keychain import keys  # type: ignore

        if "web_clipper_api_key" in keys.ls():
            return keys.web_clipper_api_key.use()
    except Exception as ex:
        eprint(f"[keychain] skip: {type(ex).__name__}: {ex}")
    # local .dev.vars
    for candidate in (
        Path("/Users/qing/code/clip/web-clipper/.dev.vars"),
        Path.home() / "code/clip/web-clipper/.dev.vars",
    ):
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                if k.strip() == "API_KEY":
                    return v.strip().strip('"').strip("'")
    raise SystemExit("API key not found (pass --api-key, env, keychain, or .dev.vars)")


def cdp_http(cdp: str, path: str, method: str = "GET") -> dict | str:
    url = cdp.rstrip("/") + path
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


async def cdp_call(ws, mid: dict, method: str, params: dict | None = None, timeout: float = 60):
    msg_id = mid["n"]
    mid["n"] += 1
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(raw)
        if data.get("id") == msg_id:
            if "error" in data:
                raise RuntimeError(f"CDP {method}: {data['error']}")
            return data.get("result") or {}


def inject_base_if_needed(html: str, base_url: str) -> str:
    if re.search(r"<base\s", html, re.I):
        return html
    tag = f'<base href="{base_url}">'
    if re.search(r"<head[^>]*>", html, re.I):
        return re.sub(r"(<head[^>]*>)", r"\1" + tag, html, count=1, flags=re.I)
    return tag + html


def strip_heavy(html: str) -> str:
    """Best-effort shrink toward 10MB limit without nuking article text."""
    # drop scripts / styles / noscript / svg (often huge)
    html = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
    html = re.sub(r"<noscript\b[^>]*>[\s\S]*?</noscript>", "", html, flags=re.I)
    html = re.sub(r"<svg\b[^>]*>[\s\S]*?</svg>", "", html, flags=re.I)
    # drop huge data: images
    html = re.sub(
        r'(<img\b[^>]*\bsrc\s*=\s*")data:image/[^"]{200,}(")',
        r'\1data:,"\2',
        html,
        flags=re.I,
    )
    return html


async def wait_load(ws, mid: dict, url: str, wait_sec: float, ready_selector: str | None) -> None:
    """Navigate (if needed) and wait until document is not about:blank and ready."""
    await cdp_call(ws, mid, "Page.navigate", {"url": url}, timeout=60)
    deadline = time.time() + max(wait_sec, 1.0)
    ready = False
    while time.time() < deadline:
        st = await cdp_call(
            ws,
            mid,
            "Runtime.evaluate",
            {
                "expression": "({rs: document.readyState, href: location.href, title: document.title||''})",
                "returnByValue": True,
            },
        )
        info = (st.get("result") or {}).get("value") or {}
        href = info.get("href") or ""
        state = info.get("rs")
        sel_ok = True
        if ready_selector:
            chk = await cdp_call(
                ws,
                mid,
                "Runtime.evaluate",
                {
                    "expression": f"!!document.querySelector({json.dumps(ready_selector)})",
                    "returnByValue": True,
                },
            )
            sel_ok = bool((chk.get("result") or {}).get("value"))
        # about:blank with complete is a false ready (new-tab race)
        if state == "complete" and href and not href.startswith("about:") and sel_ok:
            ready = True
            break
        await asyncio.sleep(0.25)
    if not ready:
        # last chance soft wait for SPA / late paint
        await asyncio.sleep(min(2.0, wait_sec))


async def capture_html(
    url: str,
    cdp: str,
    wait_sec: float,
    ready_selector: str | None,
    keep_tab: bool,
) -> dict:
    # Prefer blank tab + Page.navigate (avoids /json/new?url races → about:blank)
    target = None
    last_err = None
    for path in ("/json/new?about:blank", "/json/new"):
        try:
            target = cdp_http(cdp, path, method="PUT")
            if isinstance(target, dict) and target.get("webSocketDebuggerUrl"):
                break
        except Exception as ex:
            last_err = ex
            target = None
    if not isinstance(target, dict) or "webSocketDebuggerUrl" not in target:
        # fallback: open with URL in query (older behavior)
        q = urllib.parse.quote(url, safe="")
        try:
            target = cdp_http(cdp, f"/json/new?{q}", method="PUT")
        except Exception as ex:
            raise RuntimeError(f"/json/new failed: {ex} (prior: {last_err})") from ex
    if not isinstance(target, dict) or "webSocketDebuggerUrl" not in target:
        raise RuntimeError(f"unexpected /json/new response: {target!r}")
    tid = target["id"]
    ws_url = target["webSocketDebuggerUrl"]
    mid = {"n": 1}
    result = {
        "targetId": tid,
        "html": "",
        "title": "",
        "finalUrl": url,
        "base": url,
        "len": 0,
    }
    try:
        async with websockets.connect(ws_url, max_size=60 * 1024 * 1024) as ws:
            await cdp_call(ws, mid, "Page.enable")
            await cdp_call(ws, mid, "Runtime.enable")
            try:
                await cdp_call(ws, mid, "Page.bringToFront")
            except Exception:
                pass

            await wait_load(ws, mid, url, wait_sec=wait_sec, ready_selector=ready_selector)

            # weixin-ish lazy images + scroll nudge
            await cdp_call(
                ws,
                mid,
                "Runtime.evaluate",
                {
                    "expression": """(() => {
                      const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                      return (async () => {
                        const h = Math.max(document.body?.scrollHeight||0, document.documentElement?.scrollHeight||0);
                        const step = Math.max(window.innerHeight||600, 400);
                        for (let y=0; y<h; y+=step) {
                          window.scrollTo(0, y);
                          await sleep(80);
                        }
                        window.scrollTo(0, 0);
                        document.querySelectorAll('img[data-src]').forEach(img => {
                          const v = img.getAttribute('data-src');
                          if (v && !img.getAttribute('src')) img.setAttribute('src', v);
                        });
                        document.querySelectorAll('img[data-original]').forEach(img => {
                          const v = img.getAttribute('data-original');
                          if (v && !img.getAttribute('src')) img.setAttribute('src', v);
                        });
                        return true;
                      })();
                    })()""",
                    "awaitPromise": True,
                    "returnByValue": True,
                },
                timeout=120,
            )

            expr = """(() => {
              const html = document.documentElement.outerHTML;
              return {
                html,
                title: document.title || '',
                href: location.href,
                base: document.baseURI || location.href,
                len: html.length
              };
            })()"""
            res = await cdp_call(
                ws,
                mid,
                "Runtime.evaluate",
                {"expression": expr, "returnByValue": True},
                timeout=120,
            )
            val = (res.get("result") or {}).get("value") or {}
            result.update(
                {
                    "html": val.get("html") or "",
                    "title": val.get("title") or "",
                    "finalUrl": val.get("href") or url,
                    "base": val.get("base") or url,
                    "len": int(val.get("len") or 0),
                }
            )
    finally:
        if not keep_tab:
            try:
                cdp_http(cdp, f"/json/close/{tid}", method="GET")
            except Exception as ex:
                eprint(f"[cdp] close tab warn: {ex}")
    final = result.get("finalUrl") or ""
    if not result["html"] or final.startswith("about:") or result["len"] < 200:
        raise RuntimeError(
            f"weak capture: finalUrl={final!r} title={result.get('title')!r} len={result.get('len')}"
        )
    return result


def multipart_upload(base_url: str, api_key: str, page_url: str, html_path: Path) -> dict:
    boundary = f"----gaBrowserClip{int(time.time()*1000)}"
    file_bytes = html_path.read_bytes()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise SystemExit(f"HTML still too large after shrink: {len(file_bytes)} > {MAX_UPLOAD_BYTES}")

    def part(name: str, content: bytes, filename: str | None = None, ctype: str | None = None) -> bytes:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        headers = [disposition.encode()]
        if ctype:
            headers.append(f"Content-Type: {ctype}".encode())
        return b"\r\n".join([f"--{boundary}".encode(), *headers, b"", content, b""])

    body = b"".join(
        [
            part("url", page_url.encode("utf-8")),
            part("singlehtmlfile", file_bytes, filename=html_path.name, ctype="text/html"),
            f"--{boundary}--\r\n".encode(),
        ]
    )
    req = urllib.request.Request(
        base_url.rstrip("/") + "/upload-html",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise SystemExit(f"upload HTTP {e.code}: {raw[:500]}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"upload non-JSON ({status}): {raw[:500]}") from e
    return data


def guess_ready_selector(url: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    host = urllib.parse.urlparse(url).hostname or ""
    host = host.lower()
    if "mp.weixin.qq.com" in host:
        return "#js_content"
    if "zhihu.com" in host:
        return "article, .Post-RichText, .RichContent"
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Browser-capture URL → web-clipper /upload-html")
    p.add_argument("url", help="http(s) URL to open in real Chrome")
    p.add_argument("--base-url", default=os.environ.get("WEB_CLIPPER_BASE", DEFAULT_BASE))
    p.add_argument("--cdp", default=os.environ.get("CDP_URL", DEFAULT_CDP))
    p.add_argument("--api-key", default=None, help="prefer keychain; do not log this")
    p.add_argument("--wait", type=float, default=20.0, help="max seconds to wait for ready")
    p.add_argument("--ready-selector", default=None, help="CSS selector that must exist")
    p.add_argument("--keep-tab", action="store_true", help="do not close CDP tab")
    p.add_argument("--keep-html", default=None, help="path to save dumped HTML")
    p.add_argument("--dry-run", action="store_true", help="capture only, no upload")
    p.add_argument("--json", action="store_true", help="print full response JSON")
    args = p.parse_args(argv)

    url = args.url.strip()
    if not re.match(r"^https?://", url, re.I):
        eprint("url must be http(s)")
        return 2

    # CDP up?
    try:
        ver = cdp_http(args.cdp, "/json/version")
        if isinstance(ver, dict):
            eprint(f"[cdp] {ver.get('Browser', 'ok')}")
    except Exception as ex:
        eprint(f"CDP not reachable at {args.cdp}: {ex}")
        return 2

    selector = guess_ready_selector(url, args.ready_selector)
    eprint(f"[capture] open {url} selector={selector!r} wait={args.wait}s")
    cap = asyncio.run(
        capture_html(url, args.cdp, wait_sec=args.wait, ready_selector=selector, keep_tab=args.keep_tab)
    )
    html = inject_base_if_needed(cap["html"], cap.get("base") or cap.get("finalUrl") or url)
    raw_len = len(html.encode("utf-8", "replace"))
    if raw_len > HARD_HTML_CAP:
        eprint(f"[capture] shrink html {raw_len} bytes")
        html = strip_heavy(html)
        # if still huge, keep only body
        if len(html.encode("utf-8", "replace")) > HARD_HTML_CAP:
            m = re.search(r"<body\b[^>]*>[\s\S]*</body>", html, re.I)
            if m:
                html = (
                    "<!doctype html><html><head><meta charset=\"utf-8\">"
                    f"<base href=\"{cap.get('base') or url}\"><title>{cap.get('title') or ''}</title></head>"
                    f"{m.group(0)}</html>"
                )
            html = strip_heavy(html)
    out_len = len(html.encode("utf-8", "replace"))
    eprint(f"[capture] title={cap.get('title')!r} final={cap.get('finalUrl')} bytes={out_len}")

    if args.keep_html:
        Path(args.keep_html).write_text(html, encoding="utf-8")
        eprint(f"[capture] wrote {args.keep_html}")

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dryRun": True,
                    "title": cap.get("title"),
                    "finalUrl": cap.get("finalUrl"),
                    "bytes": out_len,
                    "targetId": cap.get("targetId"),
                },
                ensure_ascii=False,
            )
        )
        return 0

    api_key = load_api_key(args.api_key)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = Path(f.name)
    try:
        eprint(f"[upload] POST {args.base_url.rstrip('/')}/upload-html")
        resp = multipart_upload(args.base_url, api_key, cap.get("finalUrl") or url, tmp)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

    if args.json:
        print(json.dumps(resp, ensure_ascii=False, indent=2))
    else:
        # compact agent-friendly summary (no secrets)
        summary = {
            "ok": resp.get("ok"),
            "title": resp.get("title") or cap.get("title"),
            "mode": resp.get("mode"),
            "path": resp.get("path"),
            "fnsOk": resp.get("fnsOk"),
            "telegraphOk": resp.get("telegraphOk"),
            "telegraphUrl": resp.get("telegraphUrl"),
            "htmlViewUrl": resp.get("htmlViewUrl"),
            "telegramMessageId": resp.get("telegramMessageId"),
            "sourceUrl": cap.get("finalUrl") or url,
            "captureBytes": out_len,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if resp.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
