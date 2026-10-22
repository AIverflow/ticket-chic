#!/usr/bin/env python3
"""Ticket tool. One markdown file per ticket in .tickets/ (open) or .tickets/done/ (finished).
Each file starts with a frontmatter block (status, difficulty, size, blocked_by).
  tickets.py new "Title" [-d 1|2|3] [-s S|M|L] [-b T1,T2]   create the next ticket
  tickets.py list [--all]                                    print the tickets
  tickets.py set T12 <status>                                change status (done moves the file to done/)
  tickets.py done T12 [T13 ...] [--commit <hash>]            same as set <id> done
  tickets.py board                                           write board.html (filters, search, details)
  tickets.py commit-hook                                     post-commit: finishes the tickets named in the subject
Optional .tickets/config.json: {"title": "...", "id_prefix": "T", "statuses": [[key, label, colour], ...]}"""
import argparse, html, json, os, re, subprocess, sys, time

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


def load_config():
    p = os.path.join(HERE, 'config.json')
    c = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    c.setdefault('title', os.path.basename(os.path.dirname(HERE)) or 'Project')
    c.setdefault('id_prefix', 'T')
    c.setdefault('statuses', DEFAULT_STATUSES)
    if 'done' not in [s[0] for s in c['statuses']]:
        sys.exit('config.json: statuses must contain "done"')
    return c


CFG = load_config()
PREFIX = re.escape(CFG['id_prefix'])
STATUS = {s[0]: (s[1], i, s[2]) for i, s in enumerate(CFG['statuses'])}   # key -> (label, order, colour)
FIRST = 'open' if 'open' in STATUS else CFG['statuses'][0][0]   # status of a new ticket
ID_RE = re.compile(r'\b%s\d+[a-z]?\b' % PREFIX)
FILE_RE = re.compile(r'^(%s\d+[a-z]?)(?:-.*)?\.md$' % PREFIX)
FM_RE = re.compile(r'\A---\n(.*?)\n---[ \t]*\n?(.*)\Z', re.S)


# ---------- reading and writing ticket files

def split_fm(text):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for l in m.group(1).split('\n'):
        k, sep, v = l.partition(':')
        if sep and k.strip():
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def read_ticket(path, in_done):
    m = FILE_RE.match(os.path.basename(path))
    if not m:
        return None
    meta, body = split_fm(open(path, encoding='utf-8').read())
    body = body.strip()
    title = meta.get('title') or next((l[2:].strip() for l in body.split('\n') if l.startswith('# ')), m.group(1))
    status = 'done' if in_done else meta.get('status', FIRST)
    if status not in STATUS:
        status = FIRST
    return {'id': m.group(1), 'path': path, 'title': title, 'status': status,
            'difficulty': meta.get('difficulty') if meta.get('difficulty') in DIFF_ICON else '',
            'size': meta.get('size', '').upper() if meta.get('size', '').upper() in ('S', 'M', 'L') else '',
            'blocked_by': ID_RE.findall(meta.get('blocked_by', '')),
            'note': meta.get('commit', ''), 'body': body}


def all_tickets():
    out, seen = [], {}
    for d, in_done in ((HERE, False), (DONE_DIR, True)):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if t := read_ticket(os.path.join(d, f), in_done):
                    if t['id'] in seen:
                        sys.exit('duplicate ticket id %s: %s and %s' % (t['id'], seen[t['id']], t['path']))
                    seen[t['id']] = t['path']
                    out.append(t)
    return out


def num(t):
    m = re.search(r'(\d+)([a-z]?)$', t['id'])
    return (int(m.group(1)), m.group(2))


def set_meta(path, updates):
    text = open(path, encoding='utf-8').read()
    m = FM_RE.match(text)
    lines, body = (m.group(1).split('\n'), m.group(2)) if m else ([], text)
    for k, v in updates.items():
        for i, l in enumerate(lines):
            if l.partition(':')[0].strip() == k:
                lines[i] = '%s: %s' % (k, v)
                break
        else:
            lines.append('%s: %s' % (k, v))
    open(path, 'w', encoding='utf-8').write('---\n' + '\n'.join(lines) + '\n---\n' + body)


def set_status(ids, status, commit=''):
    """Change the status of each ticket; done moves the file into done/, anything else moves it back. Returns the ids changed."""
    if status not in STATUS:
        sys.exit('unknown status %r (known: %s)' % (status, ', '.join(STATUS)))
    by_id = {t['id']: t for t in all_tickets()}
    changed = []
    for tid in ids:
        t = by_id.get(tid)
        if not t:
            print('unknown ticket id: ' + tid, file=sys.stderr)
            continue
        upd = {'status': status}
        if status == 'done':
            upd['done'] = time.strftime('%Y-%m-%d')
            if commit:
                upd['commit'] = commit
        dest = os.path.join(DONE_DIR if status == 'done' else HERE, os.path.basename(t['path']))
        if dest != t['path'] and os.path.exists(dest):
            sys.exit('%s already exists: not overwritten' % dest)
        set_meta(t['path'], upd)
        if dest != t['path']:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.rename(t['path'], dest)
        changed.append(tid)
    return changed


