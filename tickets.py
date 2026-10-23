#!/usr/bin/env python3
"""Ticket tool. One markdown file per ticket in .tickets/ (open) or .tickets/done/ (finished).
Each file starts with a frontmatter block (status, difficulty, size, blocked_by).
  tickets.py new "Title" [-d 1|2|3] [-s S|M|L] [-b T1,T2]   create the next ticket
  tickets.py list [<status>] [--all]                         print the tickets (only that status if given)
  tickets.py show T12                                        print one ticket file
  tickets.py set T12 <status>                                change status (done moves the file to done/)
  tickets.py done T12 [T13 ...] [--commit <hash>]            same as set <id> done
  tickets.py board                                           write board.html (filters, search, details)
  tickets.py sync                                            commit .tickets/, then pull and push if it has a remote
  tickets.py commit-hook                                     post-commit: finishes the tickets named in the subject
Optional .tickets/config.json: {"title": "...", "id_prefix": "T" (letters), "statuses": [[key, label, colour], ...]}
  id_prefix may be a list (["T", "L"]): `new` uses the first, or $TICKETS_PREFIX.
  "auto_commit" (default true): after new, set, done and the hook, commit .tickets/ in its own repo (never pushes).
  "mode": "chain" (default) or "validate". Other keys ("roles", "worktrees", "worktree_dir") are read by agents, not here."""
from __future__ import annotations

import argparse
import contextlib
import getpass
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

fcntl: Any
try:
    import fcntl
except ImportError:   # no fcntl (Windows): locked() does nothing there
    fcntl = None

Ticket = Dict[str, Any]

HERE = os.path.dirname(os.path.abspath(__file__))
DONE_DIR = os.path.join(HERE, 'done')

DEFAULT_STATUSES = [
    ['doing', 'Doing', '#7c8cff'],
    ['ready', 'Ready', '#4ea1ff'],
    ['open', 'Open', '#f0b429'],
    ['blocked', 'Blocked', '#e5534b'],
    ['parked', 'Parked', '#e5873f'],
    ['done', 'Done', '#3fb950'],
]
DIFF_ICON = {'1': '🟢', '2': '🟡', '3': '🔴'}


def read(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read()


def write(path: str, text: str) -> None:
    # write beside it, then replace: a failed write keeps the old file. mkstemp: a new random name, never a planted symlink
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=os.path.basename(path) + '.', suffix='.tmp')
    try:
        with open(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        mask = os.umask(0); os.umask(mask)
        os.chmod(tmp, 0o666 & ~mask)   # mkstemp makes it 0600; a normal file follows the umask
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp):
            os.remove(tmp)
        raise


@contextlib.contextmanager
def locked() -> Iterator[None]:
    """One writer at a time: every change to ticket files runs inside this. Not re-entrant, never nest it.
    The kernel drops the flock when the process ends, so a dead process never leaves a stale lock behind."""
    if fcntl is None:
        yield
        return
    with open(os.path.join(HERE, '.lock'), 'a') as f:   # the file stays; only the flock matters
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def load_config() -> Dict[str, Any]:
    p = os.path.join(HERE, 'config.json')
    try:
        c = json.loads(read(p)) if os.path.exists(p) else {}
    except (ValueError, OSError) as e:
        sys.exit('config.json: cannot read (%s)' % e)
    if not isinstance(c, dict):
        sys.exit('config.json: must be a JSON object')
    c.setdefault('title', os.path.basename(os.path.dirname(HERE)) or 'Project')
    c.setdefault('id_prefix', 'T')
    c.setdefault('statuses', DEFAULT_STATUSES)
    c.setdefault('auto_commit', True)
    c.setdefault('mode', 'chain')
    if c['mode'] not in ('chain', 'validate'):
        sys.exit('config.json: mode must be "chain" or "validate", got %r' % (c['mode'],))
    if not isinstance(c['statuses'], list) or not all(isinstance(s, list) and len(s) == 3 for s in c['statuses']):
        sys.exit('config.json: statuses must be a list of [key, label, colour]')
    keys = [s[0] for s in c['statuses']]
    if 'done' not in keys:
        sys.exit('config.json: statuses must contain "done"')
    if 'blocked' not in keys:   # tickets waiting for blockers need it: added before done
        c['statuses'] = c['statuses'][:keys.index('done')] + [['blocked', 'Blocked', '#e5534b']] + c['statuses'][keys.index('done'):]
    prefixes = c['id_prefix'] if isinstance(c['id_prefix'], list) else [c['id_prefix']]
    if not prefixes or not all(isinstance(p, str) and re.fullmatch('[A-Za-z]+', p) for p in prefixes):
        sys.exit('config.json: id_prefix must be letters only (or a list of them), got %r' % (c['id_prefix'],))
    return c


