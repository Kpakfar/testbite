---
name: testbite
description: Check that tests you (an AI agent) just wrote actually catch bugs, by mutation-testing only the changed lines. Use after writing or changing code plus tests, before saying a task is done, or when the user asks whether tests are meaningful.
---

# testbite

AI-written tests often pass by construction: the same session wrote the code and the assertions. `testbite` breaks your changed lines on purpose and reports which breaks no test noticed.

1. Make sure the code and its tests are written, and the suite passes.
2. Run `testbite -- <the project's test command>` (for example `testbite -- pytest -q` or `testbite -- npm test`). Add `--base main` to cover a whole branch.
3. For each `SURVIVED` entry, write or tighten a test that fails on that exact change, then rerun. Do not edit the source to satisfy testbite.
4. If a survivor is a real no-op (dead code, logging), say so instead of adding a pointless test.
5. Report the final score honestly.

Only the diff is mutated, so a run takes seconds to minutes. If the `testbite` command is missing: `pipx install git+https://github.com/Kpakfar/testbite`.

The user may have enabled a Stop hook (`testbite trust -- <cmd>`) that blocks you from finishing while mutants survive; treat its output the same way as steps 3 and 4.
