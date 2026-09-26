---
id: TASK-111
title: Add bounded JSON output to CLI search
status: To Do
assignee: []
created_date: '2026-09-24 18:44'
labels: []
dependencies: []
references:
  - ownmail/cli.py
  - ownmail/archive.py
  - ownmail/database.py
  - ownmail/active_search.py
priority: medium
type: feature
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scripts and assistants need compact search results without parsing terminal output or querying SQLite directly. Add a supported JSON mode to CLI search using the existing query semantics and consolidated archive/Active view. Preserve the human-readable default. MCP integration is separate future work.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 JSON results include stable message IDs, sender, subject, date, bounded snippets, attachment indicators, archive/Active status, and pagination information.
- [ ] #2 Result limits and offsets are validated, with a documented result cap and predictable pagination.
- [ ] #3 Stdout contains only JSON in JSON mode; invalid queries and missing prerequisites produce defined errors and nonzero exit status, while empty results succeed. Diagnostics go to stderr.
- [ ] #4 Search performs no network calls or writes to the index, email files, Active cache, configuration, or credentials, including no implicit creation or migration.
- [ ] #5 CLI documentation and synthetic-fixture tests cover pagination, invalid input, empty results, archive/Active results, clean JSON output, and absence of writes.
<!-- AC:END -->
