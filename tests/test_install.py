import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    def install(self, proj=None):
        return sh(os.path.join(ROOT, 'install.sh'), proj or self.repo)

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
        self.assertIn('sub="sub/"', open(h).read())
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


if __name__ == '__main__':
    unittest.main()
