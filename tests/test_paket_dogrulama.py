"""Real synthetic subprocesses: bounded responses, cleanup and data isolation."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('package_probe', Path(__file__).resolve().parents[1]/'packaging/dogrulama.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class PackageProbes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = probe.ortam(Path(self.tmp.name))
        self.processes = []
        original = probe.asyncio.create_subprocess_exec
        async def recorded(*args, **kwargs):
            process = await original(*args, **kwargs)
            self.processes.append(process)
            return process
        self.patcher = patch.object(probe.asyncio, 'create_subprocess_exec', recorded)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def tearDown(self):
        self.assertTrue(all(p.returncode is not None for p in self.processes), 'Owned child left running')

    def command(self, body):
        return [sys.executable, '-u', '-c', 'import sys,json,time; sys.stdin.readline(); ' + body]

    def test_success_keeps_stdin_open_until_response_and_reaps_child(self):
        body = "print(''); print(json.dumps({'id':1,'result':{'serverInfo':{}}})); time.sleep(20)"
        response, data = probe.sorgula(self.command(body), {'id':1}, env=self.env, timeout=3)
        self.assertEqual(response['id'], 1)
        self.assertEqual(data, b'')

    def test_timeout_does_not_leave_child_or_block_on_stderr(self):
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'TimeoutError'):
            probe.sorgula(self.command("sys.stderr.write('synthetic error'); sys.stderr.flush(); time.sleep(20)"),
                          {}, env=self.env, timeout=.3)
        self.assertLess(time.monotonic()-started, 6)

    def test_full_stderr_pipe_and_binary_response(self):
        body = "sys.stderr.write('x'*2000000); sys.stderr.flush(); print(json.dumps({'n':4})); sys.stdout.flush(); sys.stdout.buffer.write(b'abcd'); sys.stdout.flush(); time.sleep(20)"
        header, data = probe.sorgula(self.command(body), {}, env=self.env, timeout=5, ikili_alan='n')
        self.assertEqual(header['n'], 4)
        self.assertEqual(data, b'abcd')

    def test_truncated_binary_response_fails_and_reaps_child(self):
        body = "print(json.dumps({'n':5})); sys.stdout.flush(); sys.stdout.buffer.write(b'ab'); sys.stdout.flush()"
        with self.assertRaisesRegex(RuntimeError, 'IncompleteReadError'):
            probe.sorgula(self.command(body), {}, env=self.env, timeout=3, ikili_alan='n')

    def test_missing_binary_bytes_are_subject_to_deadline(self):
        with self.assertRaisesRegex(RuntimeError, 'TimeoutError'):
            probe.sorgula(self.command("print(json.dumps({'n':5})); time.sleep(20)"), {},
                          env=self.env, timeout=.3, ikili_alan='n')

    def test_oversized_or_boolean_binary_length_rejected(self):
        for count in (20, True):
            with self.subTest(count=count), self.assertRaisesRegex(RuntimeError, 'Invalid binary'):
                probe.sorgula(self.command(f"print(json.dumps({{'n':{count!r}}})); time.sleep(20)"),
                              {}, env=self.env, timeout=3, ikili_alan='n', azami_bayt=10)

    def test_non_object_header_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'JSON object'):
            probe.sorgula(self.command("print('[]'); time.sleep(20)"), {}, env=self.env, timeout=3)

    def test_window_probe_accepts_live_child_and_closes_it(self):
        probe.pencere_dogrula([sys.executable, '-c', 'import time; time.sleep(20)'], env=self.env, sure=.2)

    def test_window_probe_reports_early_exit(self):
        with self.assertRaisesRegex(RuntimeError, 'Window exited'):
            probe.pencere_dogrula([sys.executable, '-c', 'raise SystemExit(2)'], env=self.env, sure=.5)

    def test_environment_drops_old_roots_and_secret_values(self):
        inherited = {'PEVRAI_POLICY':'outside', 'LIMINA_VEKIL_KOK':'outside',
                     'OKUMA_DATA_DIR':'outside', 'OPENAI_API_KEY':'synthetic-key',
                     'GH_TOKEN':'synthetic-token', 'PATH':os.environ.get('PATH','')}
        with patch.dict(os.environ, inherited, clear=True):
            env = probe.ortam(Path(self.tmp.name)/'fresh')
        self.assertNotIn('PEVRAI_POLICY', env)
        self.assertNotIn('LIMINA_VEKIL_KOK', env)
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('GH_TOKEN', env)
        self.assertEqual(env['PYTHON_KEYRING_BACKEND'], 'keyring.backends.null.Keyring')
        for key in ('USERPROFILE','HOME','APPDATA','LOCALAPPDATA','PEVRAI_VEKIL_KOK',
                    'OKUMA_DATA_DIR','OKUMA_LINK_DB','OKUMA_SETTINGS'):
            self.assertTrue(Path(env[key]).is_relative_to(Path(self.tmp.name)/'fresh'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
