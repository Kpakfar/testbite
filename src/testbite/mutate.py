"""Line-level mutation operators.

Each operator looks at one source line and proposes small edits a real bug could
look like: an off-by-one comparison, a flipped boolean, a dropped call. Matching
runs on a masked copy of the line (string literals and comments blanked out) so
text inside strings is never mutated.
"""
import re
from dataclasses import dataclass


@dataclass
class Mutant:
    file: str
    line: int
    operator: str
    original: str
    mutated: str
    status: str = "pending"  # killed | survived | timeout | pending
    seconds: float = 0.0

    def as_dict(self):
        return self.__dict__.copy()


STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')
COMMENT_RE = {"python": re.compile(r"#.*$"), "ruby": re.compile(r"#.*$")}
C_COMMENT_RE = re.compile(r"//.*$|/\*.*?\*/")

SKIP_LINE_RE = re.compile(
    r"^\s*(import |from \S+ import |#include|package |using |require\(|export \{|@|def |async def |class "
    r"|function |func |fn |pub fn |interface |type |struct |enum |module |namespace |\}?\s*else\b|\}?\s*$)"
)


def mask(line, lang):
    """Same-length copy of the line with strings and comments replaced by \\0."""
    blank = lambda m: "\0" * len(m.group(0))
    out = STRING_RE.sub(blank, line)
    if lang in COMMENT_RE:
        out = COMMENT_RE[lang].sub(blank, out)
    else:
        out = C_COMMENT_RE.sub(blank, out)
    return out


def balanced(s):
    return all(s.count(a) == s.count(b) for a, b in ("()", "[]", "{}"))


def _subs(line, masked, pattern, repl, name):
    """One mutant per match of `pattern` in the masked line."""
    out = []
    for m in re.finditer(pattern, masked):
        new = repl(m.group(0)) if callable(repl) else repl
        if new is None:
            continue
        out.append((name, line[: m.start()] + new + line[m.end():]))
    return out


COMPARE = {"==": "!=", "!=": "==", "===": "!==", "!==": "===",
           "<": "<=", "<=": "<", ">": ">=", ">=": ">"}


