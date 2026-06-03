#!/usr/bin/env python3
"""Conversation HTML Exporter: polished single-file HTML archives for AI chats."""
from __future__ import annotations
import argparse, base64, datetime as dt, html, json, os, re, sys, textwrap, urllib.request, urllib.error, mimetypes, subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROLE_ALIASES = {
    'human':'user','用户':'user','我':'user','user':'user','u':'user',
    'assistant':'assistant','agent':'assistant','ai':'assistant','机器人':'assistant','助手':'assistant',
    'system':'system','developer':'system','tool':'tool','function':'tool'
}
SECRET_PATTERNS = [
    (re.compile(r'(?i)(api[_-]?key|token|secret|password|passwd|authorization|bearer)\s*[:=]\s*([A-Za-z0-9_./+\-=]{8,})'), r'\1: [REDACTED]'),
    (re.compile(r'Bearer\s+[A-Za-z0-9_./+\-=]{12,}', re.I), 'Bearer [REDACTED]'),
    (re.compile(r'(?i)(sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,})'), '[REDACTED_TOKEN]'),
    (re.compile(r'(?i)(cookie\s*[:=]\s*)[^\n]{12,}'), r'\1[REDACTED_COOKIE]'),
    (re.compile(r'(?i)(GPlvtWhjJqvk6r2V5cYu5GrVlSalyHZr)'), '[REDACTED_WEBCLIPPER_KEY]'),
]

def redact(text: str) -> str:
    if text is None: return ''
    s = str(text)
    for pat, repl in SECRET_PATTERNS:
        s = pat.sub(repl, s)
    return s

def norm_role(role: str) -> str:
    r = (role or 'assistant').strip().lower()
    return ROLE_ALIASES.get(r, r if r in {'user','assistant','system','tool'} else 'assistant')

