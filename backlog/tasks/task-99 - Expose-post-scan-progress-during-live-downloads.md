---
id: TASK-99
title: Expose post-scan progress during live downloads
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-21 04:08'
updated_date: '2026-09-30 11:05'
labels: []
dependencies: []
references:
  - ownmail/live_sync.py
  - ownmail/static/downloads.js
priority: medium
type: bug
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A web-triggered download can look stalled after live enumeration even while the worker continues checking and refreshing messages. The refreshing UI omits skipped counts, and live_sync does not advance progress for discarded messages or final cached-message reconciliation. TASK-100 restored batched reads that flush progress after each batch, so the remaining quiet stretches come from reconciliation and silent skips. LiveLookupError also collapses underlying provider failures into a generic active_refresh reason, which prevents operators from distinguishing slow work from request failures. Make post-scan work and safe failure categories observable while preserving lifecycle safety.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Terminal and web progress remain useful throughout owned-message skips, discarded-message checks, active refresh, capture, and final reconciliation, without unbounded output or private message details.
- [x] #2 The web view includes ongoing skipped or processed work rather than showing only archive, Active, and failure totals during refreshing.
- [x] #3 Recognized provider timeout and connection failures retain safe diagnostic categories through live lookup wrapping; unknown failures remain generic and retryable.
- [ ] #4 Synthetic regressions reproduce unchanged visible counters while work advances, cover silent reconciliation paths and safe error classification, and pass the full pre-push gate.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve review base e70af546998af979a7f623d8250e90a994296ba3 on isolated branch fix/live-download-progress. Commit this task-only claim and plan before changing production or tests; preserve completed work separately.
2. Add failing synthetic regressions through the actual sync/reporting functions and downloads UI for owned skips, discarded/excluded observations, active refresh/capture, final cached-message reconciliation, rate-limited terminal output and safe transport-error categories. Retain lifecycle assertions, batching and progress I/O failure behavior.
3. Limit production changes to reporting in live_sync.py, skipped totals in static/downloads.js, and narrowly necessary exception-cause preservation in providers/live_gmail.py and providers/live_imap.py. Reuse existing progress fields/phases and fixed diagnostic messages. Provider failures remain LiveLookupError where already required; preserve retries, partial successes, member-only 404 absence, malformed-result conservatism and KeyboardInterrupt. Do not change eligibility, ownership verification, capture, cache removal, cursor commits or credential/OAuth behavior.
4. Run focused synthetic regression suites and explicit Ruff check/format-check and deptry in private runtime state. Self-review the complete diff against the original base. Coordinate the browser-only interval after TASK-44 actually exits, then run the full required pre-push gate with mandatory headless browser coverage, unchanged selection/assertions/timeouts and the coverage floor.
5. Update acceptance criteria only from verified evidence, commit meaningful checkpoints with normal hooks, and close clean only after all required gates pass. No real mailbox/network/credential operations, dependencies, denied TASK-37/95/125 changes, main mutation, merge/rebase or publication.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed against a real archive running after TASK-97: successive worker reports and the web status endpoint showed advancing counters and transitions between sources. Native sampling showed SSL reads during a quiet interval; it does not identify the exact IMAP command or prove a permanent network stall. No running process was interrupted. Code inspection locates the hidden skipped count in ownmail/static/downloads.js and unreported work and generic LiveLookupError handling in ownmail/live_sync.py. The underlying causes of the observed earlier message failures remain unverified.

Owner: Ownmail IC2. Branch: fix/live-download-progress. Review base: e70af546998af979a7f623d8250e90a994296ba3. TASK-99 is the next recorded item after TASK-44, unassigned with no dependencies before this claim. The authorized read-only premise check executed actual downloads.js with a synthetic DOM: increasing skipped from one to fifty leaves visible refreshing totals identical. Actual sync_live with in-memory cache/provider fixtures checks three discarded messages, including final reconciliation, while all progress counters remain zero. Actual provider wrappers retain timeout/connection causes but sync reporting collapses them; actual Gmail batch catalog and IMAP folder-listing catches discard causes entirely. The work is independently useful and needs no TASK-37/95/125 policy or consolidation. Production scope is restricted to live_sync reporting, downloads.js totals and two live-provider modules' diagnostic provenance; existing related synthetic test families and this task record are also owned. TASK-44 trust handlers/tests are excluded. No owner-level policy decision is needed while lifecycle, retry, storage and credential behavior remain unchanged. A policy or scope complication will be escalated before dependent edits. The current shared browser interval belongs to TASK-44; focused/static checks may proceed without it. Next action: commit this claim/plan before code.

The task-only claim/plan was committed as 7a642365d9b92888a4fdbeaf383292bc9f583991 before implementation. Reporting now counts owned, discarded, excluded and date-filtered work, prints bounded post-scan totals without message identifiers, and flushes completed reconciliation batches before the next read. The web totals retain skipped counts during scanning, refreshing and completion. Live provider failures retain explicit exception causes while user-facing diagnostics remain fixed catalog messages; known timeout/connection categories survive wrapping, unknown failures stay generic. Capture eligibility, owned files, cache/cursor decisions, retries, successful batch members, individual 404 semantics and interruption remain unchanged.

Regression evidence: 29 reporting cases failed on the original code; review identified an additional date-filtered reporting fallthrough and both terminal/web cases failed before its reporting-only fix. Provider provenance regressions failed 22 cases on original code. Provider self-review added a batch-level 404 regression that exposed an unsafe absence interpretation in the initial implementation; wrapping the batch error preserves retryability while only member-level 404 confirms absence. Final provider families pass 269 tests. Reporting, lifecycle, progress integration and shutdown families pass 154 tests. Both changed browser cases fail when the real synthetic UI receives original committed JavaScript, and all seven focused download UI browser tests pass with the fix. Repository Ruff check, explicit format-check and deptry pass. Author self-review and independent Astra Ultra review against the original base have no remaining findings; the date-filter reporting gap is resolved. All data and provider operations were synthetic. The focused browser interval was released after actual exit. ACs 1-3 are verified; the complete mandatory-browser pre-push coverage gate and final closure remain pending.

The first complete pre-push attempt on implementation 47a5cc715cc92914ef025ecd3fdf9c08fab08bbb stopped after 101 passed tests on an existing Active-download UI exact-string expectation that omitted the newly required skipped count. Chromium startup and cleanup succeeded; this was a stale expectation, not a browser environment failure. The five exact totals assertions in tests/test_active_downloads.py are updated to include zero skipped while preserving every scan, completion, privacy and state assertion. No production change is needed. The failed aggregate evidence is retained, and the browser interval was released after exit. Next action: checkpoint this related-test correction with normal hooks and rerun the complete required gate; AC4 and Done remain pending.
<!-- SECTION:NOTES:END -->
