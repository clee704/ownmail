---
id: TASK-3
title: Raise test coverage minimum from 80% to 95%
status: Done
assignee: []
created_date: '2026-07-24 04:46'
updated_date: '2026-07-24 21:36'
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
- [x] #1 Overall coverage >= 95% via pytest --cov=ownmail
- [x] #2 pyproject.toml fail_under updated to 95
- [x] #3 No module left far below the 95% line without a documented reason (e.g. unreachable defensive branches)
<!-- AC:END -->





## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Overall coverage 81.89% -> 95.23%; pyproject fail_under 80 -> 95. Verified with 'pre-commit run -a --hook-stage pre-push' (the set CI runs): 1886 passed, 1 xfailed.

Per-module before -> after:
  web.py       76% -> 93%    commands.py  76% -> 95%
  cli.py       79% -> 95%    parser.py    81% -> 93%
  gmail.py     81% -> 99%    sanitizer    82% -> 98%
  query.py     85% -> 96%    __init__.py  86% -> 100%
  sidecar.py   86% -> 98%    archive.py   88% -> 96%
  database.py  90% -> 98%    imap.py      90% -> 95%
  keychain.py  95% -> 100%   config.py    97% -> 98%

AC3: no module is far below the line -- the lowest, web.py and parser.py, are at 93%. What is still uncovered is concentrated in (a) defensive 'except: pass' arms around stdlib calls that do not fail on well-formed input, and (b) the tail of charset fallback chains: those chains end in single-byte codecs (cp1251, iso-8859-1) that decode any byte sequence without error, so the rungs after them -- including several 'return utf-8' backstops -- are unreachable. Left as-is rather than contorted into reachability.

The two pre-existing test failures the task description mentioned did not reproduce, in isolation or in-suite. Treated as stale.

Two real defects found while writing tests, filed rather than absorbed:
  TASK-12  'ownmail --verbose <cmd>' silently runs with verbose=False.
           _add_global_opts adds a second --verbose to each subparser
           sharing dest='verbose', so the subparser's False default
           overwrites the global True.
  TASK-13  A URL containing an email address is linkified twice, nesting
           an anchor inside the outer anchor's href. Covered by
           tests/test_web.py::TestLinkify::test_email_inside_url_is_not_double_linked,
           marked xfail(strict=True) -- it will fail once TASK-13 lands,
           which is the signal to drop the marker.

Also replaced three cmd_list_unknown tests that asserted nothing: they
staged files in emails/unknown/, which the command never reads (it
queries the DB for email_date IS NULL), and only checked that 'unknown'
or a digit appeared in output -- always true given the banner.
<!-- SECTION:NOTES:END -->
