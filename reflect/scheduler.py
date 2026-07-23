import os, sys, json, time as _time, socket as _socket, logging, re, subprocess
from datetime import datetime, timedelta

# 端口锁：防止重复启动，bind失败时agentmain会直接崩溃退出
# reload时mod.__dict__保留_lock，跳过重复绑定
try: _lock
except NameError:
    _lock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    _lock.bind(('127.0.0.1', 45762)); _lock.listen(1)

INTERVAL = 120
ONCE = False

_dir = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(_dir, '../sche_tasks')
DONE  = os.path.join(_dir, '../sche_tasks/done')
_LOG  = os.path.join(_dir, '../sche_tasks/scheduler.log')

os.makedirs(DONE, exist_ok=True)
_logger = logging.getLogger('scheduler')
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(_LOG, encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s',
                                        datefmt='%Y-%m-%d %H:%M'))
    _logger.addHandler(_fh)

# 默认最大延迟窗口（小时），超过此时间不触发
DEFAULT_MAX_DELAY = 6
_l4_t = 0  # last L4 archive time

def _parse_cooldown(repeat):
    """解析repeat为冷却时间(比实际周期略短,防漂移)"""
    if repeat == 'once': return timedelta(days=999999)
    if repeat in ('daily', 'weekday'): return timedelta(hours=20)
    if repeat == 'weekly': return timedelta(days=6)
    if repeat == 'monthly': return timedelta(days=27)
    if repeat.startswith('every_'):
        try:
            parts = repeat.split('_')
            n = int(parts[1].rstrip('hdm'))
            u = parts[1][-1]
            if u == 'h': return timedelta(hours=n)
            if u == 'm': return timedelta(minutes=n)
            if u == 'd': return timedelta(days=n)
        except (ValueError, IndexError):
            pass  # fall through to warning below
    _logger.warning(f'Unknown repeat type: {repeat}, fallback to 20h cooldown')
    return timedelta(hours=20)

def _last_run(tid, done_files):
    """找最近一次执行时间"""
    latest = None
    for df in done_files:
        if not df.endswith(f'_{tid}.md'): continue
        try:
            t = datetime.strptime(df[:15], '%Y-%m-%d_%H%M')
            if latest is None or t > latest: latest = t
        except: continue
    return latest

def check():
    # L4 archive cron (silent, every 12h)
    global _l4_t
    if _time.time() - _l4_t > 43200:
        _l4_t = _time.time()
        try:
            import sys; sys.path.insert(0, os.path.join(_dir, '../memory/L4_raw_sessions'))
            from compress_session import batch_process
            raw_dir = os.path.join(_dir, '../temp/model_responses')
            r = batch_process(raw_dir, dry_run=False)
            print(f'[L4 cron] {r}')
        except Exception as e:
            _logger.error(f'L4 archive failed: {e}')

    if not os.path.isdir(TASKS): return None
    now = datetime.now()
    os.makedirs(DONE, exist_ok=True)
    done_files = set(os.listdir(DONE))
    for f in sorted(os.listdir(TASKS)):
        if not f.endswith('.json'): continue
        tid = f[:-5]
        try:
            with open(os.path.join(TASKS, f), encoding='utf-8') as fp:
                task = json.loads(fp.read())
        except Exception as e:
            _logger.error(f'JSON parse error for {f}: {e}')
            continue
        if not task.get('enabled', False): continue
        
        repeat = task.get('repeat', 'daily')
        sched = task.get('schedule', '00:00')
        try:
            h, m = map(int, sched.split(':'))
        except Exception as e:
            _logger.error(f'Invalid schedule format in {f}: {sched!r} ({e})')
            continue
        
        # weekday任务：周末跳过
        if repeat == 'weekday' and now.weekday() >= 5: continue
        
        # 还没到schedule时间就跳过
        if now.hour < h or (now.hour == h and now.minute < m): continue
        
        # 执行窗口检查：超过max_delay小时则跳过（防止开机太晚触发过时任务）
        max_delay = task.get('max_delay_hours', DEFAULT_MAX_DELAY)
        sched_minutes = h * 60 + m
        now_minutes = now.hour * 60 + now.minute
        if (now_minutes - sched_minutes) > max_delay * 60:
            _logger.info(f'SKIP {tid}: {now_minutes - sched_minutes}min past schedule, '
                         f'exceeds max_delay={max_delay}h')
            continue
        
        # 检查冷却
        last = _last_run(tid, done_files)
        cooldown = _parse_cooldown(repeat)
        if last and (now - last) < cooldown: continue
        
        # 触发
        _logger.info(f'TRIGGER {tid} (repeat={repeat}, schedule={sched}, '
                     f'last_run={last})')
        ts = now.strftime('%Y-%m-%d_%H%M')
        rpt = os.path.join(DONE, f'{ts}_{tid}.md')
        prompt = task.get('prompt', '')
        # opt-in per-task model: agentmain reflect loop parses a leading
        # "[LLM] <name>" line, switches backend for this task, then restores.
        llm = str(task.get('llm', '')).strip()
        llm_line = f'[LLM] {llm}\n' if llm else ''
        return (f'{llm_line}'
                f'[定时任务] {tid}\n'
                f'[报告路径] {rpt}\n\n'
                f'先读 scheduled_task_sop 了解执行流程，然后执行以下任务：\n\n'
                f'{prompt}\n\n'
                f'完成后将执行报告写入 {rpt}。')

    return None


