import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

try:
    import fcntl
except ImportError:
    fcntl = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = None


def setUpModule():
    """A throwaway copy of the working tree, committed on branch `core`: install.sh clones from it."""
    global SOURCE
    SOURCE = tempfile.mkdtemp()
    shutil.copytree(ROOT, SOURCE, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git', '__pycache__'))
    for a in (['init', '-q', '-b', 'core'], ['add', '-A'], ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '-m', 'core']):
        subprocess.run(['git', *a], cwd=SOURCE, check=True, capture_output=True)


def tearDownModule():
    shutil.rmtree(SOURCE)


class Project:
    """A temp git repo with the system installed through install.sh."""
    def __init__(self, config=None):
        self.dir = tempfile.mkdtemp()
        self.sh('git', 'init', '-q', '-b', 'main')
        self.sh('git', 'config', 'user.email', 't@t')
        self.sh('git', 'config', 'user.name', 't')
        self.sh(os.path.join(SOURCE, 'install.sh'), self.dir)
        self.t = os.path.join(self.dir, '.tickets')
        if config:
            json.dump(config, open(os.path.join(self.t, 'config.json'), 'w'))

    def sh(self, *a):
        return subprocess.run(a, cwd=self.dir, capture_output=True, text=True, check=True).stdout

    def tk(self, *a):
        return self.sh(sys.executable, os.path.join(self.t, 'tickets.py'), *a)

    def tg(self, *a):
        return self.sh('git', '-C', self.t, *a)

    def read_root(self, name):
        return open(os.path.join(self.dir, name), encoding='utf-8').read()

    def exists(self, *p):
        return os.path.exists(os.path.join(self.t, *p))

    def read(self, *p):
        return open(os.path.join(self.t, *p), encoding='utf-8').read()

    def files(self, sub=''):
        return sorted(f for f in os.listdir(os.path.join(self.t, sub)) if f[:1] in 'TL' and f.endswith('.md'))


