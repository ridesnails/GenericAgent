---
name: conversation-html-exporter
description: Convert AI conversation transcripts from JSON/Markdown/text into polished single-file HTML archives, with redaction, code highlighting, TOC, search, role filters, collapsible messages, copy buttons, print styles, and optional WebClipper upload.
---

# Conversation HTML Exporter

Use when the user asks to save/export/beautify an AI conversation as HTML.

## Main command

```bash
python3 exporter.py --input conversation.json --output out/conversation.html --title "AI 对话存档"
```

Input may be:
- JSON array: `[{'role':'user','content':'...'}]`
- JSON object: `{'messages':[...], 'title':'...'}`
- Markdown/text transcript with role headings such as `## User`, `[Assistant]`, `USER:`

## WebClipper upload

```bash
python3 exporter.py --input conversation.json --output out/conversation.html --upload-webclipper
```

The uploader uses `../memory/keychain.py` key `web_clipper_api_key` and never prints the raw key. Default base URL is `https://c.yi.uy`.

## Features

- automatic secret redaction before rendering
- self-contained single HTML file
- Markdown-ish rendering: headings, lists, blockquotes, tables, fenced code, inline code, links
- Pygments highlighting if installed, otherwise safe plain code blocks
- light/dark theme toggle
- full-text search
- role filters
- collapsible long messages and collapse-all button
- copy buttons for message text and code blocks
- generated table of contents from headings
- print/PDF-friendly CSS
- mobile responsive layout

## Safety

Always redact secrets before upload. Do not print API keys or raw credentials.