CFG = load_config()
PREFIXES = CFG['id_prefix'] if isinstance(CFG['id_prefix'], list) else [CFG['id_prefix']]
PREFIX = '(?:%s)' % '|'.join(map(re.escape, PREFIXES))
# key -> (label, order, colour); a colour that is not #hex falls back to grey (it goes into a style attribute)
STATUS = {s[0]: (s[1], i, s[2] if re.fullmatch(r'#[0-9a-fA-F]{3,8}', str(s[2])) else '#8b949e') for i, s in enumerate(CFG['statuses'])}
FIRST = 'open' if 'open' in STATUS else next((k for k in STATUS if k not in ('blocked', 'done')), 'done')   # status of a new ticket
ID_RE = re.compile(r'\b%s\d+[a-z]?\b' % PREFIX)
FILE_RE = re.compile(r'^(%s\d+[a-z]?)(?:-.*)?\.md$' % PREFIX)
FM_RE = re.compile(r'\A---\n(.*?)\n---[ \t]*\n?(.*)\Z', re.S)


# ---------- reading and writing ticket files

def split_fm(text: str) -> Tuple[Dict[str, str], str]:
    m = FM_RE.match(text)
    if not m:
        return {}, text
    meta: Dict[str, str] = {}
    for line in m.group(1).split('\n'):
        k, sep, v = line.partition(':')
        if sep and k.strip():
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def read_ticket(path: str, in_done: bool) -> Optional[Ticket]:
    m = FILE_RE.match(os.path.basename(path))
    if not m or os.path.islink(path) or not os.path.isfile(path):   # symlinks could point outside .tickets/
        return None
    try:
        meta, body = split_fm(read(path))
    except (UnicodeDecodeError, OSError) as e:
        print('tickets: skipping %s: %s' % (path, e), file=sys.stderr)
        return None
    body = body.strip()
    title = meta.get('title') or next((line[2:].strip() for line in body.split('\n') if line.startswith('# ')), m.group(1))
    status = 'done' if in_done else meta.get('status', FIRST)
    if status not in STATUS:
        status = FIRST
    return {'id': m.group(1), 'path': path, 'title': title, 'status': status,
            'difficulty': meta.get('difficulty') if meta.get('difficulty') in DIFF_ICON else '',
            'size': meta.get('size', '').upper() if meta.get('size', '').upper() in ('S', 'M', 'L') else '',
            'blocked_by': ID_RE.findall(meta.get('blocked_by', '')),
            'note': meta.get('commit', ''), 'by': meta.get('by', ''), 'body': body}


def all_tickets() -> List[Ticket]:
    out: List[Ticket] = []
    seen: Dict[str, str] = {}
    for d, in_done in ((HERE, False), (DONE_DIR, True)):
        if os.path.isdir(d) and not os.path.islink(d):
            for f in sorted(os.listdir(d)):
                if t := read_ticket(os.path.join(d, f), in_done):
                    if t['id'] in seen:
                        sys.exit('duplicate ticket id %s: %s and %s' % (t['id'], seen[t['id']], t['path']))
                    seen[t['id']] = t['path']
                    out.append(t)
    return out


def num(t: Ticket) -> Tuple[int, str]:
    m = re.search(r'(\d+)([a-z]?)$', t['id'])
    assert m
    return (int(m.group(1)), m.group(2))


