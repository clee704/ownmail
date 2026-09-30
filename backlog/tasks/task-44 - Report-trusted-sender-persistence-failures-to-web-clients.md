---
id: TASK-44
title: Report trusted-sender persistence failures to web clients
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-12 21:27'
updated_date: '2026-09-30 10:37'
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
- [ ] #1 A configuration read or write failure returns an actionable error response without claiming that the preference was saved.
- [ ] #2 In-memory trusted-sender state remains consistent with the documented persistence outcome.
- [ ] #3 Regression tests cover successful changes, failed persistence and retry for both routes.
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
Next action: commit this task-only claim/plan with normal hooks, then prepare private source-bound tooling and failing synthetic regressions before implementation.
<!-- SECTION:NOTES:END -->
