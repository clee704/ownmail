---
id: TASK-3
title: Raise test coverage minimum from 80% to 95%
status: In Progress
assignee: []
created_date: '2026-07-24 04:46'
updated_date: '2026-07-24 20:44'
labels: []
milestone: m-4
dependencies:
  - TASK-2.6
priority: medium
ordinal: 14
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
pyproject.toml's [tool.coverage.report] fail_under is currently 80. Actual coverage as of 2026-07-24 is 81.82% overall, so this isn't just a config bump — closing the gap to 95% needs real new tests, concentrated in the lowest-coverage modules: ownmail/web.py (76%), ownmail/commands.py (76%), ownmail/cli.py (80%), ownmail/parser.py (81%), ownmail/providers/gmail.py (81%), ownmail/sanitizer/__init__.py (82%). Raise fail_under only after coverage genuinely clears 95%, not before (a premature bump just breaks the local check everyone already runs). Note: two pre-existing test failures unrelated to coverage were found during this survey (tests/test_additional_coverage.py and tests/test_gmail_provider.py, both TestGmailProviderAuthentication::test_authenticate_no_credentials_raises*) — worth a look, may or may not block this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Overall coverage >= 95% via pytest --cov=ownmail
- [ ] #2 pyproject.toml fail_under updated to 95
- [ ] #3 No module left far below the 95% line without a documented reason (e.g. unreachable defensive branches)
<!-- AC:END -->
