---
id: TASK-16
title: IMAP folders with a NIL hierarchy delimiter are silently dropped
status: To Do
assignee: []
created_date: '2026-07-25 05:24'
labels: []
dependencies: []
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The LIST response parser (ownmail/providers/imap.py, parse_list_response) matches the delimiter as a quoted string: '\((?P<flags>.*?)\) "(?P<delim>.*?)" (?P<name>.*)'. RFC 3501 allows a server to report NIL instead of a quoted delimiter when the mailbox has a flat namespace with no hierarchy. Such lines fail the regex and are skipped entirely, so those folders are never scanned and their mail is never downloaded — a silent, total sync failure for that folder rather than a visible error.

Pre-existing; predates the role work in TASK-5.2, which only moved the regex into its own function. Current behaviour is pinned by tests/test_imap_provider.py::TestParseListResponse::test_skips_unparseable_lines.

Fix: accept NIL as well as a quoted delimiter, and treat it as an empty delimiter — roles.role_for_imap_folder already handles delimiter='' by matching the whole name. Consider also warning when a LIST line fails to parse, so a future shape mismatch is visible instead of silent.
<!-- SECTION:DESCRIPTION:END -->
