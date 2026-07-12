---
name: web-clipper-conversation-archive
description: When the user explicitly says 收藏 (or asks to archive/save this AI/agent conversation into Obsidian via Web Clipper), tidy the dialogue and POST it to c.yi.uy (/upload-html or /save-md). Organize intent as clip/<AI-or-Agent>/<project>. Do not use for ordinary URL clipping, casual “save this link”, or non-conversation notes.
---

# Web Clipper Conversation Archive（收藏）

## When to load
- User clearly says **收藏**, or asks to archive/save **this conversation / agent session** into OB / clipper.
- Anti-triggers: bare URL clip only; “帮我记一下” without 收藏; editing notes already in vault; reading secrets.

## Required reads
- `memory/web_clipper_save_skill.md` for API shapes
- L2 `[WebClipper]` for live base URL and keychain name

## Verified facts
- Production base: `https://c.yi.uy` (not `clip.yi.uy`)
- Project root: `/Users/qing/code/clip/web-clipper`
- Auth: `Authorization: Bearer <API_KEY>`; local keychain entry `web_clipper_api_key` via `keys.web_clipper_api_key.use()` — never print the key
- Preferred for chat: `POST /upload-html` (multipart `singlehtmlfile` + `url`) because sessions are usually not public
- Alternative: `POST /save-md` JSON `{ title, content, tags?, html? }` when you only have Markdown
- Duplicate URL soft-updates existing FNS note (exact frontmatter `url:`)

## Canonical archive intent
Logical destination convention (CLIP_FOLDER may still be deployment-level `…/YYYY-MM/` unless configured):

```text
clip/<AI-or-Agent-name>/<project-name>
```

Examples: `clip/GenericAgent/web-clipper`, `clip/Claude/SomeProject`

## Workflow (run once per 收藏)
1. **Confirm trigger**: user said 收藏 / archive this conversation. If ambiguous, ask once.
2. **Tidy content**: keep decisions, commands, errors, file paths, outcomes; drop secrets, raw tokens, huge logs; add a short title + bullet summary at top.
3. **Build snapshot HTML** (default) with readable structure (see template below). Set:
   - `<title>` and `h1` = `{Agent} / {project} — conversation`
   - `og:url` / body Source = stable synthetic URL, e.g. `https://conversation.local/{Agent}/{project}/{YYYYMMDD-HHMMSS}`
   - include requested folder line `clip/...`
4. **Call Worker** (prefer upload-html):

```bash
BASE_URL='https://c.yi.uy'
# API_KEY from keychain / user — never echo
curl -sS -X POST "${BASE_URL}/upload-html" \
  -H "Authorization: Bearer ${API_KEY}" \
  -F "url=https://conversation.local/GenericAgent/project/20260712-120000" \
  -F "singlehtmlfile=@/tmp/conversation.html;type=text/html"
```

Or Markdown path:

```bash
curl -sS -X POST "${BASE_URL}/save-md" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  --data '{"title":"GenericAgent / project","content":"...","tags":["clip","conversation"]}'
```

5. **Report**: `ok`, `path`, `telegraphUrl` / `htmlViewUrl` if present. No token echo.
6. **Failures**:
   - `401` → wrong/missing API_KEY
   - `400` upload-html → bad/missing HTML field or size
   - `502` → Jina/FNS/Telegraph downstream; capture body once, do not blind-retry
   - After 2 network failures, stop and ask user to check deployment

## HTML template
```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>GenericAgent / web-clipper — project conversation</title>
  <meta property="og:url" content="https://conversation.local/GenericAgent/web-clipper/20260712-120000">
</head>
<body>
<article>
  <h1>GenericAgent / web-clipper — project conversation</h1>
  <p><strong>Requested folder:</strong> clip/GenericAgent/web-clipper</p>
  <p><strong>Source:</strong> https://conversation.local/GenericAgent/web-clipper/20260712-120000</p>
  <hr>
  <h2>Summary</h2>
  <ul><li>key decisions</li></ul>
  <h2>Conversation</h2>
  <!-- roles, code, commands, results -->
</article>
</body>
</html>
```

## Safety
- Never read `.dev.vars` / secret files just to discover API_KEY unless user explicitly allows and policy permits.
- Never modify `/Users/qing/code/clip/web-clipper` only to use this skill.
- Do not invent FNS paths; use response `path`.

## Should-trigger examples
- 「把这段对话收藏到 OB」
- 「收藏这次 web-clipper 排查会话」
- 「archive this agent session via clipper」

## Should-not-trigger examples
- 「帮我剪藏 https://example.com」（plain URL clip → save skill / bare link routing）
- 「总结一下刚才说了什么」（no archive）
- 「改一下 skill 文案」（authoring, not 收藏）
