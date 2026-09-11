# Contributing to ownmail

Thanks for your interest in contributing to ownmail!

This is the rulebook for **everyone working in this repo, human and AI alike** —
commit and branch conventions, dev setup, testing, and database migrations.

> **AI agents:** read [AGENTS.md](AGENTS.md) as well. It covers the rules that
> apply only to you (autonomy, session start, the backlog ledger, the
> STOP-and-ask list) and does not repeat what's here.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/clee704/ownmail.git
cd ownmail

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install commit checks and the full test suite at push time
pre-commit install
```

## Running Locally

```bash
# Run directly
python3 -m ownmail --help

# Or after pip install -e .
ownmail --help
```

When developing the web interface, run:

```bash
ownmail serve --reload
```

Python source edits restart the server, and template edits appear on the next
page refresh. This leaves the interactive debugger disabled. `--debug` enables
both reloading and the debugger and is restricted to localhost. Add
`--no-browser` to suppress the initial browser tab.

## Code Style

- Python 3.10+ (see `requires-python` in `pyproject.toml`)
- Follow PEP 8, enforced by ruff
- Use type hints where practical
- Keep functions focused and small
- Add docstrings for public methods

### File Formatting

- No trailing whitespace
- Files must end with a newline (Linux style)
- Use LF line endings only, no CRLF (Linux style)

## Testing

```bash
pytest
```

### Code Coverage

We enforce a coverage barrier to prevent regressions. Run tests with coverage:

```bash
pytest --cov=ownmail --cov-report=term-missing
```

Current minimum coverage: **95%**, including branches (configured in `pyproject.toml`).

When adding new code, write tests to maintain or improve coverage. The build will fail if coverage drops below the barrier.

## Before Committing

`pre-commit install` wires up two stages, split by how long they take:

| Stage | Checks | Cost |
|---|---|---|
| **on commit** | File hygiene (trailing whitespace, final newline, LF endings), `ruff check --fix`, `ruff format`, `deptry` | ~0.5s |
| **on push** | The above, plus `pytest` with the coverage gate | ~11s |

Tests run at push rather than at commit deliberately: it's once per push no
matter how many commits it carries, and a push is the point where anything
actually becomes visible to anyone else. Committing stays cheap enough to do
constantly.

To run the full set by hand, against the whole repo:

```bash
pre-commit run -a --hook-stage pre-push
```

The individual pieces, if you'd rather run them directly:

```bash
ruff check .          # Lint
ruff format .         # Format
pytest --cov=ownmail  # Tests + coverage gate
```

Most lint errors can be auto-fixed with `ruff check . --fix`.

**A clean local run does not guarantee a green build.** ownmail supports Python
3.10–3.12 and you are probably developing on something newer, so CI is testing
versions you aren't. Local hooks are a fast filter; CI is the gate.

> `.eml` files under `tests/fixtures/` are excluded from the formatting hooks —
> they're byte-exact test inputs, several deliberately malformed or truncated.
> Don't "fix" them.

## Continuous Integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to
`master` and every PR:

- **lint** — `ruff check`, `ruff format --check`, `deptry` (once, on 3.12)
- **test** — the full suite with coverage across Python 3.10, 3.11, and 3.12,
  with Node.js available so the HTML-sanitizer integration tests actually run
  instead of skipping

The matrix mirrors the versions in `pyproject.toml`'s classifiers. If you change
the supported Python range, update both.

## How changes land

Which path applies depends on whether you have write access — the two aren't
alternatives you choose between.

**Outside contributors** — fork the repo, branch, and open a PR. CI must pass
before it's merged. See [Pull Requests](#pull-requests) below.

**Maintainers** — commit to `master` directly. This is a small project with one
maintainer; routing every change through a PR you review and merge yourself
adds a CI wait without adding a reviewer.

Use a PR anyway when the change is one of these:

- Database schema or migrations — anything touching an existing user's `ownmail.db`
- Credential/keychain handling, or the Gmail OAuth flow
- Anything that deletes or moves archived `.eml` files
- Adding a runtime dependency, or changing the supported Python range

That's the same list AGENTS.md flags as STOP-and-ask, for the same reason:
these are the changes that are expensive or impossible to walk back, so they're
worth a green matrix and a deliberate second look before they land.

## Branches

Branch off `master`, one branch per change:

```
<type>/<short-desc>
```

`<type>` is the same set as the commit types below; `<short-desc>` is a few
lowercase, hyphenated words.

```
feat/eml-import
fix/fts5-orphan-rows
docs/agents-md
refactor/extract-email-parser
```

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) with a clear,
concise description:

### Format

```
<type>: <description>

