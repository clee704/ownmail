---
id: TASK-44
title: Report trusted-sender persistence failures to web clients
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-12 21:27'
updated_date: '2026-09-30 10:45'
labels:
  - web
dependencies: []
priority: medium
type: bug
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The trust-sender and untrust-sender routes in ownmail/web.py catch configuration read/write failures and still return a successful HTTP response. The reader therefore cannot distinguish a saved preference from a persistence failure. Confirmed by source inspection during TASK-32; this behavior predates the UI revamp. Keep this backend correction separate from the presentation and interaction changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A configuration read or write failure returns an actionable error response without claiming that the preference was saved.
- [x] #2 In-memory trusted-sender state remains consistent with the documented persistence outcome.
- [x] #3 Regression tests cover successful changes, failed persistence and retry for both routes.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Claim TASK-44 on isolated branch fix/report-trusted-sender-save-failures from clean tested base 384a8b941178e7322196d8a3bd53a6ae069c59a4. Commit this task-only plan with normal hooks before changing code or tests; retain the same review base through closure.
2. Limit production edits to web.py trust_sender and untrust_sender. Return HTTP 500 with sanitized, actionable JSON when configuration read/write fails, including form requests instead of a success redirect. Preserve successful responses and memory-only behavior when no config path exists.
3. Preserve immediate untrust revocation in this server process even if persistence fails, and explain that the preference was not saved and must be retried. Never defer revocation or restore trust on the failed path. Trust updates process state only after successful config read/save; also reconcile membership when the requested sender is already persisted so retry/no-op calls are correct.
4. Extend the existing trusted-sender tests in tests/test_web.py for successful persistence, read/write errors, unchanged config bytes, immediate revocation, sanitized error responses, retry, idempotence and re-trust after failed untrust. Change only sender-route failure expectations in the existing partial-write regression in tests/test_web_downloads.py. Keep serialization and atomic-write implementations, settings behavior, templates and JavaScript unchanged.
5. Demonstrate failing-before/passing-after synthetic tests, run retained config concurrency/partial-write and web tests, explicit Ruff check/format-check and deptry, author review, and the complete required pre-push gate with mandatory private headless browser coverage after coordinating the browser-only interval. Record verified criteria, evidence and clean local checkpoints with normal hooks. No main, merge/rebase, publication or real mail/config/credential operations.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read-only preflight independently verified the source-backed premise on 384a8b941178e7322196d8a3bd53a6ae069c59a4. Mocked Flask requests with synthetic YAML reproduce HTTP 200 status:ok (or trust-form 302) after read and write failures. Failed trust leaves the sender untrusted; failed untrust removes process trust while persisted trust remains, and retry succeeds. An already-persisted trust request can incorrectly leave process membership absent because its update is nested inside the disk-change condition. Existing reader actions already reject non-2xx responses and support retry, so no UI expansion is needed. The manager explicitly authorized preserving immediate session-only revocation on failed untrust and prohibited deferring it or weakening remote-content protection. The existing config lock and atomic replacement remain unchanged. Exact owned paths: web.py two sender routes; existing trusted-sender family in tests/test_web.py; sender-only assertions in tests/test_web_downloads.py partial-write regression; this task ledger. TASK-78 CLI work and approval-blocked TASK-37/95/125 remain outside scope.

Task-only claim/plan checkpoint 911502be29eecf530794abab9663f31b4491a982 preceded all product/test edits. Both sender routes now return HTTP 500 with fixed actionable error messages for read/save failures, preserving immediate process-only revocation on failed untrust. Successful trust also reconciles process membership when the sender is already persisted. The unchanged config serializer, atomic writer, settings endpoint, templates and JavaScript remain outside the diff. Fifteen regression cases failed against the original implementation. The implemented focused suite passed 22 tests, and the final retained web/config suite passed 379 tests with one existing expected failure, including concurrent updates and failed partial writes. Ruff check, format-check, deptry and diff whitespace checks passed. Author review and independent Astra Ultra review found no remaining issues. Review identified a swallowed test assertion; it was replaced with an observation asserted outside the route handler, and all six cases now reject an in-memory-only mutation that delays revocation until after failing I/O. No repository production mutation was used for that probe. All test data/config files were synthetic.

Reviewed implementation checkpoint e411c7fe0add4b2a0f54de339848e70cd63d60be is committed with passing normal commit/message hooks. The complete mandatory-browser pre-push gate has not run yet: its browser-only interval is awaiting coordination with concurrent TASK-78. The task remains In Progress until that required aggregate passes; focused/retained results are not a substitute.
Next action: once the browser-only interval is confirmed, run the prepared complete pre-push command with the original test selection, coverage floor and timeouts, then record its actual result and close with normal hooks only if it passes.
<!-- SECTION:NOTES:END -->
