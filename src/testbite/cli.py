"""testbite — do your tests bite? Mutation-test only the lines you just changed.

    testbite -- pytest -q                 # uncommitted changes vs HEAD
    testbite --base main -- npm test      # everything on this branch
    testbite --list                       # show planned mutants, run nothing

Exit codes: 0 = every mutant killed (or score >= --min-score), 1 = survivors,
2 = setup error or the test suite fails before any mutation.
"""
import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .diff import changed_lines, git
from .mutate import plan

BACKUP_DIR = "testbite-backup"  # lives inside .git/, never shows up as a change


def repo_root():
    try:
        return Path(git("rev-parse", "--show-toplevel").strip())
    except (RuntimeError, FileNotFoundError):
        sys.exit("testbite: not inside a git repository")


def git_dir(root):
    return Path(root, git("rev-parse", "--git-dir", cwd=root).strip())


def restore_backup(root):
    """Put back files left mutated by a run that was killed hard."""
    bdir = git_dir(root) / BACKUP_DIR
    if not bdir.exists():
        return 0
    n = 0
    for f in bdir.rglob("*"):
        if f.is_file():
            target = Path(root, f.relative_to(bdir))
            target.write_bytes(f.read_bytes())
            f.unlink()
            n += 1
    for d in sorted(bdir.rglob("*"), reverse=True):
        d.rmdir()
    bdir.rmdir()
    return n


def run_tests(cmd, root, timeout):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    start = time.monotonic()
    p = subprocess.Popen(cmd, shell=True, cwd=root, env=env, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        code = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        return "timeout", time.monotonic() - start
    return ("pass" if code == 0 else "fail"), time.monotonic() - start


def main(argv=None):
    ap = argparse.ArgumentParser(prog="testbite", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="test command, after --")
    ap.add_argument("--base", default="HEAD", help="git ref to diff against (default HEAD)")
    ap.add_argument("--staged", action="store_true", help="only staged changes")
    ap.add_argument("--no-untracked", action="store_true", help="ignore new untracked files")
    ap.add_argument("--max", type=int, default=60, help="max mutants to run (default 60)")
    ap.add_argument("--per-line", type=int, default=3, help="max mutants per line (default 3)")
    ap.add_argument("--timeout", type=float, help="seconds per test run (default 3x baseline + 5)")
    ap.add_argument("--min-score", type=float, default=100, help="exit 0 if kill %% >= this (default 100)")
    ap.add_argument("--list", action="store_true", help="print planned mutants and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--restore", action="store_true", help="restore files from an interrupted run")
    ap.add_argument("--version", action="version", version=f"testbite {__version__}")
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd

    root = repo_root()
    restored = restore_backup(root)
    if restored:
        print(f"testbite: restored {restored} file(s) left mutated by an interrupted run", file=sys.stderr)
    if a.restore:
        return 0

    files = changed_lines(root, base=a.base, staged=a.staged, untracked=not a.no_untracked)
    read = lambda p: Path(root, p).read_text()
    mutants = plan(files, read, per_line=a.per_line, limit=a.max)
    if not mutants:
        msg = "no mutable source lines in the diff (test files and non-code are skipped)"
        print(json.dumps({"mutants": [], "message": msg}) if a.json else f"testbite: {msg}")
        return 0

    if a.list:
        for m in mutants:
            print(f"{m.file}:{m.line}  [{m.operator}]  {m.original.strip()}  →  {m.mutated.strip()}")
        print(f"{len(mutants)} mutants on {len({(m.file, m.line) for m in mutants})} lines", file=sys.stderr)
        return 0
    if not cmd:
        ap.error("give a test command after --, e.g.  testbite -- pytest -q")
    cmd_str = shlex.join(cmd) if len(cmd) > 1 else cmd[0]

    tty = sys.stderr.isatty() and not a.json
    status, base_secs = run_tests(cmd_str, root, timeout=a.timeout or 1800)
    if status != "pass":
        print(f"testbite: the test command {status}s before any mutation; fix that first:\n  {cmd_str}",
              file=sys.stderr)
        return 2
    timeout = a.timeout or base_secs * 3 + 5

    originals = {f: Path(root, f).read_bytes() for f in {m.file for m in mutants}}
    bdir = git_dir(root) / BACKUP_DIR
    for f, data in originals.items():
        (bdir / f).parent.mkdir(parents=True, exist_ok=True)
        (bdir / f).write_bytes(data)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    try:
        for i, m in enumerate(mutants, 1):
            src = originals[m.file].decode().split("\n")
            src[m.line - 1] = m.mutated
            Path(root, m.file).write_text("\n".join(src))
            result, m.seconds = run_tests(cmd_str, root, timeout)
            m.status = {"pass": "survived", "fail": "killed", "timeout": "timeout"}[result]
            Path(root, m.file).write_bytes(originals[m.file])
            if tty:
                print(f"\r[{i}/{len(mutants)}] {m.status:<8}", end="", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        print("\ntestbite: interrupted", file=sys.stderr)
        return 130
    finally:
        for f, data in originals.items():
            Path(root, f).write_bytes(data)
        restore_backup(root)
        if tty:
            print("\r" + " " * 30 + "\r", end="", file=sys.stderr)

    ran = [m for m in mutants if m.status != "pending"]
    survived = [m for m in ran if m.status == "survived"]
    killed = len(ran) - len(survived)
    score = 100.0 * killed / len(ran) if ran else 100.0

    if a.json:
        print(json.dumps({"score": round(score, 1), "killed": killed, "survived": len(survived),
                          "baseline_seconds": round(base_secs, 2),
                          "mutants": [m.as_dict() for m in ran]}, indent=2))
    else:
        lines = len({(m.file, m.line) for m in ran})
        print(f"testbite: {len(ran)} mutants on {lines} changed lines · {killed} killed · "
              f"{len(survived)} survived · score {score:.0f}%")
        for m in survived:
            print(f"\nSURVIVED  {m.file}:{m.line}  [{m.operator}]")
            print(f"  - {m.original.strip()}")
            print(f"  + {m.mutated.strip()}")
        if survived:
            print("\nEach survivor is a change to your code that no test noticed. Add or tighten a test "
                  "so it fails on that change, then run testbite again.")
    return 0 if score >= a.min_score else 1


if __name__ == "__main__":
    sys.exit(main())
