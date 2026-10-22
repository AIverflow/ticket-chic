import json
import os
import shutil
import subprocess
import tempfile
import unittest

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


def sh(*a, cwd=None):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, check=True).stdout


class InstallHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, 'repo')
        os.mkdir(self.repo)
        sh('git', 'init', '-q', cwd=self.repo)
        sh('git', 'config', 'user.email', 'a@b.c', cwd=self.repo)
        sh('git', 'config', 'user.name', 'x', cwd=self.repo)
        self.hook = os.path.join(self.repo, '.git', 'hooks', 'post-commit')

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, proj=None, script=None):
        return sh(script or os.path.join(SOURCE, 'install.sh'), proj or self.repo)

    def fake_tickets(self, proj, log):
        """A tickets.py that records each call in `log`."""
        open(os.path.join(proj, '.tickets', 'tickets.py'), 'w').write(
            "open(%r,'a').write('x')\n" % log)

    def commit_in(self, folder, log):
        open(os.path.join(folder, 'f'), 'w').write('1')
        sh('git', 'add', 'f', cwd=folder)
        sh('git', 'commit', '-qm', 'a (T1)', cwd=folder)
        return open(log).read() if os.path.exists(log) else ''

    def test_fresh_and_update(self):
        self.install()
        self.assertIn('# ticketing-hook', open(self.hook).read())
        self.install()
        self.assertIn('# ticketing-hook', open(self.hook).read())

    def test_foreign_hook_kept(self):
        open(self.hook, 'w').write('#!/bin/sh\necho mine\n')
        out = self.install()
        self.assertEqual(open(self.hook).read(), '#!/bin/sh\necho mine\n')
        self.assertIn('not ours', out)

    def test_hookspath_and_subfolder(self):
        sh('git', 'config', 'core.hooksPath', 'myhooks', cwd=self.repo)
        sub = os.path.join(self.repo, 'sub')
        os.mkdir(sub)
        self.install(sub)
        h = os.path.join(self.repo, 'myhooks', 'post-commit')
        self.assertIn("sub='sub/'", open(h).read())
        self.assertFalse(os.path.exists(self.hook))

    def test_subfolder_commit_and_rebase_skip(self):
        sub = os.path.join(self.repo, 'sub')
        os.mkdir(sub)
        self.install(sub)
        t = os.path.join(sub, '.tickets')
        open(os.path.join(sub, 'f'), 'w').write('1')
        sh('git', 'add', 'f', cwd=sub)
        # fake tickets.py that records each call
        open(os.path.join(t, 'tickets.py'), 'w').write(
            "import sys\nopen(%r,'a').write('x')\n" % os.path.join(self.tmp.name, 'log'))
        sh('git', 'commit', '-qm', 'a (T1)', cwd=sub)
        log = os.path.join(self.tmp.name, 'log')
        self.assertEqual(open(log).read(), 'x')
        open(os.path.join(sub, 'f'), 'w').write('2')
        sh('git', 'commit', '-qam', 'fixup! a (T1)', cwd=sub)
        self.assertEqual(open(log).read(), 'x')

    def test_odd_folder_names_are_not_executed(self):
        log = os.path.join(self.tmp.name, 'log')
        for i, name in enumerate(['a"$(touch PWNED)"b', "it's|&\\x$HOME `touch PWNED`"]):
            sub = os.path.join(self.repo, name)
            os.mkdir(sub)
            self.install(sub)
            self.assertIn("sub='", open(self.hook).read())
            self.fake_tickets(sub, log)
            self.assertEqual(self.commit_in(sub, log), 'x' * (i + 1))
            for d, _, files in os.walk(self.repo):
                self.assertNotIn('PWNED', files, d)
            os.remove(self.hook)
        nl = os.path.join(self.repo, 'a\nb')
        os.mkdir(nl)
        r = subprocess.run([os.path.join(SOURCE, 'install.sh'), nl], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn('newline', r.stdout)

    def test_second_folder_in_same_repo_keeps_hook(self):
        for n in ('app1', 'app2'):
            os.mkdir(os.path.join(self.repo, n))
        self.install(os.path.join(self.repo, 'app1'))
        before = open(self.hook).read()
        out = self.install(os.path.join(self.repo, 'app2'))
        self.assertIn('only one ticket folder', out.lower())
        self.assertIn('app1/', out)
        self.assertEqual(open(self.hook).read(), before)
        self.assertTrue(os.path.exists(os.path.join(self.repo, 'app2', '.tickets', 'tickets.py')))
        self.install(os.path.join(self.repo, 'app1'))   # same folder: still updates
        self.assertEqual(open(self.hook).read(), before)

    def test_reinstall_same_odd_folder_updates(self):
        sub = os.path.join(self.repo, "a|b&c\\d'e")
        os.mkdir(sub)
        self.install(sub)
        out = self.install(sub)
        self.assertIn('installed', out)
        self.assertNotIn('not changed', out)

    def test_update_fetches_from_the_running_clone(self):
        self.install()
        other = os.path.join(self.tmp.name, 'other')
        sh('git', 'clone', '-q', '-b', 'core', SOURCE, other)
        open(os.path.join(other, 'extra.txt'), 'w').write('new')
        sh('git', 'add', 'extra.txt', cwd=other)
        sh('git', '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'extra', cwd=other)
        self.install(script=os.path.join(other, 'install.sh'))
        self.assertTrue(os.path.exists(os.path.join(self.repo, '.tickets', 'extra.txt')))

    def test_hook_works_in_a_submodule(self):
        lib = os.path.join(self.tmp.name, 'lib')
        os.mkdir(lib)
        sh('git', 'init', '-q', cwd=lib)
        sh('git', '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'i', cwd=lib)
        sh('git', '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', lib, 'mod', cwd=self.repo)
        mod = os.path.join(self.repo, 'mod')
        sh('git', 'config', 'user.email', 'a@b.c', cwd=mod)
        sh('git', 'config', 'user.name', 'x', cwd=mod)
        self.install(mod)
        log = os.path.join(self.tmp.name, 'log')
        self.fake_tickets(mod, log)
        self.assertEqual(self.commit_in(mod, log), 'x')

    def run_install(self, proj=None, script=None):
        return subprocess.run([script or os.path.join(SOURCE, 'install.sh'), proj or self.repo], capture_output=True, text=True)

    def test_plain_tickets_folder_in_app_repo_is_refused(self):
        os.mkdir(os.path.join(self.repo, '.tickets'))
        r = self.run_install()
        self.assertEqual(r.returncode, 1)
        self.assertIn('not a ticket repo (nothing changed)', r.stdout)
        branches = sh('git', 'branch', '--list', 'core', cwd=self.repo)
        self.assertEqual(branches.strip(), '')

    def test_update_refuses_when_main_is_not_checked_out(self):
        self.install()
        t = os.path.join(self.repo, '.tickets')
        sh('git', 'checkout', '-q', '-b', 'scratch', cwd=t)
        other = os.path.join(self.tmp.name, 'other')
        sh('git', 'clone', '-q', '-b', 'core', SOURCE, other)
        open(os.path.join(other, 'extra.txt'), 'w').write('new')
        sh('git', 'add', 'extra.txt', cwd=other)
        sh('git', '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'extra', cwd=other)
        r = self.run_install(script=os.path.join(other, 'install.sh'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('check out main', r.stdout)
        self.assertIn('(nothing changed)', r.stdout)
        self.assertFalse(os.path.exists(os.path.join(t, 'extra.txt')))
        self.assertEqual(sh('git', 'rev-parse', 'scratch', cwd=t), sh('git', 'rev-parse', 'main', cwd=t))
        self.assertNotEqual(sh('git', 'rev-parse', 'core', cwd=t), sh('git', 'rev-parse', 'scratch', cwd=t))


class FirstInstallConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, 'My App')
        os.mkdir(self.repo)
        sh('git', 'init', '-q', cwd=self.repo)
        self.cfg = os.path.join(self.repo, '.tickets', 'config.json')
        self.hook = os.path.join(self.repo, '.git', 'hooks', 'post-commit')

    def test_non_interactive_uses_defaults(self):
        r = subprocess.run([os.path.join(SOURCE, 'install.sh'), self.repo], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, check=True)
        self.assertEqual(json.load(open(self.cfg)), {
            'title': 'My App', 'id_prefix': 'T', 'auto_commit': True, 'roles': True, 'worktrees': False, 'mode': 'chain'})
        self.assertTrue(os.path.exists(self.hook))
        self.assertIn('Change any setting in .tickets/config.json', r.stdout)
        self.assertEqual(sh('git', 'status', '--porcelain', cwd=os.path.join(self.repo, '.tickets')), '')   # config is committed

    def test_update_keeps_config_and_prints_no_recap(self):
        subprocess.run([os.path.join(SOURCE, 'install.sh'), self.repo], capture_output=True, stdin=subprocess.DEVNULL, check=True)
        c = json.load(open(self.cfg))
        c['mode'] = 'validate'
        json.dump(c, open(self.cfg, 'w'))
        r = subprocess.run([os.path.join(SOURCE, 'install.sh'), self.repo], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, check=True)
        self.assertEqual(json.load(open(self.cfg))['mode'], 'validate')
        self.assertNotIn('Change any setting', r.stdout)

    def ask(self, answers):
        """Run install.sh with a pty as stdin and type the answers (one line each)."""
        import pty
        pid, fd = pty.fork()
        if pid == 0:
            os.execv(os.path.join(SOURCE, 'install.sh'), ['install.sh', self.repo])
        out = b''
        for a in answers:
            while not out.rstrip().endswith((b']', b']:')) and not out.endswith(b': '):
                out += os.read(fd, 4096)
            os.write(fd, a.encode() + b'\n')
            out = b''
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
        _, status = os.waitpid(pid, 0)
        self.assertEqual(status, 0)

    def test_interactive_answers(self):
        self.ask(['Shop', 'y', '/srv/wt/shop', 'n'])
        c = json.load(open(self.cfg))
        self.assertEqual((c['title'], c['worktrees'], c['worktree_dir']), ('Shop', True, '/srv/wt/shop'))
        self.assertFalse(os.path.exists(self.hook))

    def test_interactive_relative_worktree_folder_is_rejected_then_full_path_accepted(self):
        self.ask(['Shop', 'y', 'rel/dir', '../x', '/srv/wt/shop', 'n'])
        self.assertEqual(json.load(open(self.cfg))['worktree_dir'], '/srv/wt/shop')

    def test_interactive_tilde_worktree_folder_is_expanded(self):
        self.ask(['Shop', 'y', '~/wt/shop', 'n'])
        self.assertEqual(json.load(open(self.cfg))['worktree_dir'], os.path.expanduser('~/wt/shop'))

    def test_interactive_enter_gives_defaults(self):
        self.ask(['', '', ''])
        c = json.load(open(self.cfg))
        self.assertEqual((c['title'], c['worktrees']), ('My App', False))
        self.assertNotIn('worktree_dir', c)
        self.assertTrue(os.path.exists(self.hook))

    def test_interactive_default_worktree_folder_is_expanded(self):
        self.ask(['', 'y', '', ''])
        self.assertEqual(json.load(open(self.cfg))['worktree_dir'], os.path.expanduser('~/worktrees/My App'))


if __name__ == '__main__':
    unittest.main()