def set_meta(path: str, updates: Dict[str, str]) -> None:
    text = read(path)
    m = FM_RE.match(text)
    lines, body = (m.group(1).split('\n'), m.group(2)) if m else ([], text)
    for k, v in updates.items():
        hits = [i for i, line in enumerate(lines) if line.partition(':')[0].strip() == k]
        if hits:
            lines[hits[0]] = '%s: %s' % (k, v)
            lines = [line for i, line in enumerate(lines) if i not in hits[1:]]   # later duplicates would win when parsed
        else:
            lines.append('%s: %s' % (k, v))
    write(path, '---\n' + '\n'.join(lines) + '\n---\n' + body)


def set_status(ids: List[str], status: str, commit: str = '') -> List[str]:
    """Change the status of each ticket; done moves the file into done/, anything else moves it back. Returns the ids changed."""
    if status not in STATUS:
        sys.exit('unknown status %r (known: %s)' % (status, ', '.join(STATUS)))
    if status == 'done' and os.path.islink(DONE_DIR):
        sys.exit('%s is a symlink: refusing to move tickets through it' % DONE_DIR)
    if status == 'done' and os.path.exists(DONE_DIR) and not os.path.isdir(DONE_DIR):
        sys.exit('%s is not a folder: nothing changed' % DONE_DIR)
    with locked():
        by_id = {t['id']: t for t in all_tickets()}
        changed = []
        for tid in dict.fromkeys(ids):   # once each: a second pass would use the old path
            t = by_id.get(tid)
            if not t:
                print('unknown ticket id: ' + tid, file=sys.stderr)
                continue
            upd = {'status': status}
            if status == 'doing':
                upd['by'] = who()
            if status == 'done':
                upd['done'] = time.strftime('%Y-%m-%d')
                if commit:
                    upd['commit'] = commit
            dest = os.path.join(DONE_DIR if status == 'done' else HERE, os.path.basename(t['path']))
            if dest != t['path'] and os.path.exists(dest):
                sys.exit('%s already exists: not overwritten' % dest)
            if dest != t['path']:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
            old = read(t['path'])
            set_meta(t['path'], upd)
            if dest != t['path']:
                try:
                    os.rename(t['path'], dest)
                except OSError:
                    write(t['path'], old)   # a failed move keeps the old status
                    raise
            changed.append(tid)
    return changed


def who() -> str:
    r = subprocess.run(['git', '-C', os.path.dirname(HERE), 'config', 'user.name'], capture_output=True, text=True)
    return r.stdout.strip() or getpass.getuser()


def new_ticket(title: str, difficulty: Optional[str], size: Optional[str], blocked_by: str) -> Tuple[str, str]:
    ids = ID_RE.findall(blocked_by)
    if blocked_by.strip() and not ids:
        sys.exit('-b: no valid ticket id in %r' % blocked_by)
    with locked():
        prefix = os.environ.get('TICKETS_PREFIX') or PREFIXES[0]
        if prefix not in PREFIXES:
            sys.exit('TICKETS_PREFIX %r is not in config.json id_prefix %s' % (prefix, PREFIXES))
        own = re.compile(r'%s(\d+)[a-z]?' % re.escape(prefix))
        # from file names, not read tickets: an unreadable ticket still holds its number
        names = [f for d in (HERE, DONE_DIR) if os.path.isdir(d) and not os.path.islink(d) for f in os.listdir(d)]
        nums = [int(m.group(1)) for f in names if (fm := FILE_RE.match(f)) and (m := own.fullmatch(fm.group(1)))]
        tid = '%s%d' % (prefix, max(nums, default=0) + 1)
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:50]
        path = os.path.join(HERE, '%s-%s.md' % (tid, slug) if slug else tid + '.md')
        fm = ['title: ' + re.sub(r'[\r\n]+', ' ', title), 'status: ' + FIRST]
        if difficulty:
            fm.append('difficulty: ' + difficulty)
        if size:
            fm.append('size: ' + size.upper())
        if ids:
            fm.append('blocked_by: ' + ', '.join(ids))
        fm.append('created: ' + time.strftime('%Y-%m-%d'))
        try:
            with open(path, 'x', encoding='utf-8') as f:
                f.write('---\n' + '\n'.join(fm) + '\n---\n\n## Do\n\n\n## Done when\n\n')
        except FileExistsError:
            sys.exit('%s already exists: not overwritten' % path)
        return tid, path


