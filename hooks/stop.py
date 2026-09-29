#!/usr/bin/env python3
"""Claude Code Stop hook: don't let the agent say "done" while changed lines are untested.

Opt-in and safe by design: it only runs a test command YOU approved outside the repo
(`testbite trust -- pytest -q`, or the TESTBITE_CMD env var), never one read from the repo.
It skips when the code hasn't changed since its last run this session, and blocks at most
twice per session. Self-contained: uses the testbite source bundled with this plugin.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
from testbite import trust  # noqa: E402

MAX_BLOCKS = 2


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True).stdout


def fingerprint(root):
    diff = sh("git", "diff", "HEAD", "--no-color", cwd=root)
    other = sh("git", "ls-files", "--others", "--exclude-standard", cwd=root)
    extra = "".join(f"{f}:{Path(root, f).stat().st_mtime_ns}" for f in other.splitlines() if Path(root, f).is_file())
    return hashlib.sha256((diff + other + extra).encode()).hexdigest()


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if data.get("stop_hook_active"):
        return 0
    root = sh("git", "rev-parse", "--show-toplevel", cwd=data.get("cwd") or os.getcwd()).strip()
    if not root:
        return 0
    cmd = os.environ.get("TESTBITE_CMD") or trust.command_for(root)
    if not cmd:
        return 0
    state_dir = Path(os.environ.get("TESTBITE_STATE", "~/.cache/testbite")).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / (hashlib.sha1(f"{root}{data.get('session_id')}".encode()).hexdigest() + ".json")
    try:
        state = json.loads(state_file.read_text())
    except (OSError, ValueError):
        state = {"hash": None, "blocks": 0}
    fp = fingerprint(root)
    if fp == state["hash"] or state["blocks"] >= MAX_BLOCKS:
        return 0
    state["hash"] = fp
    state_file.write_text(json.dumps(state))
    env = dict(os.environ, PYTHONPATH=str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    p = subprocess.Popen([sys.executable, "-m", "testbite", "--max", os.environ.get("TESTBITE_MAX", "20"),
                          "--budget", "600", "--", cmd],
                         cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        out, _ = p.communicate(timeout=840)
    except subprocess.TimeoutExpired:
        p.terminate()  # SIGTERM lets testbite restore the mutated file before exiting
        try:
            p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
        return 0
    if p.returncode == 1:
        state["blocks"] += 1
        state_file.write_text(json.dumps(state))
        sys.stderr.write("testbite: your changes are not covered by tests that fail when the code breaks.\n"
                         + out[-3000:] + "\nAdd or tighten tests so each survivor above turns red, then finish.\n"
                         "If a survivor is a genuine no-op, say so and finish.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
