---
id: TASK-115
title: Remove the unused query helpers from ArchiveDatabase
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-27 08:03'
updated_date: '2026-09-30 12:28'
labels:
  - search
dependencies: []
priority: low
ordinal: 26500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ArchiveDatabase._parse_query and _convert_query (ownmail/database.py) predate ownmail/query.py. search() parses with query.parse_query, and nothing outside tests/test_fixtures.py calls either helper, so their tests cover code no user path runs.

search() also sets distinct = "" in both paths under a comment that describes a decision the code no longer makes.

Found while fixing TASK-22.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 _parse_query and _convert_query are deleted along with their tests
- [ ] #2 search() no longer carries the constant distinct placeholder
- [ ] #3 The pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Claim TASK-115 on isolated branch refactor/remove-unused-query-helpers from clean review base 75cd2955e68b7315c66baeddd9b7975c3963fc98. Commit this task-only claim/plan with normal hooks before code or test edits, retaining that review base throughout the task.
2. Preserve the reference inventory proving no runtime callers of the two obsolete private methods. Before deletion, capture actual ArchiveDatabase.search results and SQL on disposable synthetic rows across FTS/table-only filtering, ordering and pagination; guard the obsolete helpers so accidental runtime use fails visibly.
3. Delete only ArchiveDatabase._parse_query and _convert_query, their eight dedicated TestDatabaseQueryParsing tests, and the two constant-empty distinct variables plus stale comments/interpolations. Preserve the live re import, current query parser, search API, schema, all live search logic and all tests for supported behavior.
4. Compare the same synthetic results, bound SQL and ordering after deletion against the saved baseline. Verify all other source/test code is unchanged, run retained database/query/fixture checks, Ruff check/format-check, deptry and whitespace checks, and complete author self-review. Use Astra Ultra review support if useful; resolve concrete findings without widening scope.
5. Commit a clean reviewed implementation checkpoint with normal hooks and report readiness while TASK-93 owns Chromium. After browser clearance, run the complete required mandatory-browser pre-push gate with private runtime state and unchanged coverage threshold, assertions and timeouts. Close only after all acceptance criteria and required checks pass. No main changes, integration, merge/rebase, publication or next task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise and worth verified read-only on clean completed TASK-12 revision 75cd2955e68b7315c66baeddd9b7975c3963fc98 before claim. TASK-115 is the next doc-4 item after TASK-12 (position 26a), was To Do/unassigned and has no dependencies. Across all 118 tracked Python files, the two private helpers have only one internal call and ten direct calls in eight dedicated obsolete tests. Live search invokes ownmail.query.parse_query instead. The two distinct assignments are always empty strings and are used only in the corresponding SELECT interpolations. Removing these unused paths reduces duplicate parsing logic and removes tests for behavior no supported user path exercises.

Owned scope is the two obsolete methods and constant-empty distinct scaffolding in ownmail/database.py, the eight-test TestDatabaseQueryParsing class in tests/test_fixtures.py, and this task ledger. Keep import re: live address parsing still uses it. Keep all real parser/search/filter/sort/pagination tests. ArchiveDatabase is re-exported publicly, but these underscore-prefixed helpers have no documented public contract or repository production callers. Independent Astra Ultra preflight found no dependency, API-policy or STOP blocker. No schema, migration, credential, archive-file or runtime dependency change is needed. TASK-93 sanitizer scope and all held owner-policy/integration actions stay untouched.

Next action: commit this task-only claim/plan before implementation, then capture the synthetic before/after search baseline.
<!-- SECTION:NOTES:END -->
