import json, os, shutil, subprocess, sys, tempfile, unittest

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
        return sorted(f for f in os.listdir(os.path.join(self.t, sub)) if f.startswith('T') and f.endswith('.md'))


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
        self.p.tk('new', 'Mine')
        self.p.tg('add', 'T1-mine.md'); self.p.tg('commit', '-q', '-m', 'ticket')
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

if __name__ == '__main__':
    unittest.main()
