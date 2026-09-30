---
id: TASK-112
title: Read messages by ID as bounded JSON
status: In Progress
assignee:
  - Ownmail audit IC4
created_date: '2026-09-24 18:44'
updated_date: '2026-09-30 18:18'
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
- [ ] #4 Reading performs no network calls or substantive writes to the index, email files, Active cache, configuration, or credentials, including no initialization, migration, rebuild or implicit creation of application data. It follows the TASK-111 contract: live read-only SQLite handles may perform only normal WAL/SHM coordination-file writes, as explicitly approved by the user.
- [ ] #5 CLI documentation and synthetic-fixture tests cover search-to-read identity, plain-text and HTML-only messages, encoded headers, attachment names, truncation, unavailable content, and absence of writes.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pinned review base: clean main 1c7f246fabadd384fed8fc5f4a901bbbb37a26ba; dependency TASK111 is Done. 1. Add ownmail read ID as a JSON-only command, validating --body-limit before opening data (default 20000, maximum 100000 Unicode characters). Reuse TASK111 configuration validation, existing-data acquisition, pinned read-only connections, error envelope and Active status formatting; route ID lookup through the existing connection hook. 2. Resolve an exact search ID to its owned file or verified cached Active payload, preserving dual ownership and incomplete freshness. Use existing archive/cache file boundaries; report missing IDs, unavailable files/state and parse failures distinctly. Include an explicit original local file URI for the selected message; no remote access. 3. Reuse the MIME parser/header/charset/HTML-text/filename helpers with a reader mode that excludes attachment contents, preserves attachment names as a list, and reports actual parse failures without changing indexing defaults. Output body text plus its limit and truncation status; no attachment extraction or MCP. 4. Add synthetic search-to-read, plain/HTML/encoded/attachment/truncation/error and current-WAL/nonmutation checks, plus meaningful failure/mutation controls and retained search/parser tests. Document the command adjacent to JSON search, leaving the concurrent export section untouched. 5. Commit clean checkpoints with normal hooks, obtain independent focused review, then run the mandatory full gate with an exclusive browser lease and reconcile latest main before authorized integration. No real mail, credentials, network service or external push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise verified: JSON search returns stable IDs, but the CLI has no command to decode a selected result. Existing get_readable_email handles archive/Active resolution; existing parser supplies decoding helpers, and TASK111 provides validated acquisition and formatting. No new runtime dependency or database schema is needed. The task explicitly follows TASK111, so AC4 now states its already-approved coordination-file exception without expanding substantive writes. Output may include a local file URI only for the explicitly selected message, fulfilling the required original-message reference. Shared CLI edits are confined to JSON configuration reuse, the new read command/parser and early dispatch; the existing search response and human default stay compatible. Concurrent PDF/export implementation and its README section remain out of scope. All criteria stay open until evidence and completion gates.
<!-- SECTION:NOTES:END -->
