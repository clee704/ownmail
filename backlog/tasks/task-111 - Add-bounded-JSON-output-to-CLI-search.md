---
id: TASK-111
title: Add bounded JSON output to CLI search
status: In Progress
assignee:
  - Ownmail audit IC4
created_date: '2026-09-24 18:44'
updated_date: '2026-09-30 17:58'
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
- [x] #1 JSON results include stable message IDs, sender, subject, date, bounded snippets, attachment indicators, archive/Active status, and pagination information.
- [x] #2 Result limits and offsets are validated, with a documented result cap and predictable pagination.
- [x] #3 Stdout contains only JSON in JSON mode; invalid queries and missing prerequisites produce defined errors and nonzero exit status, while empty results succeed. Diagnostics go to stderr.
- [x] #4 Search performs no network calls or substantive writes to archive/index/message/cache/configuration/credential content, and performs no initialization, migration, Active-index rebuild or implicit creation of application data. Live SQLite read-only handles may perform normal WAL/SHM coordination-file writes, as explicitly approved by the user.
- [ ] #5 CLI documentation and synthetic-fixture tests cover current WAL and Active results, pagination, invalid input, empty results, clean JSON output, and unchanged substantive source data while permitting only normal SQLite coordination writes.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pinned task review base remains 95251cc64f328890362757de49d194fa8ca256fe; preserve pure formatter e42f45a6565214ae5a77a474c16cebdff6d20c79 and reconcile completed clean main in this isolated branch. User approved normal live SQLite coordination writes only. 1. Commit this corrected acquisition contract before production edits. 2. Add a narrow existing-data search view with mode=ro SQLite handles and read transactions; reuse the existing database query and archive/Active merge/freshness behavior. Do not call archive initialization, migrations, cache rebuilding, providers or credentials. Missing/incompatible/unusable existing state yields unavailable, with no repair or creation. 3. Add --json and JSON pagination to search only; validate before acquisition, keep stdout to one JSON document, route diagnostics to stderr and define nonzero errors. Leave human default and export CLI/error hunks intact. 4. Exercise current WAL commits, archive/Active/dual ownership, freshness, index prerequisites, query errors, pagination, output bounds and substantive nonmutation on synthetic fixtures, including meaningful red/green and safety mutations. 5. Reconcile latest clean main, obtain independent focused review, run normal hooks and mandatory full gate only with a browser lease, then hand off clean reviewed commits for local integration. No real-mail access or external changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User decision is pending. Do not assume permission for WAL/SHM writes or silently omit committed WAL data. Parent explicitly authorized this independent pure-formatting slice while settling acquisition. Proposed JSON contract uses results plus pagination; archived is a boolean and active is null or a whitelisted copy of existing freshness fields. Defined errors use error.code and error.message. Default limit remains the CLI existing 50, with cap 500 matching web settings; offset is nonnegative. No production command will invoke this formatter until acquisition and stdout/stderr/exit handling are completed and validated.

Formatting-only implementation is complete: ownmail/search_json.py accepts existing seven-field result tuples and matching active_infos metadata, emits results/pagination or an error envelope, preserves row order/null headers, caps pages at 500 and snippets at 200 Unicode characters, and derives next_offset only from lookahead. Missing metadata for an Active-only result raises an acquisition error rather than falsely reporting archive ownership. Pure validation is reusable before any source open. Dedicated synthetic suite: 34 passed. Runtime-only mutations removing the row cap, inventing a next page for a full terminal page, and discarding incomplete Active freshness are all detected. No owner source, index, cache, config, credentials or network are accessed by the formatter. No shared argparse, existing CLI function or command dispatch hunk changed. Self-review and Ruff checks passed. This is a deliberately partial checkpoint: no CLI flag is exposed yet; stdout/stderr/exit integration, safe acquisition, end-to-end fixture tests, user documentation and full required gate remain open. All original ACs remain unchecked and AC4 unchanged pending the user operating-contract decision.

Acquisition decision resolved by explicit user approval relayed by the coordinator: normal SQLite WAL/SHM coordination writes are permitted; substantive archive/index/message/cache/config/credential changes are not. This approval does not permit schema initialization, Active-index rebuilds, migration, download or creation of application data. AC4/AC5 are amended to that exact boundary; the previous pending-decision notes remain historical. All ACs remain open until end-to-end validation. Shared CLI changes are reserved to search options and the JSON-search dispatch before EmailArchive construction; export command and its opt-in search error handling remain owned by TASK9.

Live JSON search implementation is ready for independent review. Reconciled completed TASK37/TASK9 main b09e99c08c6af5e7c6d853a28340bda188022e29 while preserving the formatter checkpoint and all prior refs. JSON dispatch runs before writable archive construction. Existing-data archive/cache/database views reuse the current query, ownership merge and freshness logic through pinned mode=ro read transactions; temporary query tables stay in memory. Missing/old indexes and missing, stale or concurrently changed Active state produce unavailable without repair. Archive and Active committed WAL fixtures pass, the read snapshot survives a later writer commit, source UPDATE is rejected, and all query/role/ownership paths acquire only the two read-only handles. The same synthetic fixtures verify unchanged substantive files and WAL payloads; only normal WAL/SHM coordination is allowed. CLI output has bounded snippets and 1-500 results, a documented 0-2147483647 offset range, lookahead pagination, explicit incomplete Active freshness, JSON errors/nonzero statuses, stderr diagnostics and no initializer, cache rebuild, keychain or network calls. Separate-index paths containing URI-special characters work through the actual module CLI. Standard argparse syntax/help errors retain their normal behavior. Six intended CLI regressions failed before implementation; 69 focused tests and 353 retained CLI/database/ownership/export tests pass. Five in-memory mutations are caught: immutable WAL omission, writable handles, accepted stale index, ignored concurrent cache changes and stdout diagnostic pollution. The coordinator memory-measurement pause is released; every prior test process exited normally. Full diff self-review, Ruff and formatting checks pass. Criteria 1-4 are evidenced; keep criterion 5 and status open until independent focused review and the unchanged mandatory full gate with an exclusive browser lease. No real-mail or remote operation occurred.
<!-- SECTION:NOTES:END -->