def new_ticket(title, difficulty, size, blocked_by):
    nums = [num(t)[0] for t in all_tickets()]
    tid = '%s%d' % (CFG['id_prefix'], max(nums, default=0) + 1)
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:50]
    path = os.path.join(HERE, '%s-%s.md' % (tid, slug) if slug else tid + '.md')
    fm = ['title: ' + title, 'status: ' + FIRST]
    if difficulty:
        fm.append('difficulty: ' + difficulty)
    if size:
        fm.append('size: ' + size.upper())
    if blocked_by:
        fm.append('blocked_by: ' + blocked_by)
    fm.append('created: ' + time.strftime('%Y-%m-%d'))
    try:
        f = open(path, 'x', encoding='utf-8')
    except FileExistsError:
        sys.exit('%s already exists: not overwritten' % path)
    with f:
        f.write('---\n' + '\n'.join(fm) + '\n---\n\n## Do\n\n\n## Done when\n\n')
    return tid, path


def effective(t, by_id):
    """(status key, ids still waited for). A ticket with unfinished blockers shows as blocked."""
    waiting = [b for b in t['blocked_by'] if b in by_id and by_id[b]['status'] != 'done']
    if waiting and t['status'] in ('open', 'ready') and 'blocked' in STATUS:
        return 'blocked', waiting
    return t['status'], waiting


# ---------- board

def board():
    ts = all_tickets()
    by_id = {t['id']: t for t in ts}
    rows, counts = [], {k: 0 for k in STATUS}
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
            f'<td class="sm">{html.escape(wait or t["note"])}</td></tr>')
    chips =''.join(f'<button class="chip" data-k="{html.escape(k)}" style="--c:{html.escape(v[2])}">{html.escape(v[0])} <b>{counts[k]}</b></button>'
                    for k, v in STATUS.items())
    title = html.escape(CFG['title'])
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
const on=new Set({json.dumps([k for k in STATUS if k != 'done'])}); // done hidden by default
const rows=[...document.querySelectorAll('tr.r')], chips=[...document.querySelectorAll('.chip')], q=document.getElementById('q');
function apply(){{const s=q.value.toLowerCase();
 chips.forEach(c=>c.classList.toggle('on',on.has(c.dataset.k)));
 rows.forEach(r=>r.classList.toggle('hide',!on.has(r.dataset.k)||(s&&!r.dataset.q.includes(s))));}}
chips.forEach(c=>c.onclick=()=>{{on.has(c.dataset.k)?on.delete(c.dataset.k):on.add(c.dataset.k);apply();}});
q.oninput=apply; apply();
</script></html>'''
    out = os.path.join(HERE, 'board.html')
    open(out, 'w', encoding='utf-8').write(page)
    print('wrote', out, {STATUS[k][0]: v for k, v in counts.items() if v})


# ---------- git hook

def ids_in_subject(subject):
    """IDs inside a trailing '(...)' of a commit subject: '(T64, T67 to T71)' -> T64, T67, ..., T71. '(see T95)' does not count."""
    p = CFG['id_prefix']
    m = re.search(r'\((%s\d+[a-z]?(?:\s*(?:,|and|to)\s*%s\d+[a-z]?)*)\)\s*$' % (PREFIX, PREFIX), subject)
    if not m:
        return []
    inner, ids = m.group(1), []
    for a, b in re.findall(r'\b%s(\d+)\s+to\s+%s(\d+)\b' % (PREFIX, PREFIX), inner):
        ids += ['%s%d' % (p, n) for n in range(int(a), int(b) + 1)]
    inner = re.sub(r'\b%s\d+\s+to\s+%s\d+\b' % (PREFIX, PREFIX), '', inner)
    ids += ID_RE.findall(inner)
    return list(dict.fromkeys(ids))


def git(*a):
    return subprocess.run(['git', *a], capture_output=True, text=True, check=True).stdout.strip()


def commit_hook():
    h, subject = git('log', '-1', '--format=%h%n%s').split('\n', 1)
    ids = ids_in_subject(subject)
    moved = set_status(ids, 'done', h) if ids else []
    if moved:
        board()
        print('tickets: done: ' + ', '.join(moved), file=sys.stderr)


def main(argv):
    ap = argparse.ArgumentParser(prog='tickets.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')
    n = sub.add_parser('new'); n.add_argument('title')
    n.add_argument('-d', '--difficulty', choices=list(DIFF_ICON)); n.add_argument('-s', '--size', choices=['S', 'M', 'L', 's', 'm', 'l'])
    n.add_argument('-b', '--blocked-by', default='')
    l = sub.add_parser('list'); l.add_argument('--all', action='store_true')
    s = sub.add_parser('set'); s.add_argument('id'); s.add_argument('status')
    d = sub.add_parser('done'); d.add_argument('ids', nargs='+'); d.add_argument('--commit', default='')
    for c in ('board', 'commit-hook'):
        sub.add_parser(c)
    a = ap.parse_args(argv)
    if a.cmd == 'new':
        tid, path = new_ticket(a.title, a.difficulty, a.size, a.blocked_by)
        print(tid, path); board()
    elif a.cmd == 'list':
        ts = all_tickets()
        by_id = {t['id']: t for t in ts}
        for t in sorted(ts, key=lambda t: (STATUS[effective(t, by_id)[0]][1], num(t))):
            key, _ = effective(t, by_id)
            if key != 'done' or a.all:
                print('%-6s %-8s %s %-2s %s' % (t['id'], key, DIFF_ICON.get(t['difficulty'], ' '), t['size'], t['title']))
    elif a.cmd == 'set':
        print('changed:', set_status([a.id], a.status) or 'nothing (unknown id)'); board()
    elif a.cmd == 'done':
        print('done:', set_status(a.ids, 'done', a.commit) or 'nothing (unknown id)'); board()
    elif a.cmd == 'board' or a.cmd is None:
        board()
    elif a.cmd == 'commit-hook':
        commit_hook()


if __name__ == '__main__':
    main(sys.argv[1:])
