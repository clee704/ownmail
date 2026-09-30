---
id: TASK-111
title: Add bounded JSON output to CLI search
status: In Progress
assignee:
  - Ownmail audit IC4
created_date: '2026-09-24 18:44'
updated_date: '2026-09-30 16:59'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pinned review base: 95251cc64f328890362757de49d194fa8ca256fe; isolated branch feat/bounded-search-json. This checkpoint implements only the decision-independent pure JSON formatter and synthetic tests. Add ownmail/search_json.py and tests/test_search_json.py; no shared argparse, command dispatch, database, Active cache, provider or export/sync edits. Reuse existing seven-field search tuples and active_infos metadata, preserve supplied search order, bound pages to 500 rows (existing web maximum) and snippets to 200 Unicode characters, and use one lookahead row for has_more/next_offset. Serialize results/pagination or a structured error envelope with no I/O. Document null/default behavior and Active freshness, retaining stable IDs without exposing file paths. Add failure-capable tests for the whole schema, limits/offsets, truncation, lookahead, empty pages, archive/Active/matched ownership, incomplete freshness, Unicode/control escaping and errors. Run only focused tests and normal commit hooks, review and commit cleanly. Acquisition is explicitly blocked on the user choice between live SQLite coordination writes and a prepared immutable snapshot; retain AC4 unchanged and leave every end-to-end AC and the full gate open.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User decision is pending. Do not assume permission for WAL/SHM writes or silently omit committed WAL data. Parent explicitly authorized this independent pure-formatting slice while settling acquisition. Proposed JSON contract uses results plus pagination; archived is a boolean and active is null or a whitelisted copy of existing freshness fields. Defined errors use error.code and error.message. Default limit remains the CLI existing 50, with cap 500 matching web settings; offset is nonnegative. No production command will invoke this formatter until acquisition and stdout/stderr/exit handling are completed and validated.

Formatting-only implementation is complete: ownmail/search_json.py accepts existing seven-field result tuples and matching active_infos metadata, emits results/pagination or an error envelope, preserves row order/null headers, caps pages at 500 and snippets at 200 Unicode characters, and derives next_offset only from lookahead. Missing metadata for an Active-only result raises an acquisition error rather than falsely reporting archive ownership. Pure validation is reusable before any source open. Dedicated synthetic suite: 34 passed. Runtime-only mutations removing the row cap, inventing a next page for a full terminal page, and discarding incomplete Active freshness are all detected. No owner source, index, cache, config, credentials or network are accessed by the formatter. No shared argparse, existing CLI function or command dispatch hunk changed. Self-review and Ruff checks passed. This is a deliberately partial checkpoint: no CLI flag is exposed yet; stdout/stderr/exit integration, safe acquisition, end-to-end fixture tests, user documentation and full required gate remain open. All original ACs remain unchecked and AC4 unchanged pending the user operating-contract decision.
<!-- SECTION:NOTES:END -->
