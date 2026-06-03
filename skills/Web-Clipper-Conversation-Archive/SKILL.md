---
name: web-clipper-conversation-archive
description: Save project conversations through the deployed Web Clipper workflow at clip.yi.uy, using URL clipping or uploaded HTML snapshots, and organize the clipping intent as clip/<AI-or-Agent>/<project>. Use when the user asks to preserve AI/agent project dialogue, investigation notes, or session transcripts into the clipper/Obsidian workflow.
---

# Web Clipper Conversation Archive

Use this skill when the user wants to save a project conversation, agent session, or AI investigation log through the Web Clipper workflow deployed for `~/code/Clip/web-clipper`.

Verified project facts:

- Deployment address supplied by the user: `clip.yi.uy`.
- Project root inspected: `/Users/qing/code/Clip/web-clipper`.
- Worker routes verified from source/README/tests: `POST /`, `POST /upload-html`, `/telegram-webhook`, `/image-proxy`, and `/favicon.ico`.
- `POST /` body is JSON with `url` and uses Jina before the common clipping pipeline.
- `POST /upload-html` body is `multipart/form-data` with `singlehtmlfile` plus `url`; it skips Jina and parses uploaded HTML directly.
- Common pipeline generates Markdown/frontmatter, writes through FNS, and optionally pushes Telegraph/Telegram.
- Duplicate URL behavior is soft-update: existing note is found by URL, frontmatter/clip metadata is updated, and a clipping record is appended rather than creating a second note.
- Current code builds the FNS path as `${env.CLIP_FOLDER}/${YYYY-MM}/${timestamp}-${slug}.md`; it does **not** read a per-request `folder`, `path`, `agent`, or `project` field.
- Local tests previously passed: 4 files / 100 tests.

## Canonical Archive Intent

When saving project conversations, express the desired logical destination as:

```text
clip/<AI-or-Agent-name>/<project-name>
```

Examples:

```text
clip/GenericAgent/web-clipper
clip/Claude/SomeProject
clip/ChatGPT/SomeProject
```

Important limitation: with the currently verified Worker code, this folder convention is an archive **intent/convention** only unless the deployed Worker has been extended or configured accordingly. The verified source only writes under the deployment-level `CLIP_FOLDER/YYYY-MM/`. To physically create `clip/<AI-or-Agent>/<project>/...`, one of these must be true:

1. `CLIP_FOLDER` is set to the exact desired folder before clipping, or
2. the Worker is modified to accept and validate a per-request folder/path parameter, or
3. a post-processing/FNS move workflow is used after clipping.

Do not claim that dynamic per-project folders are supported until verified from code or a successful response path.

## Inputs To Collect

Before clipping a conversation, determine:

- `agent_name`: the AI/agent/session owner, e.g. `GenericAgent`, `Claude`, `ChatGPT`, `Qwen`.
- `project_name`: repository or project name, e.g. `web-clipper`.
- `source_url`: a stable URL for the conversation if one exists; otherwise synthesize a stable pseudo URL for the uploaded HTML, e.g. `https://conversation.local/<agent>/<project>/<YYYYMMDD-HHMMSS>`.
- `title`: include agent and project, e.g. `GenericAgent / web-clipper — 2026-05-28 project conversation`.
- `html_snapshot`: full rendered HTML for conversations that are not publicly accessible or that require login.
- `API_KEY`: must be supplied by the user or a safe runtime secret source. Never read `.dev.vars` or secret files just to discover it.

## Preferred Workflow For Project Conversations

Use `POST /upload-html` for AI/agent conversations because most chat/project sessions are login-gated or not extractable by Jina.

1. Convert the conversation/session transcript into a self-contained HTML document.
2. Include visible metadata at the top of the document:
   - title
   - agent name
   - project name
   - requested logical folder `clip/<agent>/<project>`
   - source URL or pseudo URL
   - clipping timestamp