class Tickets(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.addCleanup(shutil.rmtree, self.p.dir)

    def test_install_clones_core_and_makes_main(self):
        for f in ('tickets.py', 'WORKFLOW.md', 'config.json', 'hooks/post-commit', 'modules/worktrees.md', 'modules/roles.md', 'board.html'):
            self.assertTrue(self.p.exists(f), f)
        self.assertTrue(os.path.exists(os.path.join(self.p.dir, '.git/hooks/post-commit')))
        self.assertEqual(self.p.tg('branch', '--show-current').strip(), 'main')
        self.assertIn('core', self.p.tg('branch'))
        self.assertIn('.tickets/', self.p.read_root('.gitignore'))

    def test_update_merges_core_and_keeps_project_files(self):
        self.p.tk('new', 'Mine')   # auto_commit commits it
        open(os.path.join(SOURCE, 'NEW.md'), 'w').write('from core')
        self.addCleanup(os.remove, os.path.join(SOURCE, 'NEW.md'))
        self.p.sh('git', '-C', SOURCE, 'add', 'NEW.md')
        self.p.sh('git', '-C', SOURCE, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '-m', 'more')
        self.p.sh(os.path.join(SOURCE, 'install.sh'), self.p.dir)
        self.assertTrue(self.p.exists('NEW.md'))
        self.assertTrue(self.p.exists('T1-mine.md'))

    def test_new_numbers_and_frontmatter(self):
        self.p.tk('new', 'Fix the seek bug', '-d', '2', '-s', 's', '-b', 'T9')
        self.p.tk('new', 'Second one')
        self.assertEqual(self.p.files(), ['T1-fix-the-seek-bug.md', 'T2-second-one.md'])
        txt = self.p.read('T1-fix-the-seek-bug.md')
        for line in ('title: Fix the seek bug', 'status: open', 'difficulty: 2', 'size: S', 'blocked_by: T9'):
            self.assertIn(line, txt)

    def test_set_status_moves_files_both_ways(self):
        self.p.tk('new', 'A')
        self.p.tk('set', 'T1', 'ready')
        self.assertIn('status: ready', self.p.read('T1-a.md'))
        self.p.tk('done', 'T1', '--commit', 'abc123')
        self.assertEqual(self.p.files(), [])
        done = self.p.read('done', 'T1-a.md')
        self.assertIn('status: done', done)
        self.assertIn('commit: abc123', done)
        self.p.tk('set', 'T1', 'parked')
        self.assertEqual(self.p.files(), ['T1-a.md'])
        self.assertIn('status: parked', self.p.read('T1-a.md'))

    def test_unknown_status_and_id(self):
        self.p.tk('new', 'A')
        with self.assertRaises(subprocess.CalledProcessError):
            self.p.tk('set', 'T1', 'nonsense')
        self.assertIn('nothing', self.p.tk('done', 'T99'))

    def test_show_and_list_filter(self):
        self.p.tk('new', 'First')
        self.p.tk('new', 'Second', '-b', 'T1')
        self.p.tk('set', 'T1', 'ready'); self.p.tk('set', 'T2', 'ready')
        out = self.p.tk('show', 'T2')
        self.assertIn('T2-second.md', out)
        self.assertIn('title: Second', out)
        self.assertIn('## Done when', out)
        with self.assertRaises(subprocess.CalledProcessError):
            self.p.tk('show', 'T99')
        ready = self.p.tk('list', 'ready')
        self.assertIn('First', ready)
        self.assertNotIn('Second', ready)          # waits for T1: blocked, not ready
        self.assertIn('Second', self.p.tk('list', 'blocked'))
        self.p.tk('done', 'T1')
        self.assertIn('First', self.p.tk('list', 'done'))   # a done filter needs no --all
        with self.assertRaises(subprocess.CalledProcessError):
            self.p.tk('list', 'nonsense')

    def test_commit_hook_warns_on_unknown_id(self):
        self.p.tk('new', 'A')
        r = subprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', 'Typo (T9)'],
                           cwd=self.p.dir, capture_output=True, text=True, check=True)
        self.assertIn('unknown ticket id: T9', r.stderr)
        self.assertEqual(self.p.files(), ['T1-a.md'])

    def test_board_escapes_config_values(self):
        cfg = {'statuses': [['open', 'Open', '"><x>'], ['done', 'Done', '#3fb950']]}
        json.dump(cfg, open(os.path.join(self.p.t, 'config.json'), 'w'))
        self.p.tk('board')
        self.assertNotIn('"><x>', self.p.read('board.html'))

    def test_blocked_by_shows_as_blocked_until_done(self):
        self.p.tk('new', 'First')
        self.p.tk('new', 'Second', '-b', 'T1')
        self.p.tk('set', 'T2', 'ready')
        self.assertRegex(self.p.tk('list'), r'T2\s+blocked')
        self.p.tk('done', 'T1')
        self.assertRegex(self.p.tk('list'), r'T2\s+ready')

    def test_board_lists_tickets_and_escapes(self):
        self.p.tk('new', 'Fix <b>markup</b>', '-d', '3')
        board = self.p.read('board.html')
        self.assertIn('Fix &lt;b&gt;markup&lt;/b&gt;', board)
        self.assertIn('🔴', board)

    def test_commit_hook_finishes_ticket_in_subject(self):
        self.p.tk('new', 'A'); self.p.tk('new', 'B'); self.p.tk('new', 'C')
        open(os.path.join(self.p.dir, 'f'), 'w').write('x')
        self.p.sh('git', 'add', 'f')
        self.p.sh('git', 'commit', '-q', '-m', 'Work (T1, T2)')
        self.assertEqual(self.p.files(), ['T3-c.md'])
        self.assertRegex(self.p.read('done', 'T1-a.md'), r'commit: [0-9a-f]{7,}')
        self.p.sh('git', 'commit', '-q', '--allow-empty', '-m', 'Partial T3 (see T3)')
        self.assertEqual(self.p.files(), ['T3-c.md'])

    def test_ids_in_subject_ranges(self):
        sys.path.insert(0, ROOT)
        import importlib.util
        spec = importlib.util.spec_from_file_location('tickets_mod', os.path.join(ROOT, 'tickets.py'))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        self.assertEqual(sorted(m.ids_in_subject('X (T64, T67 to T70)')), ['T64', 'T67', 'T68', 'T69', 'T70'])
        self.assertEqual(m.ids_in_subject('X (see T95)'), [])
        self.assertEqual(m.ids_in_subject('X T5'), [])


class CustomConfig(unittest.TestCase):
    def test_prefix_and_statuses(self):
        p = Project({'title': 'Demo', 'id_prefix': 'V', 'statuses': [['todo', 'To do', '#fff'], ['done', 'Done', '#0f0']]})
        self.addCleanup(shutil.rmtree, p.dir)
        p.tk('new', 'Thing')
        self.assertEqual(p.files(), [])
        self.assertTrue(p.exists('V1-thing.md'))
        p.tk('set', 'V1', 'todo')
        with self.assertRaises(subprocess.CalledProcessError):
            p.tk('set', 'V1', 'ready')


