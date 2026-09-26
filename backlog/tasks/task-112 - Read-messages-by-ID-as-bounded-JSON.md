---
id: TASK-112
title: Read messages by ID as bounded JSON
status: To Do
assignee: []
created_date: '2026-09-24 18:44'
labels: []
dependencies:
  - TASK-111
references:
  - ownmail/cli.py
  - ownmail/archive.py
  - ownmail/parser.py
priority: medium
type: feature
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scripts and assistants need to read a selected search result without writing ad hoc MIME parsers. Add a CLI command that accepts an ID returned by JSON search and returns decoded message content from locally available archive or Active mail. Follow the JSON and read-only behavior established by TASK-111. Attachment content extraction and MCP integration are outside this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An ID from JSON search resolves to the corresponding archived or cached Active message and returns decoded headers, readable text, attachment names, archive/Active status, and a usable original-message reference.
- [ ] #2 Returned body text has a documented default and maximum size; callers can select a limit and responses explicitly report truncation.
- [ ] #3 Missing IDs, unavailable files, and parse failures return defined errors and nonzero exit status. Stdout remains JSON and diagnostics go to stderr.
- [ ] #4 Reading performs no network calls or writes to the index, email files, Active cache, configuration, or credentials, including no implicit creation or migration.
- [ ] #5 CLI documentation and synthetic-fixture tests cover search-to-read identity, plain-text and HTML-only messages, encoded headers, attachment names, truncation, unavailable content, and absence of writes.
<!-- AC:END -->