def _extract_report_path(text):
    match = re.search(r'\[报告路径\]\s*(.+)', text or '')
    if match:
        path = match.group(1).strip()
        if path and os.path.exists(path):
            return path
    # Fallback: latest recently written scheduler report.
    try:
        files = [os.path.join(DONE, f) for f in os.listdir(DONE) if f.endswith('.md')]
        files = [p for p in files if os.path.isfile(p)]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        if files and (_time.time() - os.path.getmtime(files[0])) < 3600:
            return files[0]
    except Exception as e:
        _logger.error(f'find latest report failed: {e}')
    return None


def _short_text(text, limit=3600):
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit - 80].rstrip() + '\n\n...[truncated, see attached report if available]'


def _resolve_notify_python(root):
    """Prefer project venv so notify has requests/telegram; never bare brew python."""
    candidates = [
        os.path.join(root, '.venv', 'bin', 'python3'),
        os.path.join(root, '.venv', 'bin', 'python'),
        getattr(sys, 'executable', '') or '',
        '/opt/homebrew/bin/python3',
        '/usr/bin/python3',
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _telegram_notify(text, report_path=None):
    root = os.path.abspath(os.path.join(_dir, '..'))
    pybin = _resolve_notify_python(root)
    if not pybin:
        _logger.warning('Telegram notify skipped: no usable python found')
        return
    payload = json.dumps({'text': text or '', 'report_path': report_path or '', 'root': root}, ensure_ascii=False)
    script = r'''
import os, sys, json, asyncio
payload = json.loads(sys.stdin.read())
root = payload.get('root') or os.getcwd()
for p in (root, os.path.join(root, 'frontends')):
    if p not in sys.path:
        sys.path.insert(0, p)
from llmcore import mykeys
from telegram import Bot

def short_text(text, limit=3600):
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit - 80].rstrip() + '\n\n...[truncated, see attached report if available]'

async def main():
    token = mykeys.get('tg_bot_token')
    chat_ids = mykeys.get('tg_allowed_users', []) or []
    if not token or not chat_ids:
        print('missing telegram config')
        return
    bot = Bot(token=token)
    report_path = payload.get('report_path') or ''
    body = '✅ GenericAgent 定时任务完成\n\n' + short_text(payload.get('text') or '')
    for chat_id in chat_ids:
        await bot.send_message(chat_id=chat_id, text=body, disable_web_page_preview=True)
        if report_path and os.path.exists(report_path):
            with open(report_path, 'rb') as fp:
                await bot.send_document(chat_id=chat_id, document=fp, filename=os.path.basename(report_path), caption='定时任务报告')
    print(f'sent to {len(chat_ids)} chat(s); report={bool(report_path and os.path.exists(report_path))}')
asyncio.run(main())
'''
    cp = subprocess.run([pybin, '-c', script], input=payload, text=True, cwd=root,
                        capture_output=True, timeout=120)
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or '').strip() or f'notify subprocess rc={cp.returncode}')
    _logger.info('Telegram notify subprocess: ' + (cp.stdout.strip() or 'ok'))


def on_done(result):
    """Reflect hook: push completed scheduler result to the existing Telegram bot."""
    report_path = _extract_report_path(result)
    try:
        _telegram_notify(result, report_path=report_path)
        _logger.info(f'Telegram notify sent report={report_path or "<none>"}')
    except Exception as e:
        _logger.error(f'Telegram notify failed: {type(e).__name__}: {e}')