class MultiUser(unittest.TestCase):
    """Optional: several prefixes, a name on doing, sync and auto-commit of .tickets/."""
    def setUp(self):
        self.p = Project()
        self.addCleanup(shutil.rmtree, self.p.dir)

    def config(self, **kw):
        json.dump(dict({'title': 'x', 'id_prefix': 'T'}, **kw), open(os.path.join(self.p.t, 'config.json'), 'w'))

    def test_one_prefix_per_machine(self):
        self.config(id_prefix=['T', 'L'])
        self.p.tk('new', 'Desk')
        with mock.patch.dict(os.environ, {'TICKETS_PREFIX': 'L'}):
            self.p.tk('new', 'Laptop one'); self.p.tk('new', 'Laptop two')
            with self.assertRaises(subprocess.CalledProcessError), mock.patch.dict(os.environ, {'TICKETS_PREFIX': 'X'}):
                self.p.tk('new', 'Bad')
        self.assertEqual(self.p.files(), ['L1-laptop-one.md', 'L2-laptop-two.md', 'T1-desk.md'])
        self.p.sh('git', 'commit', '-q', '--allow-empty', '-m', 'Work (T1, L1 to L2)')
        self.assertEqual(self.p.files(), [])

    def test_doing_records_who(self):
        self.p.tk('new', 'A')
        self.p.tk('set', 'T1', 'doing')
        self.assertIn('by: t', self.p.read('T1-a.md'))
        self.assertIn('by t', self.p.read('board.html'))

    def test_sync_without_remote_only_commits(self):
        self.p.tk('new', 'A')
        out = self.p.tk('sync')
        self.assertIn('no remote', out)
        self.assertEqual(self.p.tg('status', '--porcelain'), '')

    def test_sync_with_remote(self):
        remote = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, remote)
        self.p.sh('git', 'init', '-q', '--bare', remote)
        self.p.tg('remote', 'add', 'share', remote)
        self.p.tg('push', '-q', '-u', 'share', 'main')
        other = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, other)
        self.p.sh('git', 'clone', '-q', '-b', 'main', remote, other)
        open(os.path.join(other, 'L1-from-laptop.md'), 'w').write('---\ntitle: From laptop\nstatus: open\n---\n')
        for a in (['add', '.'], ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '-m', 'laptop'], ['push', '-q']):
            self.p.sh('git', '-C', other, *a)
        self.p.tk('new', 'From desk')
        self.p.tk('sync')
        self.assertIn('L1-from-laptop.md', self.p.files())
        self.assertIn('T1-from-desk.md', self.p.sh('git', '-C', remote, 'ls-tree', '--name-only', 'main'))

    def test_hook_auto_commit(self):
        self.config(auto_commit=True)
        self.p.tg('commit', '-q', '-am', 'config')
        self.p.tk('new', 'A')
        open(os.path.join(self.p.dir, 'f'), 'w').write('x')
        self.p.sh('git', 'add', 'f')
        self.p.sh('git', 'commit', '-q', '-m', 'Work (T1)')
        self.assertEqual(self.p.tg('status', '--porcelain'), '')
        self.assertIn('T1', self.p.tg('log', '-1', '--format=%s'))
        self.assertEqual(self.p.sh('git', 'diff', '--cached', '--name-only'), '')   # the project's index is untouched