3. Save the HTML as a temporary `.html` file.
4. Upload it to the clipper with `singlehtmlfile` and `url`.
5. Inspect the JSON response. Treat success as `ok: true`; record returned `path`, `mode`, `telegraphUrl`, and `telegramMessageId` if present.
6. If the returned `path` is only under `CLIP_FOLDER/YYYY-MM/`, do not pretend the dynamic folder was honored; note the returned physical path and the requested logical folder separately.

### cURL Template: Upload Conversation HTML

```bash
API_KEY='<provided-by-user-or-safe-secret-source>'
CLIP_BASE='https://clip.yi.uy'
HTML_FILE='/tmp/project-conversation.html'
SOURCE_URL='https://conversation.local/GenericAgent/web-clipper/20260528-120000'

curl -sS \
  -H "Authorization: Bearer ${API_KEY}" \
  -F "singlehtmlfile=@${HTML_FILE};type=text/html" \
  -F "url=${SOURCE_URL}" \
  "${CLIP_BASE}/upload-html"
```

Expected successful response shape:

```json
{
  "ok": true,
  "title": "...",
  "fnsOk": true,
  "mode": "created-or-updated",
  "path": "...",
  "telegraphOk": true,
  "telegraphUrl": "https://telegra.ph/...",
  "telegramMessageId": 123
}
```

`telegraphOk`, `telegraphUrl`, and `telegramMessageId` depend on deployment configuration and may be absent/false while FNS succeeds.

## URL-Only Workflow

Use `POST /` only when the conversation or project page has a public/stable URL that Jina can extract.

```bash
API_KEY='<provided-by-user-or-safe-secret-source>'
CLIP_BASE='https://clip.yi.uy'
TARGET_URL='https://example.com/project-note'

curl -sS \
  -H "Authorization: Bearer ${API_KEY}" \
  -H 'Content-Type: application/json' \
  -d "{\"url\":\"${TARGET_URL}\"}" \
  "${CLIP_BASE}/"
```

## HTML Snapshot Template

When generating the temporary HTML, use a simple, readable structure so Readability/singlefile parsing keeps the useful body:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>GenericAgent / web-clipper — project conversation</title>
  <meta property="og:url" content="https://conversation.local/GenericAgent/web-clipper/20260528-120000">
</head>
<body>
<article>
  <h1>GenericAgent / web-clipper — project conversation</h1>
  <p><strong>Requested folder:</strong> clip/GenericAgent/web-clipper</p>
  <p><strong>Source:</strong> https://conversation.local/GenericAgent/web-clipper/20260528-120000</p>
  <hr>
  <h2>Conversation</h2>
  <!-- render the transcript here, preserving roles, code blocks, commands, results, and decisions -->
</article>
</body>
</html>
```

## Verification And Failure Handling

- Probe before asserting deployment health. In the local environment on 2026-05-28, DNS resolved `clip.yi.uy` to `84.75.76.31`, but HTTPS probes failed with `LibreSSL SSL_connect: SSL_ERROR_SYSCALL` and HTTP returned an empty reply. Re-test from the active environment before concluding service status.
- `401` means missing/wrong `API_KEY`.
- `400` on `/upload-html` usually means missing/invalid `singlehtmlfile`, non-HTML filename, empty file, oversized file, or missing/invalid body.
- `502` can mean Jina failure for URL mode or FNS/Telegraph downstream failure.
- Do not retry blindly. After one network/API failure, capture status code, response body, and whether the request reached `clip.yi.uy`; after repeated TLS/network failures, ask the user to verify DNS/Cloudflare/Traefik/deployment exposure.

## Safety Constraints

- Do not read `.dev.vars`, Cloudflare secret files, keychains, or token files to obtain `API_KEY` unless the user explicitly instructs and policy allows it.
- Do not print full API keys in logs or final answers.
- Do not modify `/Users/qing/code/Clip/web-clipper` just to use this skill. If dynamic folder support is required, ask before editing that project and then add tests.
