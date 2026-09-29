"""Find the source lines a change touched: git diff hunks plus untracked files."""
import re
import subprocess
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

SOURCE_EXT = {
    ".py": "python",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js", ".ts": "js", ".tsx": "js",
    ".go": "go",
    ".java": "c", ".kt": "c", ".cs": "c", ".c": "c", ".h": "c", ".cc": "c", ".cpp": "c",
    ".hpp": "c", ".rs": "c", ".swift": "c", ".php": "c", ".dart": "c", ".scala": "c",
    ".rb": "ruby",
}

TEST_NAME_RE = re.compile(
    r"(^test_.*\.py$|_test\.py$|^conftest\.py$|_test\.go$|\.(test|spec)\.[cm]?[jt]sx?$"
    r"|Tests?\.(java|kt|cs|swift)$|_spec\.rb$|_test\.rb$)"
)
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testdata", "__mocks__"}


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def language(path):
    return SOURCE_EXT.get(Path(path).suffix.lower())


def is_test_file(path):
    p = Path(path)
    return bool(TEST_NAME_RE.search(p.name)) or any(part in TEST_DIRS for part in p.parts[:-1])


def parse_diff(text):
    """Unified diff (-U0) -> {path: set(new-side line numbers)}."""
    changed, path = {}, None
    for line in text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
        elif path and (m := HUNK_RE.match(line)):
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if count:
                changed.setdefault(path, set()).update(range(start, start + count))
    return changed


def changed_lines(root, base="HEAD", staged=False, untracked=True):
    """{relative path: sorted line numbers} for mutable, non-test source files."""
    args = ["diff", "--unified=0", "--no-color", "--no-ext-diff", "--no-renames"]
    if staged:
        args.append("--cached")
    if base:
        args.append(base)
    try:
        changed = parse_diff(git(*args, cwd=root))
    except RuntimeError:
        if base != "HEAD":
            raise
        changed = {}  # repo without commits yet: everything is untracked
    if untracked and not staged:
        for f in git("ls-files", "--others", "--exclude-standard", cwd=root).splitlines():
            full = Path(root, f)
            if full.is_file():
                n = len(full.read_text(errors="replace").splitlines())
                changed.setdefault(f, set()).update(range(1, n + 1))
    return {
        f: sorted(lines) for f, lines in sorted(changed.items())
        if language(f) and not is_test_file(f) and Path(root, f).is_file()
    }