def load_messages(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = path.read_text(encoding='utf-8')
    meta: Dict[str, Any] = {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            meta = {k:v for k,v in data.items() if k != 'messages'}
            msgs = data.get('messages') or data.get('conversation') or data.get('turns') or []
        elif isinstance(data, list):
            msgs = data
        else:
            msgs = []
        out=[]
        for i,m in enumerate(msgs):
            if isinstance(m, dict):
                content = m.get('content', m.get('text', m.get('message','')))
                if isinstance(content, list):
                    content = '\n'.join(str(x.get('text',x)) if isinstance(x,dict) else str(x) for x in content)
                out.append({**m, 'role': norm_role(str(m.get('role','assistant'))), 'content': redact(str(content)), 'index': i+1})
            else:
                out.append({'role':'assistant','content':redact(str(m)), 'index': i+1})
        if out: return out, meta
    except Exception:
        pass
    return parse_transcript(raw), meta

def parse_transcript(raw: str) -> List[Dict[str, Any]]:
    lines = raw.splitlines()
    msgs=[]; role=None; buf=[]
    heading = re.compile(r'^\s*(?:#{1,4}\s*)?(?:\[)?(User|Assistant|Agent|System|Tool|Developer|用户|助手)(?:\])?\s*[:：]?\s*$', re.I)
    inline = re.compile(r'^\s*(User|Assistant|Agent|System|Tool|Developer|用户|助手)\s*[:：]\s*(.*)$', re.I)
    def flush():
        nonlocal buf, role
        if role is not None or buf:
            msgs.append({'role': norm_role(role or 'assistant'), 'content': redact('\n'.join(buf).strip()), 'index': len(msgs)+1})
        buf=[]
    for line in lines:
        m=heading.match(line)
        mi=inline.match(line)
        if m:
            flush(); role=m.group(1); continue
        if mi and len(line) < 200:
            flush(); role=mi.group(1); buf=[mi.group(2)] if mi.group(2) else []; continue
        buf.append(line)
    flush()
    return [m for m in msgs if m['content']]

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, TextLexer
    from pygments.formatters import HtmlFormatter
    PYGMENTS_CSS = HtmlFormatter(style='github-dark').get_style_defs('.highlight')
except Exception:
    highlight = None; HtmlFormatter = None; PYGMENTS_CSS = ''

def slugify(s: str, used: set) -> str:
    base = re.sub(r'[^\w\u4e00-\u9fff-]+','-',s.lower()).strip('-')[:60] or 'section'
    slug=base; n=2
    while slug in used:
        slug=f'{base}-{n}'; n+=1
    used.add(slug); return slug

def render_inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r'(?<!["\(>])(https?://[^\s<]+)', r'<a href="\1" target="_blank" rel="noopener">\1</a>', s)
    return s

def render_code(code: str, lang: str) -> str:
    lang = (lang or '').strip() or 'text'
    if highlight:
        try:
            lexer = get_lexer_by_name(lang, stripall=False)
        except Exception:
            lexer = TextLexer(stripall=False)
        body = highlight(code, lexer, HtmlFormatter(nowrap=False))
    else:
        body = f'<pre><code>{html.escape(code)}</code></pre>'
    return f'<div class="code-wrap" data-lang="{html.escape(lang)}"><button class="copy-code">复制代码</button>{body}</div>'

def render_markdown(md: str) -> Tuple[str, List[Tuple[int,str,str]]]:
    lines = md.splitlines(); out=[]; toc=[]; used=set(); i=0; in_code=False; code=[]; lang=''; in_ul=False; in_ol=False; in_bq=False
    def close_lists():
        nonlocal in_ul, in_ol, in_bq
        if in_ul: out.append('</ul>'); in_ul=False
        if in_ol: out.append('</ol>'); in_ol=False
        if in_bq: out.append('</blockquote>'); in_bq=False
    while i < len(lines):
        line=lines[i]
        if line.strip().startswith('```'):
            if not in_code:
                close_lists(); in_code=True; lang=line.strip()[3:].strip(); code=[]
            else:
                out.append(render_code('\n'.join(code), lang)); in_code=False; lang=''
            i+=1; continue
        if in_code:
            code.append(line); i+=1; continue
        if not line.strip():
            close_lists(); i+=1; continue
        hm=re.match(r'^(#{1,4})\s+(.+)$', line)
        if hm:
            close_lists(); level=len(hm.group(1)); title=re.sub(r'`|\*|_', '', hm.group(2)).strip(); slug=slugify(title, used); toc.append((level,title,slug)); out.append(f'<h{level} id="{slug}">{render_inline(title)}</h{level}>'); i+=1; continue
        if '|' in line and i+1 < len(lines) and re.match(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$', lines[i+1]):
            close_lists(); headers=[c.strip() for c in line.strip('|').split('|')]; i+=2; rows=[]
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip('|').split('|')]); i+=1
            out.append('<div class="table-scroll"><table><thead><tr>' + ''.join(f'<th>{render_inline(c)}</th>' for c in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join(f'<td>{render_inline(c)}</td>' for c in r)+'</tr>' for r in rows) + '</tbody></table></div>'); continue
        lm=re.match(r'^\s*[-*+]\s+(.+)$', line)
        om=re.match(r'^\s*\d+[.)]\s+(.+)$', line)
        if lm:
            if not in_ul: close_lists(); out.append('<ul>'); in_ul=True
            out.append(f'<li>{render_inline(lm.group(1))}</li>'); i+=1; continue
        if om:
            if not in_ol: close_lists(); out.append('<ol>'); in_ol=True
            out.append(f'<li>{render_inline(om.group(1))}</li>'); i+=1; continue
        if line.lstrip().startswith('>'):
            if not in_bq: close_lists(); out.append('<blockquote>'); in_bq=True
            out.append(f'<p>{render_inline(line.lstrip()[1:].strip())}</p>'); i+=1; continue
        close_lists(); out.append(f'<p>{render_inline(line)}</p>'); i+=1
    if in_code: out.append(render_code('\n'.join(code), lang))
    close_lists(); return '\n'.join(out), toc

