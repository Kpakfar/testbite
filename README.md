# testbite

**Do your tests bite?** `testbite` breaks the lines you just changed, one small edit at a time, and tells you which breaks no test noticed.

AI coding agents write tests that pass by construction: the same session wrote the code and the assertions, so the tests assert whatever the code already does. Full mutation testing answers this, but it is slow and per-language. `testbite` only mutates the **git diff**, needs **no setup**, and works on any language it can read.

```console
$ testbite -- pytest -q
testbite: 6 mutants on 3 changed lines · 5 killed · 1 survived · score 83%

SURVIVED  shop.py:16  [arithmetic]
  - t = t + discount(p, q) * q
  + t = t + discount(p, q) / q

Each survivor is a change to your code that no test noticed. ...
```

Here the test only ever buys one item, so `* q` and `/ q` look the same. That is the gap.

## Install

```bash
pipx install git+https://github.com/Kpakfar/testbite
```

Needs Python 3.9+ and git. No other dependencies.

## Use

```bash
testbite -- pytest -q              # uncommitted changes vs HEAD (new files included)
testbite --base main -- npm test   # everything on this branch
testbite --staged -- go test ./... # only what is staged
testbite --list                    # show the planned mutants, run nothing
testbite --json -- pytest -q       # machine-readable, for agents and CI
testbite --min-score 90 -- ...     # exit 0 when at least 90% are killed
```

Exit code: `0` all killed (or above `--min-score`), `1` survivors, `2` your tests fail before any mutation.

It runs your test command once to get a baseline, then once per mutant (default cap 60, `--max` to change), with a timeout of 3x the baseline. Files are restored after every mutant, and a backup inside `.git/` repairs them if the process is killed hard (`testbite --restore`).

## What it mutates

Changed lines in Python, JS/TS, Go, Ruby and C-family files (Java, C#, Kotlin, Swift, Rust, C/C++, PHP, Dart, Scala). Test files are skipped. Per line it tries:

| Operator | Example |
|---|---|
| comparison | `>` → `>=`, `==` → `!=` |
| logic | `and` → `or`, `&&` → `\|\|` |
| boolean | `True` → `False` |
| arithmetic | `+` → `-`, `*` → `/` |
| constant | `10` → `11` |
| negate | `if x:` → `if not (x):` |
| return | `return x` → `return None` |
| delete | drop a statement |

Text inside strings and comments is never touched. The mutations are line-level text edits, not AST rewrites. That is what makes it language-agnostic and fast, and also why an occasional mutant does not compile; that counts as killed, so a score can be slightly flattering. Treat survivors as the signal, not the percentage.

## Use it with Claude Code

```
/plugin marketplace add Kpakfar/testbite
/plugin install testbite@testbite
```

You get a skill that tells the agent to run `testbite` after writing tests, and an optional **Stop hook** that refuses to let the agent finish while mutants survive. The plugin bundles its own copy of testbite, so the hook needs nothing on your PATH.

The hook is **off until you approve a test command for a repo**, from your own terminal:

```bash
cd my-project
testbite trust -- pytest -q     # approve; `testbite trust --revoke` to undo
```

The approval is stored in `~/.config/testbite/trusted.json`, outside the repo, so a cloned repository can never choose the command your hook runs. Once approved, on each Stop the hook mutates the diff (max 20 mutants, 10 minute budget) and blocks with the survivors listed. It skips if the code hasn't changed since its last run and blocks at most twice per session, so it cannot loop or nag. Set `TESTBITE_MAX` to change the mutant cap.

## Develop

```bash
python3 -m pytest
```

MIT
