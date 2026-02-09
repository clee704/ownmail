# Copilot Instructions for ownmail

## Project Overview

ownmail is a file-based email backup and search tool. Read [README.md](../README.md) for project philosophy and features.

## Before Contributing

Read [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- Database migration guidelines

## Key Principles

1. **Files are the source of truth** — `.eml` files are the archive, database is just an index
2. **Fail gracefully** — Handle malformed emails, network errors without crashing
3. **Resumable operations** — Long-running commands should be safe to Ctrl-C and resume
4. **Minimal dependencies** — Only add dependencies when truly necessary

## Before Committing

Always run:
```bash
ruff check .          # Lint check
pytest                # Run tests
```

## Code Style

- Python 3.8+ compatible
- Follow PEP 8 (enforced by ruff)
- Use type hints where practical
- Add docstrings for public methods

## Commit Messages

Use semantic commit messages:

```
feat: add new feature
fix: bug fix
docs: documentation changes
test: adding or updating tests
refactor: code refactoring
perf: performance improvements
chore: maintenance tasks
```

Examples:
- `feat: add db-check command for database integrity`
- `fix: use NOT IN instead of LEFT JOIN for FTS5 performance`
- `docs: add detailed help messages for all commands`
- `test: add unit tests for EmailParser`