def mutants_for_line(line, lang):
    """Return [(operator, mutated_line)] for one source line."""
    stripped = line.strip()
    if not stripped or SKIP_LINE_RE.match(line):
        return []
    masked = mask(line, lang)
    if not masked.strip("\0 \t"):
        return []  # whole line is a comment or string
    out = []

    # boundary / equality: spaced operators only, so generics (List<T>) and arrows are left alone
    out += _subs(line, masked, r"(?<=\s)(===|!==|==|!=|<=|>=|<|>)(?=\s)",
                 lambda op: COMPARE[op], "comparison")

    # logic
    if lang in ("python", "ruby"):
        out += _subs(line, masked, r"(?<=\s)and(?=\s)", "or", "logic")
        out += _subs(line, masked, r"(?<=\s)or(?=\s)", "and", "logic")
    if lang != "python":
        out += _subs(line, masked, r"&&", "||", "logic")
        out += _subs(line, masked, r"\|\|", "&&", "logic")

    # boolean literals
    if lang == "python":
        out += _subs(line, masked, r"\bTrue\b", "False", "boolean")
        out += _subs(line, masked, r"\bFalse\b", "True", "boolean")
    else:
        out += _subs(line, masked, r"\btrue\b", "false", "boolean")
        out += _subs(line, masked, r"\bfalse\b", "true", "boolean")

    # arithmetic, spaced binary operators only
    arith = {"+": "-", "-": "+", "*": "/", "/": "*"}
    out += _subs(line, masked, r"(?<=\s)[-+*/](?=\s)", lambda op: arith[op], "arithmetic")

    # integer constants (not parts of identifiers or floats)
    out += _subs(line, masked, r"(?<![\w.])\d+(?![\w.])", lambda n: str(int(n) + 1), "constant")

    # negate a whole condition
    indent = line[: len(line) - len(line.lstrip())]
    if lang == "python":
        m = re.match(r"^(\s*)(if|elif|while) (.+):\s*$", masked)
        if m and "\0" not in m.group(3)[-1:]:
            cond = line[m.start(3): m.end(3)]
            out.append(("negate", f"{m.group(1)}{m.group(2)} not ({cond}):"))
    elif lang == "go":
        m = re.match(r"^(\s*)(\}\s*else\s+)?if (.+) \{\s*$", masked)
        if m and ";" not in m.group(3):
            cond = line[m.start(3): m.end(3)]
            out.append(("negate", f"{m.group(1)}{m.group(2) or ''}if !({cond}) {{"))
    else:
        m = re.match(r"^(\s*)(\}\s*else\s+)?(if|while)\s*\((.+)\)\s*(\{?)\s*$", masked)
        if m and balanced(m.group(4)):
            cond = line[m.start(4): m.end(4)]
            out.append(("negate", f"{m.group(1)}{m.group(2) or ''}{m.group(3)} (!({cond})) {m.group(5)}".rstrip()))

    # return value
    if lang == "python":
        m = re.match(r"^(\s*)return (.+)$", masked)
        if m and line[m.start(2):].strip() not in ("None", "") and balanced(masked):
            out.append(("return", f"{m.group(1)}return None"))
    elif lang == "js":
        m = re.match(r"^(\s*)return (.+?);?\s*$", masked)
        if m and balanced(masked) and m.group(2).strip() not in ("undefined", "null", "{", "("):
            out.append(("return", f"{m.group(1)}return undefined;"))

    # drop a statement
    if balanced(masked) and not masked.rstrip().endswith((":", ",", "\\", "(", "[", "{", "=")):
        if lang == "python":
            if not re.match(r"^\s*(return|raise|yield|pass|break|continue|else|elif|if|for|while|with|try|except|finally)\b", line):
                out.append(("delete", f"{indent}pass"))
        elif lang in ("js", "c"):
            if re.match(r"^\s*[\w.$\[\]]+\s*(\(|[-+*/]?=[^=])", masked) and masked.rstrip().endswith(";") \
                    and not re.match(r"^\s*(let|const|var|return|throw|int|long|float|double|bool|char|auto|final|val)\b", line):
                out.append(("delete", indent + ("/* testbite */;" if lang == "c" else ";")))
        elif lang == "go":
            if re.match(r"^\s*[\w.]+\(.*\)\s*$", masked):
                out.append(("delete", f"{indent}// testbite: deleted"))

    # dedupe, keep order
    seen, uniq = set(), []
    for name, new in out:
        if new != line and new not in seen:
            seen.add(new)
            uniq.append((name, new))
    return uniq


def plan(files, read, per_line=3, limit=60):
    """files: {path: [line numbers]}, read(path) -> text. Returns a list of Mutants.

    Takes at most `per_line` mutants from each line (one per operator first), then
    round-robins across lines so a big diff still gets spread-out coverage.
    """
    from .diff import language

    per_line_lists = []
    for path, lines in files.items():
        lang = language(path)
        src = read(path).splitlines()
        for n in lines:
            if n - 1 >= len(src):
                continue
            original = src[n - 1]
            cands = mutants_for_line(original, lang)
            by_op, rest = [], []
            ops_seen = set()
            for name, new in cands:
                (rest if name in ops_seen else by_op).append((name, new))
                ops_seen.add(name)
            chosen = (by_op + rest)[:per_line]
            if chosen:
                per_line_lists.append([Mutant(path, n, name, original, new) for name, new in chosen])
    out, i = [], 0
    while len(out) < limit and any(i < len(l) for l in per_line_lists):
        for l in per_line_lists:
            if i < len(l) and len(out) < limit:
                out.append(l[i])
        i += 1
    out.sort(key=lambda m: (m.file, m.line))
    return out
