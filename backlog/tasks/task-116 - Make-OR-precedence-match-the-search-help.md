---
id: TASK-116
title: Make OR precedence match the search help
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-27 08:16'
updated_date: '2026-09-30 05:43'
labels:
  - search
  - bug
dependencies: []
priority: medium
ordinal: 10500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
FTS5 binds implicit AND tighter than OR, so `attachment:pdf report OR invoice` means (PDF attachment AND report) OR invoice. The help page's Examples table says it finds PDFs with report or invoice, but the actual search can also return invoice mail without a PDF attachment.

Use the documentation-only solution and preserve current search semantics. Preflight through ArchiveDatabase.search verified `attachment:pdf report OR attachment:pdf invoice` as the working PDF example. The earlier proposed `attachment:pdf (report OR invoice)` conjunction fails through the actual search path and must not be advertised. Correct the Boolean and Example rows together: show text negation with positive search context, use a verified standalone grouping example, and describe the fixed 2024 date literally rather than as "this year".

Text terms and attachment-name terms use the existing FTS behavior. Since TASK-21, SQL-applied filters apply to the whole search and cannot be OR alternatives. Keep production query/database behavior unchanged; confirm every edited example through real ArchiveDatabase.search over synthetic fixtures.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The help page describes OR precedence as search applies it, and every Boolean and Example row returns what its description says
- [ ] #2 A test runs the documented OR example through search() and asserts its result
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Independently reconfirm the documentation defect and selected examples through ArchiveDatabase.search with synthetic fixtures; inspect existing search/help regressions and retain the current parser semantics.
2. Correct ownmail/templates/help.html: repeat attachment:pdf on both OR branches, explain actual precedence, use positive-context text negation and verified standalone grouping, and give the fixed 2024 date its literal meaning.
3. Add actual-search regressions in tests/test_database.py and update only help-route assertions in tests/test_web.py. Ensure the documented queries return exactly the described synthetic messages and that the regression fails for the original misleading example.
4. Run focused checks, then the repository's complete coverage/browser/pre-push gate in the assigned validation slot; self-review the complete task diff, record results, and close this task with normal hooks.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC1. Reserved for TASK-116. Review base: da018d5d1dd309ee5767ac8483fc746d7ff3155f. Planned branch: fix/search-help-boolean-examples.
Intended write scope: ownmail/templates/help.html; tests/test_database.py for actual ArchiveDatabase.search regressions; help-route-only assertions in tests/test_web.py; this task file. Production query/database/search code is read-only. IC2 owns TASK-16's archive IMAP LIST parser and tests/test_imap_provider.py. README and the integration checkout are reserved for integration coordination.
Start from the common committed claim base after both task claims. Use an isolated local worktree in the IC's own writable workspace. Integrate TASK-116 before TASK-16; serialize full suites, browser validation and commit hooks through the coordinator. Preserve every other task and implementation scope.
The selected solution is truthful documentation plus regression coverage. The failing parenthesized PDF conjunction is explicitly excluded; do not change parser precedence to make it work. Scope excludes schema, credentials/OAuth, runtime dependencies, real mail operations and publishing.
Next action: IC1 rechecks the task premise and verified example results on the common claim base, then confirms or updates this bounded plan before implementation.
<!-- SECTION:NOTES:END -->