class AutoCommit(unittest.TestCase):
    """auto_commit (default true): one commit in .tickets/ after new, set, done and the hook. Best effort, never pushes."""
    def setUp(self):
        self.p = Project()
        self.addCleanup(shutil.rmtree, self.p.dir)

    def subjects(self):
        return self.p.tg('log', '--format=%s', 'main').split('\n')[:-1]

    def test_default_config_commits_once_per_command(self):
        n = len(self.subjects())
        self.p.tk('new', 'A'); self.p.tk('new', 'B')
        self.p.tk('set', 'T1', 'doing')
        self.p.tk('set', 'T1', 'doing')   # no change: no commit
        self.p.tk('done', 'T2', '--commit', 'abc123')
        self.assertEqual(self.subjects()[:4], ['Done: T2 (abc123)', 'T1: doing', 'New: T2', 'New: T1'])
        self.assertEqual(len(self.subjects()), n + 4)
        self.assertEqual(self.p.tg('status', '--porcelain'), '')

    def test_hook_commit_is_one_commit(self):
        self.p.tk('new', 'A')
        n = len(self.subjects())
        self.p.sh('git', 'commit', '-q', '--allow-empty', '-m', 'Work (T1)')
        h = self.p.sh('git', 'log', '-1', '--format=%h').strip()
        self.assertEqual(self.subjects()[0], 'Done: T1 (%s)' % h)
        self.assertEqual(len(self.subjects()), n + 1)
        self.assertEqual(self.p.sh('git', 'diff', '--cached', '--name-only'), '')

    def test_unknown_id_makes_no_commit(self):
        n = len(self.subjects())
        self.p.tk('set', 'T9', 'ready'); self.p.tk('done', 'T9')
        self.assertEqual(len(self.subjects()), n)

    def test_off_makes_no_commit(self):
        p = Project({'auto_commit': False})
        self.addCleanup(shutil.rmtree, p.dir)
        n = p.tg('rev-list', '--count', 'main')
        p.tk('new', 'A'); p.tk('set', 'T1', 'ready'); p.tk('done', 'T1')
        p.sh('git', 'commit', '-q', '--allow-empty', '-m', 'Work (T1)')
        self.assertEqual(p.tg('rev-list', '--count', 'main'), n)
        self.assertIn('done/', p.tg('status', '--porcelain'))   # still uncommitted

    def run_tk(self, *a):
        return subprocess.run([sys.executable, os.path.join(self.p.t, 'tickets.py'), *a], cwd=self.p.dir, capture_output=True, text=True)

    def test_not_its_own_repo_warns_and_succeeds(self):
        shutil.rmtree(os.path.join(self.p.t, '.git'))
        r = self.run_tk('new', 'A')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.p.exists('T1-a.md'))
        self.assertEqual(r.stderr.count('\n'), 1)
        self.assertIn('not committed', r.stderr)
        self.assertEqual(self.p.sh('git', 'rev-list', '--all', '--count').strip(), '0')   # nothing went into the project's repo

    def test_rebase_in_progress_warns_and_succeeds(self):
        os.mkdir(os.path.join(self.p.t, '.git', 'rebase-merge'))
        r = self.run_tk('new', 'A')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.p.exists('T1-a.md'))
        self.assertIn('not committed', r.stderr)
        self.assertIn('rebase', r.stderr)
        self.assertEqual(r.stderr.count('\n'), 1)

    def test_git_failure_warns_and_succeeds(self):
        pre = os.path.join(self.p.t, '.git', 'hooks', 'pre-commit')
        open(pre, 'w').write('#!/bin/sh\nexit 1\n')
        os.chmod(pre, 0o755)
        r = self.run_tk('new', 'A')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('not committed', r.stderr)

    def test_mode_must_be_chain_or_validate(self):
        for mode, ok in (('chain', True), ('validate', True), ('fast', False)):
            json.dump({'mode': mode}, open(os.path.join(self.p.t, 'config.json'), 'w'))
            r = self.run_tk('board')
            self.assertEqual(r.returncode == 0, ok, r.stderr)
            if not ok:
                self.assertIn('mode must be "chain" or "validate"', r.stderr)


