#!/usr/bin/env python3
"""Claude Code Stop hook: don't let the agent say "done" while changed lines are untested.

Opt-in per repo: put your test command in a `.testbite` file at the repo root
(one line, e.g. `pytest -q`) or set TESTBITE_CMD. Without either, this hook does nothing.
Blocks at most once per turn (stop_hook_active) so it can never loop.
"""
import json
import os
import shutil
import subprocess
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if data.get("stop_hook_active"):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True)
    if top.returncode:
        return 0
    root = top.stdout.strip()
    cmd = os.environ.get("TESTBITE_CMD")
    cfg = os.path.join(root, ".testbite")
    if not cmd and os.path.isfile(cfg):
        lines = open(cfg).read().strip().splitlines()
        cmd = lines[0].strip() if lines else None
    exe = shutil.which("testbite")
    if not cmd or not exe:
        return 0
    r = subprocess.run([exe, "--max", os.environ.get("TESTBITE_MAX", "20"), "--", cmd],
                       cwd=root, capture_output=True, text=True, timeout=900)
    if r.returncode == 1:
        sys.stderr.write("testbite: your changes are not covered by tests that fail when the code breaks.\n"
                         + r.stdout[-3000:]
                         + "\nAdd or tighten tests so each survivor above turns red, then finish.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
