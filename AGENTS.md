# AGENTS.md

Operating rules for AI agents working in this repo (Claude Code, Codex, Copilot,
Cursor, and anything else that reads `AGENTS.md`).

This file is **AI-only**. Rules that apply to humans and AI alike — commit
format, branch naming, dev setup, testing, migrations — live in
[CONTRIBUTING.md](CONTRIBUTING.md) and are **not** repeated here. Read both.

---

## Doc map

| File | Audience | Contains |
|------|----------|----------|
| [README.md](README.md) | Everyone | What ownmail is, install, usage |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Humans + AI | Repo rules: commits, branches, PRs, setup, testing, migrations |
| **AGENTS.md** (this file) | AI only | Autonomy policy, session start, hygiene guardrails, STOP list |
| [CLAUDE.md](CLAUDE.md) | Claude Code | Thin pointer — imports this file |
| [.github/copilot-instructions.md](.github/copilot-instructions.md) | Copilot | Thin pointer — points at this file |
| `backlog/tasks/` | Everyone | The progress ledger — see below |
| `backlog/docs/` | Everyone | Design docs and decision records |

---

## Session start

**If the user gives you no specific direction at session start, do not ask which
task to work on. Pick one and start.**

Selection order:

1. **Resume before you start.** If any task is `In Progress`, finish it before
   pulling new work. Check the working tree too — an uncommitted diff is
   in-progress work whether or not a task says so.
2. **Otherwise take the next `To Do` task**: lowest `ordinal` within the
   earliest open milestone. `backlog task list --plain` and `backlog board`
   show this directly. Sequencing rationale lives in
   `backlog/docs/doc-4 - Execution order`.
3. **Respect `dependencies:`.** A task whose dependencies aren't `Done` is not
   eligible — skip to the next one.
4. **If several tasks tie**, or the ledger contradicts itself (two tasks
   `In Progress`, an ordinal collision, a dependency on a task that no longer
   exists), pick the one you judge best, say which you picked and why in your
   first message, and keep going. Don't stall on the tie.

Say what you're starting on in one line, then work.

## Autonomy

Bias to action. You are expected to make progress without a human unblocking
each step.

- **Commit at every reasonable checkpoint** — a passing test, a completed
  refactor, a finished subtask. Don't wait to be asked to commit.
- **Never end a turn with a dirty working tree.** Either commit the work or
  explain why it isn't committable. The next session starts from the repo, not
  from this conversation — anything uncommitted is invisible to it.
- **Keep the backlog task current as you go**, not at the end: set `In Progress`
  when you start, tick acceptance criteria as they're actually met, set `Done`
  when they all are. Record decisions and caveats in the task's Implementation
  Notes.
- **Finish the whole task.** If part of it turns out to be blocked, do
  everything else and state plainly what you left undone and why.

### Where to commit