def effective(t: Ticket, by_id: Dict[str, Ticket]) -> Tuple[str, List[str]]:
    """(status key, ids still waited for). A ticket with unfinished blockers shows as blocked."""
    waiting = [b for b in t['blocked_by'] if b not in by_id or by_id[b]['status'] != 'done']   # an unknown id still blocks
    if waiting and t['status'] in ('open', 'ready'):
        return 'blocked', waiting
    return t['status'], waiting


# ---------- board

def board() -> None:
    with locked():   # read and write under the lock: an older board never overwrites a newer one
        write_board()


def write_board() -> None:
    ts = all_tickets()
    by_id = {t['id']: t for t in ts}
    rows: List[str] = []
    counts = dict.fromkeys(STATUS, 0)
    for t in sorted(ts, key=lambda t: (STATUS[effective(t, by_id)[0]][1], -num(t)[0] if t['status'] == 'done' else num(t)[0])):
        key, waiting = effective(t, by_id)
        counts[key] += 1
        label, _, col = STATUS[key]
        wait = ('waits for ' + ', '.join(waiting)) if waiting else ', '.join(t['blocked_by'])
        rows.append(
            f'<tr class="r" data-k="{html.escape(key)}" data-q="{html.escape((t["id"] + " " + t["title"]).lower())}">'
            f'<td class="id">{html.escape(t["id"])}</td><td>{DIFF_ICON.get(t["difficulty"], "")}</td><td>{html.escape(t["size"])}</td>'
            f'<td class="ti">{html.escape(t["title"])}'
            f'<details><summary>details</summary><pre>{html.escape(t["body"])}</pre></details></td>'
            f'<td><span class="b" style="--c:{html.escape(col)}">{html.escape(label)}</span></td>'
            f'<td class="sm">{html.escape(wait or ("by " + t["by"] if key == "doing" and t["by"] else t["note"]))}</td></tr>')
    chips =''.join(f'<button class="chip" data-k="{html.escape(k)}" style="--c:{html.escape(v[2])}">{html.escape(v[0])} <b>{counts[k]}</b></button>'
                    for k, v in STATUS.items())
    title = html.escape(CFG['title'])
    shown = json.dumps([k for k in STATUS if k != 'done']).replace('</', '<\\/')   # no </script> breakout
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>{title} tickets</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:20px 28px}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#8b949e;margin-bottom:14px}}
.bar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}}
.chip{{background:#161b22;color:#e6edf3;border:1px solid var(--c);border-radius:999px;padding:5px 12px;cursor:pointer;font:inherit}}
.chip.on{{background:var(--c);color:#0d1117}} .chip b{{margin-left:4px}}
input{{background:#161b22;border:1px solid #30363d;color:#e6edf3;border-radius:6px;padding:6px 10px;font:inherit;width:220px}}
table{{border-collapse:collapse;width:100%}} th{{text-align:left;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;padding:6px 8px}}
td{{border-bottom:1px solid #21262d;padding:7px 8px;vertical-align:top}}
.id{{font-weight:700;white-space:nowrap}} .ti{{max-width:640px}} .sm{{color:#8b949e;font-size:12.5px}}
.b{{display:inline-block;border:1px solid var(--c);color:var(--c);border-radius:5px;padding:1px 8px;white-space:nowrap;font-size:12.5px}}
details{{margin-top:4px}} summary{{cursor:pointer;color:#58a6ff;font-size:12.5px}}
pre{{white-space:pre-wrap;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:10px;margin:6px 0 0;font:12.5px/1.45 ui-monospace,monospace}}
.hide{{display:none}}
</style>
<h1>{title} · tickets</h1>
<div class="sub">Generated {time.strftime('%Y-%m-%d %H:%M')} · refresh: <code>python3 .tickets/tickets.py board</code></div>
<div class="bar">{chips}<input id="q" placeholder="search id or title"></div>
<table><thead><tr><th>ID</th><th>Diff</th><th>Size</th><th>Title</th><th>Status</th><th>Note</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<script>
const on=new Set({shown}); // done hidden by default
const rows=[...document.querySelectorAll('tr.r')], chips=[...document.querySelectorAll('.chip')], q=document.getElementById('q');
function apply(){{const s=q.value.toLowerCase();
 chips.forEach(c=>c.classList.toggle('on',on.has(c.dataset.k)));
 rows.forEach(r=>r.classList.toggle('hide',!on.has(r.dataset.k)||(s&&!r.dataset.q.includes(s))));}}
chips.forEach(c=>c.onclick=()=>{{on.has(c.dataset.k)?on.delete(c.dataset.k):on.add(c.dataset.k);apply();}});
q.oninput=apply; apply();
</script></html>'''
    out = os.path.join(HERE, 'board.html')
    write(out, page)
    print('wrote', out, {STATUS[k][0]: v for k, v in counts.items() if v})


# ---------- git hook

def ids_in_subject(subject: str) -> List[str]:
    """IDs inside a trailing '(...)' of a commit subject: '(T64, T67 to T71)' -> T64, T67, ..., T71. '(see T95)' does not count."""
    m = re.search(r'\((%s\d+[a-z]?(?:\s*(?:,|and|to)\s*%s\d+[a-z]?)*)\)\s*$' % (PREFIX, PREFIX), subject)
    if not m:
        return []
    inner = m.group(1)
    ids: List[str] = []
    for pa, a, pb, b in re.findall(r'\b(%s)(\d+)\s+to\s+(%s)(\d+)\b' % (PREFIX, PREFIX), inner):
        if pa != pb or not int(a) <= int(b) <= int(a) + 1000:
            print('tickets: range %s%s to %s%s skipped (reversed, mixed prefixes or over 1000 ids)' % (pa, a, pb, b), file=sys.stderr)
            continue
        ids += ['%s%d' % (pa, n) for n in range(int(a), int(b) + 1)]
    inner = re.sub(r'\b%s\d+\s+to\s+%s\d+\b' % (PREFIX, PREFIX), '', inner)
    ids += ID_RE.findall(inner)
    return list(dict.fromkeys(ids))


def git(*a: str) -> str:
    return subprocess.run(['git', *a], capture_output=True, text=True, check=True).stdout.strip()


def tgit(*a: str) -> "subprocess.CompletedProcess[str]":
    """git inside .tickets/. GIT_* variables are dropped: inside a hook they point at the project's repo."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    return subprocess.run(['git', '-C', HERE, *a], capture_output=True, text=True, env=env)


def commit_tickets(message: str) -> None:
    with locked():
        commit_unlocked(message)


def commit_unlocked(message: str) -> None:
    """Caller holds locked()."""
    for g in ('rebase-merge', 'rebase-apply', 'MERGE_HEAD'):
        p = tgit('rev-parse', '--git-path', g).stdout.strip()
        if p and os.path.exists(os.path.join(HERE, p)):
            sys.exit('a rebase or merge is in progress: finish or abort it in %s first' % HERE)
    if tgit('diff', '--name-only', '--diff-filter=U').stdout.strip():
        sys.exit('unmerged files: finish or abort the rebase/merge in %s first' % HERE)
    r = tgit('add', '-A')
    if r.returncode:
        sys.exit(r.stderr.strip() or 'git add failed in ' + HERE)
    if tgit('diff', '--cached', '--quiet').returncode:
        r = tgit('commit', '-q', '-m', message)
        if r.returncode:
            sys.exit(r.stderr.strip() or 'git commit failed in ' + HERE)


def check_own_repo() -> None:
    """Without .tickets/.git, git would use the project's repo and commit its code."""
    top = tgit('rev-parse', '--show-toplevel').stdout.strip()
    if not top or os.path.realpath(top) != os.path.realpath(HERE):
        sys.exit('%s is not its own git repo' % HERE)


def auto_commit(message: str) -> None:
    """config auto_commit: commit .tickets/ after a change. Best effort: a problem is a warning, never a failure. Never pushes."""
    if not CFG['auto_commit']:
        return
    try:
        check_own_repo()
        commit_tickets(message)
    except SystemExit as e:
        reason = str(e.code) if isinstance(e.code, str) else 'git failed'
        print('tickets: not committed: ' + ' '.join(reason.split()), file=sys.stderr)
    except OSError as e:
        print('tickets: not committed: %s' % e, file=sys.stderr)


def sync() -> None:
    check_own_repo()
    with locked():   # the pull changes ticket files: no other writer meanwhile
        commit_unlocked('Tickets: sync')
        up = tgit('rev-parse', '--abbrev-ref', '@{upstream}')
        if up.returncode:
            print('no remote for this branch: committed locally only. To share: git -C %s push -u <remote> <branch>' % HERE)
            return
        r = tgit('pull', '-q', '--rebase')
        if r.returncode:
            sys.exit(r.stderr.strip() or 'git pull failed')
    r = tgit('push', '-q')
    if r.returncode:
        sys.exit(r.stderr.strip() or 'git push failed')
    # a new process: the pull may have changed config.json, which this one read at start
    if subprocess.run([sys.executable, os.path.abspath(__file__), 'board']).returncode:
        sys.exit('board failed after sync')
    print('synced with', up.stdout.strip())


def commit_hook() -> None:
    h, _, subject = git('log', '-1', '--format=%h%n%s').partition('\n')
    ids = ids_in_subject(subject)
    moved = set_status(ids, 'done', h) if ids else []
    if moved:
        board()
        auto_commit('Done: %s (%s)' % (', '.join(moved), h))
        print('tickets: done: ' + ', '.join(moved), file=sys.stderr)


def main(argv: List[str]) -> None:
    ap = argparse.ArgumentParser(prog='tickets.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')
    n = sub.add_parser('new'); n.add_argument('title')
    n.add_argument('-d', '--difficulty', choices=list(DIFF_ICON)); n.add_argument('-s', '--size', choices=['S', 'M', 'L', 's', 'm', 'l'])
    n.add_argument('-b', '--blocked-by', default='')
    ls = sub.add_parser('list'); ls.add_argument('status', nargs='?'); ls.add_argument('--all', action='store_true')
    sh = sub.add_parser('show'); sh.add_argument('id')
    s = sub.add_parser('set'); s.add_argument('id'); s.add_argument('status')
    d = sub.add_parser('done'); d.add_argument('ids', nargs='+'); d.add_argument('--commit', default='')
    for c in ('board', 'sync', 'commit-hook'):
        sub.add_parser(c)
    a = ap.parse_args(argv)
    if a.cmd == 'new':
        tid, path = new_ticket(a.title, a.difficulty, a.size, a.blocked_by)
        print(tid, path); board()
        auto_commit('New: ' + tid)
    elif a.cmd == 'list':
        if a.status and a.status not in STATUS:
            sys.exit('unknown status %r (known: %s)' % (a.status, ', '.join(STATUS)))
        with locked():   # a ticket moved during the read would vanish between listdir and open
            ts = all_tickets()
        by_id = {t['id']: t for t in ts}
        for t in sorted(ts, key=lambda t: (STATUS[effective(t, by_id)[0]][1], num(t))):
            key, _ = effective(t, by_id)
            if (key == a.status) if a.status else (key != 'done' or a.all):
                print('%-6s %-8s %s %-2s %s' % (t['id'], key, DIFF_ICON.get(t['difficulty'], ' '), t['size'], t['title']))
    elif a.cmd == 'show':
        with locked():
            t = {t['id']: t for t in all_tickets()}.get(a.id) or sys.exit('unknown ticket id: ' + a.id)
            text = read(t['path'])
        print(t['path']); print(text, end='')
    elif a.cmd == 'set':
        changed = set_status([a.id], a.status)
        print('changed:', changed or 'nothing (unknown id)'); board()
        if changed:
            auto_commit('%s: %s' % (a.id, a.status))
    elif a.cmd == 'done':
        changed = set_status(a.ids, 'done', a.commit)
        print('done:', changed or 'nothing (unknown id)'); board()
        if changed:
            auto_commit('Done: %s%s' % (', '.join(changed), ' (%s)' % a.commit if a.commit else ''))
    elif a.cmd == 'board' or a.cmd is None:
        board()
    elif a.cmd == 'sync':
        sync()
    elif a.cmd == 'commit-hook':
        commit_hook()


if __name__ == '__main__':
    main(sys.argv[1:])
