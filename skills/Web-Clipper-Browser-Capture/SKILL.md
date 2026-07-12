---
name: web-clipper-browser-capture
description: Capture hard-to-fetch pages (WeChat mp.weixin, paywalls, anti-bot) by opening the URL in the host real Chrome (Ye CDP 9222), dumping rendered HTML, then POSTing to c.yi.uy/upload-html. Use when the user asks for 浏览器剪藏/微信公众号/反爬剪藏/singlefile clip, or after plain POST / fails with empty/blocked body. Do not use for ordinary easy URLs (prefer POST /), or when the user says 收藏 for chat archive (use Web-Clipper-Conversation-Archive).
---

# Web Clipper Browser Capture

## When to load
- WeChat / 公众号: `mp.weixin.qq.com`, “微信文章”, “公众号”
- Anti-bot / login wall / empty Jina body / prior `502` on URL clip
- User says: `浏览器剪藏`, `用浏览器打开再收藏`, `singlefile 剪藏`, `真机剪藏`
- Anti-triggers:
  - Easy public docs/news → plain `POST https://c.yi.uy/` with JSON `url`
  - User **收藏** an **AI/Agent conversation** → `Web-Clipper-Conversation-Archive`
  - Summarize only, no vault write

## Required reads
- `memory/web_clipper_save_skill.md` — API shapes, auth
- `memory/tmwebdriver_sop.md` — CDP/navigation gotchas if debugging tabs manually
- L2 `[ChromeInstances]` — **Ye = default** CDP `127.0.0.1:9222`, proxy `1081`; do not use main profile

## Verified facts
- Production base: `https://c.yi.uy`
- Auth: keychain `web_clipper_api_key` via `keys.web_clipper_api_key.use()` — **never print**
- Hard pages: **do not** rely on Worker/Jina fetch; use host browser HTML → `POST /upload-html`
- Upload field names: multipart `url` + `singlehtmlfile` (`.html`, ≤10MB)
- Ye CDP must be running (`curl -s http://127.0.0.1:9222/json/version`)
- Script (preferred): `skills/Web-Clipper-Browser-Capture/scripts/browser_clip.py`

## Decision tree
1. If URL host is easy and user did not demand browser → `POST /` (JSON url).
2. If host ∈ hard list OR plain clip returns empty/blocked/503 shell → **this skill**.
3. Hard hosts (non-exhaustive): `mp.weixin.qq.com`, `zhihu.com` (often), `xiaohongshu.com`, sites that need login cookies already in Ye.
4. Fail twice → stop; report title/URL/error; ask user to pass captcha/login in Ye, then retry.

## Canonical workflow (Agent)
Prefer the script:

```bash
# from GenericAgent repo root (or absolute path)
python3 skills/Web-Clipper-Browser-Capture/scripts/browser_clip.py \
  'https://mp.weixin.qq.com/s/xxxx' \
  --wait 25
```

Options:
- `--cdp http://127.0.0.1:9222` (default Ye)
- `--base-url https://c.yi.uy`
- `--ready-selector '#js_content'` (auto for WeChat)
- `--keep-tab` if user must solve captcha then re-run dump-only path
- `--dry-run` capture HTML only
- `--keep-html /tmp/clip.html` save dump
- `--json` full worker response

Manual equivalent (if script unavailable):
1. CDP `PUT /json/new?<url>` on Ye
2. Wait `document.readyState==complete` + selector (`#js_content` on WeChat)
3. Scroll once; promote `img[data-src]` → `src`
4. `document.documentElement.outerHTML`; inject `<base href="...">` if missing
5. Strip scripts/SVG/huge `data:` if >~9MB
6. `POST /upload-html` with Bearer token + browser User-Agent (avoid CF 1010)

## Response to user
Always report (no secrets): `path`, `fnsOk`, `telegraphUrl` / `htmlViewUrl` if any, `mode`, source final URL.
For WeChat: **FNS + html-view are source of truth**; Telegraph images may break (hotlink).

## WeChat / anti-bot gotchas
- Empty or “环境异常” page → Ye not logged in / risk control; user must open tab in Ye first
- Lazy images use `data-src`; script scrolls + rewrites before dump
- CF 1010 on API if User-Agent is bare Python — script sets a Chrome UA
- Never paste Cookie / token into the note body
- Do not kill random Chrome; only close the tab the script opened (default)
- CDP race: `/json/new?url` can leave `about:blank`; script opens blank tab then `Page.navigate` and rejects weak dumps (`about:` / tiny HTML) before upload

## Eval (success)
- Given `https://example.com/`, script exits 0, JSON `ok:true`, non-empty `path`, `fnsOk:true`
- WeChat URL with visible `#js_content` in Ye → upload ok OR clear login/captcha error (no silent empty note)

## Near-miss / do-not-trigger
- “收藏这次会话” → conversation archive skill
- “帮我打开这个链接看看” without save intent → browse only
- Bulk URL list of easy sites → plain POST `/`, not browser
