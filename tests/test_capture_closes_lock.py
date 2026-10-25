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



class TestDailyRunLockSections(unittest.TestCase):
    """run-daily-picks.sh holds scripts/.tracker.lock around BOTH of its git sections —
    the morning pull + CLV backfill commit/push, and the V3 observations commit + push +
    rebase retry (#114) — and has released it before the long `claude -p` step on every
    path, so captures for 9:15-10:00 starts still run."""

    def setUp(self):
        self.lines = DAILY.read_text().splitlines()

    def _at(self, needle, start=0):
        for i in range(start, len(self.lines)):
            if needle in self.lines[i] and not self.lines[i].lstrip().startswith("#"):
                return i
        self.fail(f"{needle!r} not found after line {start}")

    def test_both_git_sections_sit_inside_a_take_release_pair(self):
        take1 = self._at('tracker_lock_take "')
        pull = self._at('git pull --rebase --autostash origin main 2>&1 | tee -a "$LOG"', take1)
        backfill = self._at("backfill-clv", pull)
        bf_push = self._at("git push origin main", backfill)
        rel1 = self._at("tracker_lock_release", bf_push)
        take2 = self._at('tracker_lock_take "', rel1)
        v3_add = self._at('git add -- "$V3_OBS"', take2)
        v3_commit = self._at('git commit -m "chore: V3 observation scan', v3_add)
        v3_push = self._at("v3_push_observations ||", v3_commit)
        rel2 = self._at("tracker_lock_release", v3_push)
        stop = self._at("exit 1", rel2)            # the rc == 2 "HEAD off main" stop
        claude = self._at('claude -p "$PROMPT"', stop)
        self.assertLess(rel2, stop, "lock must be released before the rc==2 exit path")
        # Nothing may take the lock again between the last release and claude -p.
        between = self.lines[rel2 + 1:claude]
        self.assertFalse([l for l in between if "tracker_lock_take" in l and not l.lstrip().startswith("#")])
        self.assertIn("tracker_lock_release", "\n".join(between),
                      "a final unconditional release must precede claude -p")

    def test_the_v3_retry_todo_is_resolved(self):
        self.assertNotIn("TODO(#112)", DAILY.read_text())

    @unittest.skipUnless(shutil.which("flock") and shutil.which("bash"), "needs flock + bash")
    def test_take_holds_the_lock_and_release_frees_it(self):
        text = DAILY.read_text()
        funcs = []
        for name in ("tracker_lock_take", "tracker_lock_release"):
            start = text.index(f"{name}() {{")
            end = text.index("\n}\n", start) + 3
            funcs.append(text[start:end])
        tmp = Path(tempfile.mkdtemp())
        try:
            script = "\n".join([
                f'TRACKER_LOCK="{tmp}/.tracker.lock"', f'LOG="{tmp}/log"', *funcs,
                'tracker_lock_take "test" || exit 3',
                'flock -n "$TRACKER_LOCK" true && echo LEAKED || echo HELD',
                "tracker_lock_release",
                'flock -n "$TRACKER_LOCK" true && echo FREE || echo STUCK',
            ])
            r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ["HELD", "FREE"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
