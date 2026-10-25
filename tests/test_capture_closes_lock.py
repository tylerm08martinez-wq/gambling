"""capture-closes.sh and run-daily-picks.sh share one flock (review of PR #112).

The */15 capture cron fires at 09:00, the same minute run-daily-picks.sh pulls with
--autostash, backfills CLV and commits closing_lines.json. Both take
scripts/.tracker.lock around their read-modify-write + git steps; capture SKIPS a pass
when the lock is held instead of waiting (the next pass is 15 minutes away).

The capture script is run for real against stubbed `date` (forces a game-hour) and
`python3` (records that tracker.py would have run), so no network and no tracker.
"""

import fcntl
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAPTURE = REPO / "scripts" / "capture-closes.sh"
DAILY = REPO / "scripts" / "run-daily-picks.sh"
LOCK_REL = "scripts/.tracker.lock"


def _exe(path, body):
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@unittest.skipUnless(shutil.which("flock") and shutil.which("bash"), "needs flock + bash")
class TestCaptureClosesLock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "scripts").mkdir()
        shutil.copy(CAPTURE, self.tmp / "scripts" / "capture-closes.sh")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.ran = self.tmp / "python3-ran"
        real_date = shutil.which("date")
        _exe(self.bin / "date", f'#!/bin/bash\nif [ "$1" = "+%H" ]; then echo 10; else {real_date} "$@"; fi\n')
        _exe(self.bin / "python3", f'#!/bin/bash\necho "$@" >> {self.ran}\necho "  📸 stub: T-10m"\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ.get('PATH', '')}")
        return subprocess.run(["bash", str(self.tmp / "scripts" / "capture-closes.sh")],
                              env=env, capture_output=True, text=True, timeout=60)

    def test_runs_tracker_when_the_lock_is_free(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.ran.exists(), "tracker.py capture-closes should have run")
        self.assertIn("capture-closes", self.ran.read_text())

    def test_skips_without_waiting_when_the_lock_is_held(self):
        lock = self.tmp / LOCK_REL
        with open(lock, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.ran.exists(), "must not touch closing_lines.json while locked")
        # A skipped pass is not a failure: no sentinel for the health check to alarm on.
        self.assertFalse((self.tmp / "scripts" / ".CAPTURE-FAILED").exists())
        self.assertIn("lock", (self.tmp / "scripts" / ".capture-closes.log").read_text())


class TestSharedLockFile(unittest.TestCase):
    def test_both_scripts_use_the_same_lock_file(self):
        for script in (CAPTURE, DAILY):
            with self.subTest(script=script.name):
                self.assertIn(LOCK_REL, script.read_text())

    def test_lock_file_is_gitignored(self):
        r = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", LOCK_REL])
        self.assertEqual(r.returncode, 0, f"{LOCK_REL} must be gitignored")


if __name__ == "__main__":
    unittest.main()