You are working as the maintainer, so
[CONTRIBUTING.md § How changes land](CONTRIBUTING.md#how-changes-land) applies:
commit to `master` directly, except for the change types listed there — which
are the same ones on the STOP list below. For those, branch and open a PR
rather than pushing to `master`, and let CI and a human weigh in before it
lands.

### Staging

Commit format and branch naming are in
[CONTRIBUTING.md](CONTRIBUTING.md#commit-messages). Two things specific to
agents:

- **Never `git add -A` or `git add .`** — it stages files you didn't look at.
  Run `git status` first, then `git add <path>` for each file you actually
  changed.
- **A dirty file you didn't touch is a signal, not noise.** Someone (or a prior
  session) left work in the tree. Read it and deal with it deliberately —
  commit it separately, or say it's there — before layering your own changes on
  top.

## The progress ledger

`backlog/` is the durable record of in-flight work. Chat history is not — it
disappears. Anything a future session needs to know goes in a task or a doc.

```bash
backlog task list --plain               # what's open
backlog task <id> --plain               # read one task
backlog task edit <id> -s "In Progress" # update status
backlog task edit <id> --check-ac 1     # tick acceptance criterion 1 (--ac ADDS one)
backlog task create "Title" -d "..."    # file new work
backlog doc create "Title"              # record a decision or design
```

Rules:

- **Discovered work gets filed, not silently absorbed.** If you find a bug or
  cleanup outside the current task's scope, `backlog task create` it and move
  on. Don't expand the task you're on to cover it.
- **Don't tick an acceptance criterion you haven't actually verified.** "Should
  work" is not verified.
- **A task is `Done` only when every AC is met**, tests pass, and the work is
  committed.
- **The ledger is public. Keep one person's data out of it.** `backlog/` ships
  in the repo, and so do commit messages — both are permanent once pushed.
  Evidence from a real archive is welcome and makes a bug credible: "confirmed
  against a real archive", a label name, a reproduction. What never goes in is
  anything tied to one install — filesystem paths, account names or addresses,
  message counts, folder trees. Write the finding, not the fingerprint.
- **A task is product work.** Running a one-off operation on your own archive
  isn't a task, even when a task made it possible. File the capability; the
  operator runs it.

## Code hygiene

- **Survey before you add.** Search for an existing helper before writing a new
  one. Two functions doing the same thing is worse than one awkward one.
- **Subtractive bias.** Deleting code is a legitimate and preferred outcome.
  When a change makes something unreachable, delete it in the same commit.
- **No dead code, no speculative abstractions.** Don't add a parameter, hook, or
  layer for a use case that doesn't exist yet. Write for what's needed now.
- **Match the surrounding code.** Naming, comment density, error handling, and
  idiom should look like the file you're editing, not like your defaults.
- **One concern per file.** File size is a smell, not a hard limit — a 900-line
  file that does one thing is fine; a 200-line file doing three isn't.

## Test hygiene

- **A test must be able to fail.** If it passes against deliberately broken
  code, it tests nothing. Sanity-check new tests by breaking the code under
  test.
- **Cover reachable behavior, not a percentage.** The coverage gate is a floor
  against regressions, not a target to game with tests that assert nothing.
- **No redundant tests.** If an existing test already covers the path, extend it
  rather than adding a near-duplicate.
- **Never weaken a test to make it pass.** If a test fails, the default
  assumption is that the code is wrong. Loosening an assertion or deleting a
  case to get green is only acceptable when the test's expectation is itself
  demonstrably wrong — and say so explicitly when you do it.

## Project invariants

These are load-bearing. Changing any of them is a STOP (see below).

1. **Files are the source of truth.** The `.eml` files are the archive; the
   SQLite database is a rebuildable index. Never write code that makes the DB
   authoritative or that loses data present only in the DB.
2. **Fail gracefully.** Malformed emails, encoding garbage, network errors, and
   partial server responses are normal input, not exceptional. Skip and report;
   don't crash a 15,000-email run over one bad message.
3. **Long operations are resumable.** Anything that loops over emails must be
   Ctrl-C safe and restartable: batch-commit progress, and leave consistent
   state at every batch boundary.
4. **Minimal dependencies.** Adding a runtime dependency needs a real
   justification. The stdlib is usually enough.

## STOP and ask the human when

Stop and ask before doing any of these — don't decide unilaterally:

- **Database schema or migration changes.** Adding/renaming/dropping columns or
  tables, changing indexes, anything that touches an existing user's `ownmail.db`.
- **Credential or keychain handling.** How secrets are stored, named, read, or
  logged. Never print or write a secret anywhere, including debug output.
- **The OAuth flow.** Scopes, token refresh, the consent path, the client
  credential handling in `providers/gmail.py`.
- **Irreversible git operations.** Force-push, history rewrite, hard reset over
  uncommitted work, branch deletion, tag deletion.
- **Anything that deletes or moves user email files.** The archive is
  irreplaceable data. Deleting a `.eml` file, moving the archive, or rewriting
  filenames en masse gets human sign-off first.
- **Adding a runtime dependency**, or bumping the minimum Python version.
- **Publishing** — `scripts/publish.sh`, PyPI uploads, git tags, releases.

Working on the *tests* for these areas is fine. It's changing the behavior that
needs sign-off.

Once signed off, these also go through a PR rather than straight to `master`
— see [Where to commit](#where-to-commit).

## Before you finish a turn

- `pre-commit run -a --hook-stage pre-push` passes. (That's ruff, deptry, and
  the full suite with the coverage gate — the same set CI runs.)
- The backlog task reflects reality — status, ACs, notes.
- The working tree is clean.
