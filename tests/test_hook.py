import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "stop.py"
TEST_CMD = f"{sys.executable} -m pytest -q -p no:cacheprovider"


def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    sh(r, "git", "init", "-q")
    sh(r, "git", "config", "user.email", "t@t")
    sh(r, "git", "config", "user.name", "t")
    (r / "lib.py").write_text("def big(n):\n    return n > 10\n")
    (r / "test_lib.py").write_text("from lib import big\n\ndef test_a():\n    assert big(100)\n")
    sh(r, "git", "add", ".")
    sh(r, "git", "commit", "-qm", "i")
    (r / "lib.py").write_text("def big(n):\n    return n > 10  # edited\n")
    return r


def stop(tmp_path, r, **extra):
    env = {**os.environ, "TESTBITE_STATE": str(tmp_path / "state"), "TESTBITE_CONFIG": str(tmp_path / "trusted.json")}
    env.pop("TESTBITE_CMD", None)
    env.update(extra)
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(r), "session_id": "s"}),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def trust(tmp_path, r):
    env = {**os.environ, "PYTHONPATH": str(HOOK.parent.parent / "src"), "TESTBITE_CONFIG": str(tmp_path / "trusted.json")}
    subprocess.run([sys.executable, "-m", "testbite", "trust", "--", *TEST_CMD.split()], cwd=r, env=env, check=True,
                   capture_output=True)


def test_untrusted_repo_is_never_run(tmp_path):
    r = repo(tmp_path)
    (r / ".testbite").write_text("touch PWNED")  # a repo cannot pick its own command
    assert stop(tmp_path, r) == (0, "")
    assert not (r / "PWNED").exists()


def test_trusted_repo_blocks_once_per_change_and_max_twice(tmp_path):
    r = repo(tmp_path)
    trust(tmp_path, r)
    code, err = stop(tmp_path, r)
    assert code == 2 and "SURVIVED" in err
    assert stop(tmp_path, r) == (0, "")  # same diff: not re-run
    (r / "lib.py").write_text("def big(n):\n    return n > 20\n")
    assert stop(tmp_path, r)[0] == 2  # new diff: second and last block
    (r / "lib.py").write_text("def big(n):\n    return n > 30\n")
    assert stop(tmp_path, r) == (0, "")  # cap reached
    assert "n > 30" in (r / "lib.py").read_text()