[optional body]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `test` | Adding or updating tests |
| `refactor` | Code refactoring (no functional change) |
| `perf` | Performance improvements |
| `chore` | Maintenance tasks (deps, CI, etc.) |
| `release` | Version bump for a published release |

### Examples

```
feat: add db-check command for database integrity

fix: use NOT IN instead of LEFT JOIN for FTS5 performance

docs: add detailed help messages for all commands

test: add unit tests for EmailParser

refactor: extract email parsing into separate class

perf: batch FTS deletes at end of reindex for 10x speedup
```

### Guidelines

- Use imperative mood: "add feature" not "added feature"
- Keep first line under 72 characters
- Add body for complex changes explaining why, not just what
- Reference the backlog task ID when there is one: `feat: add import command (TASK-7)`

## Pull Requests

### One PR = one squashed commit

PRs are **squash-merged**. Every PR lands on `master` as exactly one commit, so:

- **The PR title is that commit's Conventional Commits header.** It must follow
  the `<type>: <description>` format above — it's what ends up in the history,
  not your individual work-in-progress commit messages.
- **Keep each PR self-contained and focused on one change.** Don't mix a
  refactor with a feature, or a bug fix with a dependency bump. If a change
  needs two Conventional Commits types to describe it, it's two PRs.

This matters because `master`'s history *is* the changelog: release notes are
generated from the commit headers. One noisy or mistyped PR title puts a wrong
entry in the changelog permanently, and a PR that mixes concerns can't be
described by a single type at all.

The same "one self-contained change per commit" rule applies to commits pushed
straight to `master` — there's just no PR title to get right, since the commit
header *is* the header.

### Checklist

1. Branch off `master` following the naming convention above
2. Make your changes
3. Update documentation if needed
4. Add tests for new functionality
5. `pre-commit run -a --hook-stage pre-push` passes
6. Open the PR with a Conventional Commits title and a description of *why*

## Database Migrations

When changing the database schema:

### Before v1.0.0 (Pre-release)

For an unreleased schema that no existing archive uses, update the `CREATE TABLE`
statements in `_init_db()`. Schemas already in use need migrations and tests
against existing archives, even before v1.0.0.

### After v1.0.0 (Post-release)

Once published, we must support migration from previous versions:

1. **Adding a column**: Use `ALTER TABLE ... ADD COLUMN` with try/except:
   ```python
   try:
       conn.execute("ALTER TABLE emails ADD COLUMN new_column TEXT")
   except sqlite3.OperationalError:
       pass  # Column already exists
   ```

2. **Renaming a column**: SQLite doesn't support `RENAME COLUMN` in older versions. Create new, copy, drop old.

3. **Changing column type**: Requires table rebuild (create new table, copy data, drop old, rename).

4. **Always test migrations**: Test with a database from the previous release.

### Schema Version Tracking (Future)

For complex migrations, we may add a `schema_version` to `sync_state`:
```python
conn.execute("INSERT OR REPLACE INTO sync_state VALUES ('schema_version', '2')")
```

## Philosophy Reminders

When contributing, keep these principles in mind:

- **Files are the source of truth** — The `.eml` files are the archive. The database is just an index.
- **Fail gracefully** — Handle malformed emails, network errors, etc. without crashing.
- **Resumable operations** — Long-running commands should be safe to Ctrl-C and resume.
- **Minimal dependencies** — Only add dependencies when truly necessary.

## Questions?

Open an issue for discussion before starting major changes.
