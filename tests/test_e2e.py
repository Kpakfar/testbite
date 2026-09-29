import subprocess
import sys

from testbite.cli import main


def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


def make_repo(tmp_path, tests):
    sh(tmp_path, "git", "init", "-q")
    sh(tmp_path, "git", "config", "user.email", "t@t")
    sh(tmp_path, "git", "config", "user.name", "t")
    (tmp_path / "lib.py").write_text("def big(n):\n    return n > 10\n")
    (tmp_path / "test_lib.py").write_text(tests)
    sh(tmp_path, "git", "add", ".")
    sh(tmp_path, "git", "commit", "-qm", "init")
    (tmp_path / "lib.py").write_text("def big(n):\n    return n > 10  # changed\n\n\ndef small(n):\n    return n < 5\n")


def run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["--", sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    return code, capsys.readouterr().out


def test_weak_tests_survive(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, "from lib import big, small\n\ndef test_a():\n    assert big(100)\n    assert small(1)\n")
    code, out = run(tmp_path, monkeypatch, capsys)
    assert code == 1 and "SURVIVED" in out
    assert "n < 5" in (tmp_path / "lib.py").read_text()  # file restored after the run


def test_strong_tests_kill_everything(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, "from lib import big, small\n\ndef test_a():\n    assert big(11) and not big(10) and not big(0)\n"
                        "    assert small(4) and not small(5) and not small(6)\n")
    code, out = run(tmp_path, monkeypatch, capsys)
    assert code == 0, out