def build_html(messages: List[Dict[str,Any]], title: str, meta: Dict[str,Any]) -> str:
    now = dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    rendered=[]; all_toc=[]
    counts={r:0 for r in ['user','assistant','system','tool']}
    for idx,m in enumerate(messages,1):
        role=norm_role(m.get('role','assistant')); counts[role]=counts.get(role,0)+1
        content=redact(m.get('content',''))
        body,toc=render_markdown(content)
        for level,t,slug in toc[:8]: all_toc.append((idx,level,t,slug,role))
        plain=html.escape(content[:12000])
        long_cls=' long' if len(content)>1200 else ''
        rendered.append(f'''<section class="msg {role}{long_cls}" data-role="{role}" data-index="{idx}" data-text="{html.escape(content.lower()[:4000])}">
  <div class="avatar">{html.escape({'user':'U','assistant':'A','system':'S','tool':'T'}.get(role,'A'))}</div>
  <article class="bubble">
    <header class="msg-head"><span class="role">{role.title()}</span><span class="idx">#{idx}</span><button class="copy-msg" data-plain="{plain}">复制</button><button class="toggle-msg">折叠</button></header>
    <div class="content markdown-body">{body}</div>
  </article>
</section>''')
    toc_html=''.join(f'<a class="toc-l{min(level,4)}" href="#msg-{i}" onclick="document.querySelector(\'[data-index=&quot;{i}&quot;]\').scrollIntoView()"><span>{i}</span> {html.escape(t)}</a>' for i,level,t,slug,role in all_toc[:120]) or '<span class="muted">无标题目录</span>'
    meta_items = ''.join(f'<span class="chip">{html.escape(str(k))}: {html.escape(str(v))}</span>' for k,v in meta.items() if k!='messages')
    css = CSS.replace('__PYGMENTS__', PYGMENTS_CSS)
    js = JS
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{css}</style></head>
<body><div class="app">
<aside class="side"><div class="brand">Conversation<br><b>HTML Exporter</b></div><nav>{toc_html}</nav></aside>
<main><header class="hero"><div><h1>{html.escape(title)}</h1><p>生成时间：{html.escape(now)} · 消息数：{len(messages)} · User {counts.get('user',0)} / Assistant {counts.get('assistant',0)} / Tool {counts.get('tool',0)}</p><div class="chips">{meta_items}</div></div>
<div class="actions"><button id="theme">明/暗</button><button id="collapseAll">全部折叠</button><button onclick="window.print()">打印/PDF</button></div></header>
<div class="toolbar"><input id="q" placeholder="搜索对话内容…"><label><input type="checkbox" class="rf" value="user" checked>用户</label><label><input type="checkbox" class="rf" value="assistant" checked>助手</label><label><input type="checkbox" class="rf" value="system" checked>系统</label><label><input type="checkbox" class="rf" value="tool" checked>工具</label></div>
<div id="conversation">{''.join(rendered)}</div><footer>Generated by conversation_html_exporter · secrets redacted before rendering</footer></main></div><script>{js}</script></body></html>'''

CSS = r'''
:root{--bg:#f6f7fb;--panel:#ffffff;--text:#172033;--muted:#64748b;--line:#e2e8f0;--accent:#6366f1;--user:#e0f2fe;--assistant:#fff;--system:#fef3c7;--tool:#ecfccb;--code:#0f172a;--shadow:0 18px 50px rgba(15,23,42,.10)}
[data-theme=dark]{--bg:#0b1020;--panel:#111827;--text:#e5e7eb;--muted:#94a3b8;--line:#273449;--accent:#8b5cf6;--user:#082f49;--assistant:#111827;--system:#422006;--tool:#1a2e05;--code:#020617;--shadow:0 18px 50px rgba(0,0,0,.35)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,rgba(99,102,241,.18),transparent 32rem),var(--bg);color:var(--text);font:16px/1.62 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.app{display:grid;grid-template-columns:280px 1fr;min-height:100vh}.side{position:sticky;top:0;height:100vh;overflow:auto;padding:24px;border-right:1px solid var(--line);background:color-mix(in srgb,var(--panel) 84%,transparent);backdrop-filter:blur(18px)}.brand{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:24px}.brand b{font-size:18px;color:var(--text);letter-spacing:0}nav a{display:block;padding:8px 10px;margin:3px 0;border-radius:10px;color:var(--muted);text-decoration:none;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}nav a:hover{background:rgba(99,102,241,.12);color:var(--accent)}.toc-l3{padding-left:22px}.toc-l4{padding-left:34px}main{max-width:1080px;width:100%;margin:0 auto;padding:32px}.hero{display:flex;gap:18px;justify-content:space-between;align-items:flex-start;margin-bottom:18px;padding:28px;border:1px solid var(--line);border-radius:28px;background:linear-gradient(135deg,color-mix(in srgb,var(--panel) 92%,transparent),color-mix(in srgb,var(--accent) 10%,var(--panel)));box-shadow:var(--shadow)}h1{font-size:34px;line-height:1.1;margin:0 0 8px}.hero p,.muted{color:var(--muted);margin:0}.chips{margin-top:12px}.chip{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 10px;margin:4px 5px 0 0;color:var(--muted);font-size:12px}.actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.toolbar{position:sticky;top:0;z-index:5;display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:18px 0;padding:12px 14px;border:1px solid var(--line);border-radius:18px;background:color-mix(in srgb,var(--panel) 90%,transparent);backdrop-filter:blur(12px)}input#q{flex:1;min-width:220px;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:12px;padding:10px 12px}button{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:12px;padding:8px 12px;cursor:pointer}button:hover{border-color:var(--accent);color:var(--accent)}.msg{display:grid;grid-template-columns:48px 1fr;gap:14px;margin:18px 0;scroll-margin-top:96px}.avatar{width:42px;height:42px;border-radius:16px;display:grid;place-items:center;font-weight:800;background:var(--accent);color:white;box-shadow:var(--shadow)}.bubble{border:1px solid var(--line);border-radius:22px;background:var(--assistant);box-shadow:0 8px 24px rgba(15,23,42,.06);overflow:hidden}.msg.user .bubble{background:var(--user)}.msg.system .bubble{background:var(--system)}.msg.tool .bubble{background:var(--tool)}.msg-head{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid var(--line);color:var(--muted);font-size:13px}.role{font-weight:800;color:var(--text)}.idx{margin-right:auto}.content{padding:18px 20px}.collapsed .content{max-height:72px;overflow:hidden;mask-image:linear-gradient(#000 45%,transparent)}.hidden{display:none!important}.markdown-body h1,.markdown-body h2,.markdown-body h3,.markdown-body h4{margin:1.2em 0 .5em;line-height:1.25}.markdown-body h1{font-size:1.65em}.markdown-body h2{font-size:1.35em}.markdown-body h3{font-size:1.15em}.markdown-body p{margin:.65em 0}.markdown-body a{color:var(--accent)}.markdown-body code{background:rgba(99,102,241,.12);padding:.14em .35em;border-radius:6px}.code-wrap{position:relative;margin:14px 0;background:var(--code);border-radius:16px;overflow:hidden;border:1px solid var(--line)}.code-wrap:before{content:attr(data-lang);position:absolute;top:8px;left:12px;color:#94a3b8;font-size:12px}.copy-code{position:absolute;right:8px;top:6px;z-index:2;background:#1e293b;color:#e2e8f0;border-color:#334155}.highlight,pre{margin:0;padding:38px 16px 16px;overflow:auto;background:var(--code)!important;color:#e2e8f0}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid var(--line);padding:8px 10px;text-align:left}blockquote{border-left:4px solid var(--accent);margin:12px 0;padding:4px 14px;color:var(--muted);background:rgba(99,102,241,.08);border-radius:0 12px 12px 0}mark{background:#facc15;color:#111827;border-radius:4px;padding:0 2px}footer{text-align:center;color:var(--muted);padding:34px}__PYGMENTS__
@media(max-width:860px){.app{display:block}.side{display:none}main{padding:16px}.hero{display:block}.actions{justify-content:flex-start;margin-top:14px}.msg{grid-template-columns:1fr}.avatar{display:none}}
@media print{.side,.toolbar,.actions,.copy-msg,.toggle-msg,.copy-code{display:none!important}body{background:#fff;color:#111}.app{display:block}main{max-width:none;padding:0}.bubble,.hero{box-shadow:none;break-inside:avoid}.content{max-height:none!important;overflow:visible!important;mask-image:none!important}}
'''
JS = r'''
const root=document.documentElement; if(localStorage.convTheme) root.dataset.theme=localStorage.convTheme;
document.getElementById('theme').onclick=()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';localStorage.convTheme=root.dataset.theme};
document.querySelectorAll('.toggle-msg').forEach(b=>b.onclick=()=>b.closest('.msg').classList.toggle('collapsed'));
document.getElementById('collapseAll').onclick=()=>{const any=[...document.querySelectorAll('.msg')].some(m=>!m.classList.contains('collapsed'));document.querySelectorAll('.msg').forEach(m=>m.classList.toggle('collapsed',any))};
async function copyText(t){try{await navigator.clipboard.writeText(t)}catch(e){const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove()}}
document.querySelectorAll('.copy-msg').forEach(b=>b.onclick=()=>copyText(b.dataset.plain||b.closest('.msg').innerText));
document.querySelectorAll('.copy-code').forEach(b=>b.onclick=()=>copyText(b.parentElement.innerText.replace(/^复制代码\n?/,'').replace(/^\w+\n/,'')));
function applyFilter(){const q=document.getElementById('q').value.trim().toLowerCase();const roles=new Set([...document.querySelectorAll('.rf:checked')].map(x=>x.value));document.querySelectorAll('.msg').forEach(m=>{const ok=roles.has(m.dataset.role)&&(!q||(m.dataset.text||m.innerText.toLowerCase()).includes(q));m.classList.toggle('hidden',!ok)})}
document.getElementById('q').addEventListener('input',applyFilter);document.querySelectorAll('.rf').forEach(x=>x.addEventListener('change',applyFilter));
'''

def upload_webclipper(html_path: Path, base_url: str, source_url: str='conversation://local') -> Dict[str,Any]:
    """Upload via the already-verified WebClipper project endpoint.

    Use curl multipart instead of urllib: the deployed Worker/Cloudflare path has
    already been validated with curl, while Python urllib may trigger CF 1010.
    Never print the token or command line.
    """
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo/'memory'))
    from keychain import keys  # type: ignore
    token = keys.web_clipper_api_key.use()
    endpoint = base_url.rstrip('/') + '/upload-html'
    cmd = [
        'curl', '-sS', '-X', 'POST', endpoint,
        '-H', 'Authorization: Bearer ' + token,
        '-F', 'url=' + source_url,
        '-F', f'singlehtmlfile=@{str(html_path)};type=text/html',
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if cp.returncode != 0:
            return {'ok': False, 'status': 'curl_failed', 'error': cp.stderr[:1000]}
        try:
            return json.loads(cp.stdout)
        except json.JSONDecodeError:
            return {'ok': False, 'status': 'bad_json', 'error': cp.stdout[:1000]}
    except Exception as e:
        return {'ok': False, 'status': 'exception', 'error': str(e)[:1000]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input','-i',required=True); ap.add_argument('--output','-o',required=True)
    ap.add_argument('--title','-t',default='AI 对话存档'); ap.add_argument('--meta',action='append',default=[],help='key=value metadata')
    ap.add_argument('--upload-webclipper',action='store_true'); ap.add_argument('--base-url',default='https://c.yi.uy'); ap.add_argument('--source-url',default='conversation://local')
    args=ap.parse_args(); inp=Path(args.input); out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    messages, meta=load_messages(inp); meta.update(dict(x.split('=',1) for x in args.meta if '=' in x))
    if not messages: raise SystemExit('No messages parsed')
    title = str(meta.get('title') or args.title)
    doc=build_html(messages,title,meta); out.write_text(doc,encoding='utf-8')
    print(json.dumps({'ok':True,'output':str(out),'messages':len(messages),'bytes':out.stat().st_size},ensure_ascii=False))
    if args.upload_webclipper:
        res=upload_webclipper(out,args.base_url,args.source_url)
        safe={k:v for k,v in res.items() if 'token' not in k.lower() and 'key' not in k.lower()}
        print(json.dumps({'webclipper':safe},ensure_ascii=False))
if __name__=='__main__': main()
