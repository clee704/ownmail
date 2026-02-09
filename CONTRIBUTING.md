# Contributing to ownmail

Thanks for your interest in contributing to ownmail!

> **Note:** This guide is for both human and AI contributors. For AI-specific guidelines, see [.github/copilot-instructions.md](.github/copilot-instructions.md).

## Development Setup

```bash
# Clone the repo
git clone https://github.com/chungmin/ownmail.git
cd ownmail

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"
```

## Running Locally

```bash
# Run directly
python3 ownmail.py --help

# Or after pip install -e .
ownmail --help
```

## Code Style

- Follow PEP 8
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

Current minimum coverage: **85%** (configured in `pyproject.toml`).

When adding new code, write tests to maintain or improve coverage. The build will fail if coverage drops below the barrier.

## Before Committing

**Always run tests and lint before committing:**

```bash
# Run lint check
ruff check .

# Run tests with coverage
pytest --cov=ownmail

# Or both together
ruff check . && pytest
```

Fix any lint errors before committing. Most can be auto-fixed with `ruff check . --fix`.

## Commit Messages

Use semantic commit messages with a clear, concise description:

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

## Database Migrations

When changing the database schema:

### Before v1.0.0 (Pre-release)

We can change the schema freely since there are no published versions. Just update the `CREATE TABLE` statements in `_init_db()`.

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

## Pull Request Guidelines

1. Fork the repo and create a feature branch
2. Make your changes with clear commit messages
3. Update documentation if needed
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a PR with a clear description
7. **Keep PRs self-contained** — each PR should be logically independent and focused on one change

## Philosophy Reminders

When contributing, keep these principles in mind:

- **Files are the source of truth** — The `.eml` files are the archive. The database is just an index.
- **Fail gracefully** — Handle malformed emails, network errors, etc. without crashing.
- **Resumable operations** — Long-running commands should be safe to Ctrl-C and resume.
- **Minimal dependencies** — Only add dependencies when truly necessary.

## Questions?

Open an issue for discussion before starting major changes.