class Safety(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.addCleanup(shutil.rmtree, self.p.dir)

    def test_duplicate_id_fails(self):
        self.p.tk('new', 'One')
        open(os.path.join(self.p.t, 'T1-other.md'), 'w').write('---\nstatus: open\n---\n')
        with self.assertRaises(subprocess.CalledProcessError) as c:
            self.p.sh(sys.executable, os.path.join(self.p.t, 'tickets.py'), 'list')
        self.assertIn('duplicate ticket id T1', c.exception.stderr)

    def test_no_overwrite(self):
        import importlib.util
        self.p.tk('new', 'One')
        spec = importlib.util.spec_from_file_location('tk_under_test', os.path.join(self.p.t, 'tickets.py'))
        tk = importlib.util.module_from_spec(spec); spec.loader.exec_module(tk)
        path = os.path.join(self.p.t, 'T1-one.md')
        real = tk.all_tickets
        tk.all_tickets = lambda: []                  # hide T1 so the next id collides with its file
        with self.assertRaises(SystemExit):
            tk.new_ticket('One', '', '', '')
        tk.all_tickets = real
        os.makedirs(tk.DONE_DIR, exist_ok=True)
        dest = os.path.join(tk.DONE_DIR, 'T1-one.md')
        open(dest, 'w').write('keep')
        tk.all_tickets = lambda: [{'id': 'T1', 'path': path}]
        with self.assertRaises(SystemExit):
            tk.set_status(['T1'], 'done')
        self.assertEqual(open(dest).read(), 'keep')
        self.assertTrue(os.path.exists(path))

    def load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('tk_under_test', os.path.join(self.p.t, 'tickets.py'))
        tk = importlib.util.module_from_spec(spec); spec.loader.exec_module(tk)
        return tk

    def test_board_escapes_status_keys_and_colours(self):
        json.dump({'statuses': [['open', 'Open', 'red;background:url(https://x)'], ['a</script><b>', 'A', '#abc'], ['done', 'Done', '#3fb950']]},
                  open(os.path.join(self.p.t, 'config.json'), 'w'))
        self.p.tk('board')
        page = self.p.read('board.html')
        self.assertNotIn('</script><b>', page)
        self.assertIn('a<\\/script><b>', page)
        self.assertNotIn('url(https', page)
        self.assertIn('--c:#8b949e', page)
        self.assertIn('--c:#abc', page)

    def test_symlinked_ticket_is_ignored(self):
        outside = os.path.join(self.p.dir, 'outside.md')
        open(outside, 'w').write('---\nstatus: open\n---\nsecret')
        os.symlink(outside, os.path.join(self.p.t, 'T1-link.md'))
        with self.assertRaises(subprocess.CalledProcessError):
            self.p.tk('show', 'T1')
        self.assertIn('nothing', self.p.tk('set', 'T1', 'doing'))
        self.assertNotIn('secret', self.p.read('board.html'))
        self.assertNotIn('doing', open(outside).read())
        os.makedirs(os.path.join(self.p.dir, 'elsewhere'))
        open(os.path.join(self.p.dir, 'elsewhere', 'T2-x.md'), 'w').write('---\nstatus: open\n---\n')
        os.symlink(os.path.join(self.p.dir, 'elsewhere'), os.path.join(self.p.t, 'done'))
        self.assertNotIn('T2', self.p.tk('list', '--all'))

    def test_failed_write_keeps_original(self):
        self.p.tk('new', 'A')
        tk = self.load()
        path = os.path.join(self.p.t, 'T1-a.md')
        before = open(path).read()
        real_open = open

        class Bad:
            def __init__(self, f):
                self.f = f
            def __enter__(self):
                return self
            def __exit__(self, *a):
                self.f.close()
            def write(self, s):
                self.f.write(s[:5]); self.f.flush()
                raise OSError('disk full')

        def fake_open(p, mode='r', *a, **k):
            f = real_open(p, mode, *a, **k)
            return Bad(f) if 'w' in mode else f
        with mock.patch('builtins.open', fake_open), self.assertRaises(OSError):
            tk.set_meta(path, {'status': 'ready'})
        self.assertEqual(open(path).read(), before)
        self.assertEqual(self.p.files(), ['T1-a.md'])
        self.assertEqual([f for f in os.listdir(self.p.t) if f.endswith('.tmp')], [])

    def test_symlinked_done_dir_refused(self):
        self.p.tk('new', 'A')
        outside = os.path.join(self.p.dir, 'elsewhere')
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.p.t, 'done'))
        with self.assertRaises(subprocess.CalledProcessError):
            self.p.tk('done', 'T1')
        self.assertEqual(os.listdir(outside), [])
        self.assertEqual(self.p.files(), ['T1-a.md'])

    def test_symlinked_board_is_replaced_not_followed(self):
        outside = os.path.join(self.p.dir, 'precious')
        open(outside, 'w').write('keep')
        board = os.path.join(self.p.t, 'board.html')
        os.remove(board)
        os.symlink(outside, board)
        self.p.tk('board')
        self.assertEqual(open(outside).read(), 'keep')
        self.assertFalse(os.path.islink(board))
        self.assertIn('<table', self.p.read('board.html'))

    def test_missing_blocker_still_blocks(self):
        self.p.tk('new', 'A', '-b', 'T99')
        self.p.tk('set', 'T1', 'ready')
        self.assertRegex(self.p.tk('list'), r'T1\s+blocked')
        self.assertIn('waits for T99', self.p.read('board.html'))

    def test_sync_fails_when_add_fails(self):
        self.p.tk('new', 'A')
        lock = self.p.tg('rev-parse', '--git-path', 'index.lock').strip()
        open(os.path.join(self.p.t, lock), 'w').close()
        with self.assertRaises(subprocess.CalledProcessError) as c:
            self.p.tk('sync')
        self.assertIn('index.lock', c.exception.stderr)

    def test_duplicate_frontmatter_key_is_collapsed(self):
        self.p.tk('new', 'A')
        path = os.path.join(self.p.t, 'T1-a.md')
        text = open(path).read().replace('status: open\n', 'status: open\nstatus: parked\n')
        open(path, 'w').write(text)
        self.p.tk('set', 'T1', 'ready')
        self.assertEqual(self.p.read('T1-a.md').count('status:'), 1)
        self.assertRegex(self.p.tk('list'), r'T1\s+ready')

    def test_sync_refuses_while_rebase_conflict(self):
        remote = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, remote)
        other = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, other)
        self.p.sh('git', 'init', '-q', '--bare', remote)
        self.p.tk('new', 'A')
        self.p.tk('sync')
        self.p.tg('remote', 'add', 'share', remote)
        self.p.tg('push', '-q', '-u', 'share', 'main')
        self.p.sh('git', 'clone', '-q', '-b', 'main', remote, other)
        f = os.path.join(other, 'T1-a.md')
        with open(f) as r:
            text = r.read()
        with open(f, 'w') as w:
            w.write(text.replace('status: open', 'status: ready'))
        for a in (['commit', '-q', '-am', 'laptop'], ['push', '-q']):
            self.p.sh('git', '-C', other, '-c', 'user.email=t@t', '-c', 'user.name=t', *a)
        self.p.tk('set', 'T1', 'parked')
        with self.assertRaises(subprocess.CalledProcessError):
            self.p.tk('sync')                                    # conflict: stops mid-rebase
        with self.assertRaises(subprocess.CalledProcessError) as c:
            self.p.tk('sync')
        self.assertIn('finish or abort', c.exception.stderr)
        self.assertNotIn('<<<<<<<', self.p.tg('log', '--all', '-p', '--', 'T1-a.md'))

    def test_parallel_new_gives_distinct_ids(self):
        cmd = [sys.executable, os.path.join(self.p.t, 'tickets.py'), 'new']
        procs = [subprocess.Popen(cmd + ['race %d' % i], cwd=self.p.dir, stdout=subprocess.PIPE, text=True) for i in range(6)]
        ids = [pr.communicate()[0].split()[0] for pr in procs]
        self.assertEqual(len(set(ids)), 6)
        self.assertEqual(len(self.p.files()), 6)
        self.p.tk('list')                                        # no duplicate id error

    def test_status_change_waits_for_a_concurrent_one(self):
        """set T1 ready pauses after reading T1; done T1 meanwhile must wait, not leave two T1 files."""
        self.p.tk('new', 'One')
        mark = os.path.join(self.p.dir, 'paused')
        code = (
            'import importlib.util, os, sys, time\n'
            'spec = importlib.util.spec_from_file_location("tk", sys.argv[1])\n'
            'tk = importlib.util.module_from_spec(spec); spec.loader.exec_module(tk)\n'
            'real = tk.write\n'
            'def slow(path, text):\n'
            '    open(sys.argv[2], "w").close(); time.sleep(1); real(path, text)\n'
            'tk.write = slow\n'
            'tk.set_status(["T1"], "ready")\n')
        slow = subprocess.Popen([sys.executable, '-c', code, os.path.join(self.p.t, 'tickets.py'), mark], cwd=self.p.dir)
        for _ in range(100):
            if os.path.exists(mark):
                break
            time.sleep(0.05)
        self.assertTrue(os.path.exists(mark), 'helper never reached its pause')
        self.p.tk('done', 'T1')
        self.assertEqual(slow.wait(), 0)
        self.assertEqual(len(self.p.files()) + len(self.p.files('done')), 1)
        self.assertIn('T1', self.p.tk('list', '--all'))

    @unittest.skipUnless(fcntl, 'needs fcntl')
    def test_new_waits_for_a_held_lock_without_evicting_it(self):
        lock = open(os.path.join(self.p.t, '.lock'), 'a')
        self.addCleanup(lock.close)
        fcntl.flock(lock, fcntl.LOCK_EX)
        cmd = [sys.executable, os.path.join(self.p.t, 'tickets.py'), 'new', 'X']
        pr = subprocess.Popen(cmd, cwd=self.p.dir, stdout=subprocess.PIPE, text=True)
        time.sleep(0.5)
        self.assertIsNone(pr.poll(), 'new did not wait for the lock')
        self.assertEqual(self.p.files(), [])
        fcntl.flock(lock, fcntl.LOCK_UN)
        out = pr.communicate(timeout=10)[0]
        self.assertEqual(out.split()[0], 'T1')
        self.assertEqual(len(self.p.files()), 1)

    def test_lock_file_is_not_committed_by_sync(self):
        self.p.tk('new', 'One')
        self.p.tk('sync')
        self.assertTrue(self.p.exists('.lock'))
        self.assertNotIn('.lock', self.p.tg('ls-files').split())
        self.assertEqual(self.p.tg('status', '--porcelain').strip(), '')

    def test_bad_ranges_warn_and_are_skipped(self):
        json.dump({'id_prefix': ['T', 'L']}, open(os.path.join(self.p.t, 'config.json'), 'w'))
        tk = self.load()
        for subject in ('Work (T7 to T3)', 'Work (T1 to T20000000)', 'Work (T1 to L5)'):
            with mock.patch('sys.stderr') as err:
                self.assertEqual(tk.ids_in_subject(subject), [])
            self.assertTrue(err.write.called, subject)
        self.assertEqual(tk.ids_in_subject('Work (T64, T67 to T69)'), ['T67', 'T68', 'T69', 'T64'])


    def share(self):
        """A bare remote for .tickets/ and a second clone of it. Returns the clone."""
        remote = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, remote)
        other = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, other)
        self.p.sh('git', 'init', '-q', '--bare', remote)
        self.p.tg('remote', 'add', 'share', remote)
        self.p.tg('push', '-q', '-u', 'share', 'main')
        self.p.sh('git', 'clone', '-q', '-b', 'main', remote, other)
        return other

    def push_from(self, other, msg):
        for a in (['add', '-A'], ['-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '-m', msg], ['push', '-q']):
            self.p.sh('git', '-C', other, *a)

    def waits_for_lock(self, *args):
        """Runs tickets.py <args> while the test holds the lock: it must not finish before the lock is released."""
        lock = open(os.path.join(self.p.t, '.lock'), 'a')
        self.addCleanup(lock.close)
        fcntl.flock(lock, fcntl.LOCK_EX)
        pr = subprocess.Popen([sys.executable, os.path.join(self.p.t, 'tickets.py'), *args], cwd=self.p.dir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.5)
        self.assertIsNone(pr.poll(), '%s did not wait for the lock' % ' '.join(args))
        fcntl.flock(lock, fcntl.LOCK_UN)
        out, err = pr.communicate(timeout=20)
        self.assertEqual(pr.returncode, 0, err)
        return out

    @unittest.skipUnless(fcntl, 'needs fcntl')
    def test_sync_pull_waits_for_the_lock(self):
        other = self.share()
        open(os.path.join(other, 'L1-x.md'), 'w').write('---\nstatus: open\n---\n')
        self.push_from(other, 'laptop')
        tk = self.load()
        real, seen = tk.tgit, []

        def spy(*a):
            if a[0] == 'pull':
                with open(os.path.join(self.p.t, '.lock'), 'a') as f:   # a new fd: flock conflicts with the one sync holds
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        seen.append(False)
                    except BlockingIOError:
                        seen.append(True)
            return real(*a)

        tk.tgit = spy
        tk.sync()
        self.assertEqual(seen, [True], 'the pull must run while sync holds the lock')
        self.assertIn('L1-x.md', os.listdir(self.p.t))

    @unittest.skipUnless(fcntl, 'needs fcntl')
    def test_board_and_readers_wait_for_the_lock(self):
        self.p.tk('new', 'A')
        self.waits_for_lock('board')
        self.assertIn('T1', self.waits_for_lock('list'))
        self.assertIn('T1-a.md', self.waits_for_lock('show', 'T1'))

    def test_planted_tmp_symlink_is_not_followed(self):
        self.p.tk('new', 'A')
        tk = self.load()
        path = os.path.join(self.p.t, 'T1-a.md')
        outside = os.path.join(self.p.dir, 'precious')
        open(outside, 'w').write('keep')
        os.symlink(outside, '%s.%d.tmp' % (path, os.getpid()))   # the name the old write() used
        tk.set_meta(path, {'status': 'ready'})
        self.assertEqual(open(outside).read(), 'keep')
        self.assertFalse(os.path.islink(path))
        self.assertIn('status: ready', open(path).read())
        mask = os.umask(0); os.umask(mask)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o666 & ~mask)

    def test_failed_move_keeps_status(self):
        self.p.tk('new', 'A')
        before = self.p.read('T1-a.md')
        open(os.path.join(self.p.t, 'done'), 'w').close()      # a file where the folder should be
        with self.assertRaises(subprocess.CalledProcessError) as c:
            self.p.tk('done', 'T1')
        self.assertIn('not a folder', c.exception.stderr)
        self.assertEqual(self.p.read('T1-a.md'), before)
        os.remove(os.path.join(self.p.t, 'done'))
        tk = self.load()
        with mock.patch('os.rename', side_effect=OSError('injected')), self.assertRaises(OSError):
            tk.set_status(['T1'], 'done')
        self.assertEqual(self.p.read('T1-a.md'), before)

    def test_prefix_must_be_letters(self):
        for bad in ('../escaped', '', ['T', 'a/b'], [], 5):
            json.dump({'id_prefix': bad}, open(os.path.join(self.p.t, 'config.json'), 'w'))
            with self.assertRaises(subprocess.CalledProcessError) as c:
                self.p.tk('new', 'X')
            self.assertIn('id_prefix', c.exception.stderr)
        self.assertEqual([f for f in os.listdir(self.p.dir) if f.endswith('.md')], [])

    def test_blocked_works_without_blocked_status(self):
        json.dump({'statuses': [['ready', 'Ready', '#4ea1ff'], ['open', 'Open', '#f0b429'], ['done', 'Done', '#3fb950']]},
                  open(os.path.join(self.p.t, 'config.json'), 'w'))   # the README example
        self.p.tk('new', 'A', '-b', 'T99')
        self.p.tk('set', 'T1', 'ready')
        self.assertRegex(self.p.tk('list'), r'T1\s+blocked')
        self.assertEqual(self.p.tk('list', 'ready'), '')

    def test_first_status_is_never_the_added_blocked(self):
        for statuses, want in (([['done', 'Done', '#3fb950']], 'done'),
                               ([['done', 'Done', '#3fb950'], ['todo', 'Todo', '#4ea1ff']], 'todo')):
            for f in os.listdir(self.p.t):
                if f.endswith('.md'):
                    os.remove(os.path.join(self.p.t, f))
            json.dump({'statuses': statuses}, open(os.path.join(self.p.t, 'config.json'), 'w'))
            self.p.tk('new', 'X')
            self.assertIn('status: ' + want, self.p.read('T1-x.md'))

    def test_unreadable_ticket_is_skipped_with_warning(self):
        self.p.tk('new', 'A')
        open(os.path.join(self.p.t, 'T9-x.md'), 'wb').write(b'---\n\xff\xfe\n---\n')
        os.mkdir(os.path.join(self.p.t, 'T8-y.md'))
        r = subprocess.run([sys.executable, os.path.join(self.p.t, 'tickets.py'), 'list'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn('T9-x.md', r.stderr)
        self.assertIn('A', r.stdout)

    def test_new_strips_newlines_and_bad_blockers(self):
        self.p.tk('new', 'X\ndifficulty: 3\r\n---', '-b', 'T5\nsize: L, junk T6')
        txt = self.p.read(self.p.files()[0])
        self.assertIn('title: X difficulty: 3 ---\n', txt)
        self.assertIn('blocked_by: T5, T6\n', txt)
        self.assertNotIn('\ndifficulty:', txt)
        with self.assertRaises(subprocess.CalledProcessError):
            self.p.tk('new', 'Y', '-b', 'nonsense')

    def test_commit_hook_empty_subject_does_nothing(self):
        self.p.tk('new', 'A')
        subprocess.run(['git', 'commit', '-q', '--allow-empty', '--allow-empty-message', '-m', ''],
                       cwd=self.p.dir, capture_output=True, text=True, check=True)
        self.p.tk('commit-hook')
        self.assertEqual(self.p.files(), ['T1-a.md'])

    def test_malformed_config_exits_with_message(self):
        for bad in ('[1]', '{', '{"statuses": [["done"]]}', '{"statuses": 5}'):
            open(os.path.join(self.p.t, 'config.json'), 'w').write(bad)
            with self.assertRaises(subprocess.CalledProcessError) as cm:
                self.p.tk('list')
            self.assertIn('config.json', cm.exception.stderr)
            self.assertNotIn('Traceback', cm.exception.stderr)

    def test_gitignore_has_tmp(self):
        self.assertIn('*.tmp', self.p.read('.gitignore'))

    def test_sync_board_uses_pulled_config(self):
        other = self.share()
        json.dump({'title': 'Renamed', 'id_prefix': ['T', 'L']}, open(os.path.join(other, 'config.json'), 'w'))
        open(os.path.join(other, 'L1-new.md'), 'w').write('---\ntitle: From laptop\nstatus: open\n---\n')
        self.push_from(other, 'laptop')
        self.p.tk('sync')
        page = self.p.read('board.html')
        self.assertIn('Renamed', page)
        self.assertIn('From laptop', page)

if __name__ == '__main__':
    unittest.main()
