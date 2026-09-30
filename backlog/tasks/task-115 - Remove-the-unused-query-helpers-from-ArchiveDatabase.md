---
id: TASK-115
title: Remove the unused query helpers from ArchiveDatabase
status: Done
assignee:
  - Ownmail IC1
created_date: '2026-09-27 08:03'
updated_date: '2026-09-30 12:51'
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
- [x] #1 _parse_query and _convert_query are deleted along with their tests
- [x] #2 search() no longer carries the constant distinct placeholder
- [x] #3 The pre-push gate passes
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

Task-only claim/plan checkpoint 72c46d0bdd6694310f71d658528698c3679e396d was committed with normal hooks before any production or test edits. A saved inventory of all 118 tracked Python files confirmed one internal helper call plus ten calls in the eight obsolete tests and no other callers. The actual-search baseline used five disposable synthetic metadata rows and nine cases spanning FTS/table-only paths, label/recipient/date/account filters, ordering, offset/limit pagination and a parse error. Each case asserted exact expected message IDs; obsolete-helper guards would raise if invoked, and neither guard was called.

Deleted exactly the two obsolete private methods, the eight-test TestDatabaseQueryParsing class, and the two empty distinct assignments plus their stale comments/interpolations. Repeating the identical synthetic search matrix after deletion produced the same ordered result tuples and whitespace-normalized bound SELECT statements for all nine cases, with both obsolete-helper guards unused. No schema or supported query/API behavior was added or changed. The live re import and query.parse_query path remain intact.

All 428 retained database, query and fixture tests passed. Ruff check, format-check, deptry and whitespace checks passed without formatting changes. Source comparison against the fixed review base verified the exact deletion boundaries and that all tests outside the obsolete class are byte-identical. No helper attribute references remain in tracked Python files. Author self-review and a fresh independent Astra Ultra review found no correctness or deletion-boundary findings. No tests of supported behavior were removed or weakened, and no new tests were needed for this deletion-only cleanup.

Acceptance criteria 1 and 2 were verified at the implementation checkpoint. Criterion 3 stayed unchecked and the task stayed In Progress while the complete required mandatory-browser pre-push gate was unrun and TASK-93 owned Chromium. A private source-bound environment, task-specific runtime state and the full-gate command were prepared without launching a browser. All baseline fixtures were synthetic and disposable; no real archive/configuration/credential operations, integration, publication or next task occurred.

Reviewed implementation checkpoint 4e468558f7594ee90cce43d2277a4e27b937df9c passed normal commit hooks. After browser clearance, the complete required pre-commit run -a --hook-stage pre-push gate passed against that clean checkpoint: all hygiene, Ruff and deptry hooks passed, and all 4,003 tests passed in 185.53 seconds with no skips or xfails. Branch-inclusive coverage reached 96.57%, above the unchanged 95% floor. The full-suite count is reduced by exactly the eight obsolete helper tests; all supported-behavior tests remain intact. Mandatory Chromium coverage ran with private synthetic fixtures/profiles. All 13 observed browser probes completed successfully with no timeout. The runtime-only observer preserved subprocess behavior, test selection, assertions and timeouts. The gate process exited successfully and the browser interval was released immediately; a scoped process check found no remaining task-owned pytest/browser/profile processes.

All three acceptance criteria are met. Author and independent Astra Ultra reviews have no findings. This final closure is ledger-only and preserves production, tests and validation configuration from the tested implementation checkpoint. Local verification used Python 3.14.6; the supported-Python CI matrix remains a later integration check. No main changes, integration, publication or next task were performed.

Next action: none within TASK-115; await separately authorized integration while preserving this completed isolated branch.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Removed two unused private database query helpers, their eight dedicated obsolete tests and constant-empty distinct scaffolding. Live parsing, re usage, schema and supported behavior/tests remain unchanged. Nine synthetic actual-search cases preserved exact IDs, ordered results and normalized bound SQL before/after. All 4,003 full-suite tests and required hooks passed with 96.57% branch-inclusive coverage and mandatory Chromium coverage.
<!-- SECTION:FINAL_SUMMARY:END -->
