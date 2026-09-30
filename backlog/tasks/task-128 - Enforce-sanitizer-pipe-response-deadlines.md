---
id: TASK-128
title: Enforce sanitizer pipe response deadlines
status: Done
assignee:
  - Ownmail backend audit
created_date: '2026-09-30 16:04'
updated_date: '2026-09-30 16:43'
labels: []
dependencies: []
references:
  - ownmail/sanitizer/__init__.py
priority: medium
type: bug
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The sanitizer checks elapsed time before blocking stdout.readline, so a worker that accepts a request but never completes its reply can hold rendering past the configured deadline. A bounded synthetic OS-pipe reproduction fails on both the common baseline and the reviewed integration candidate. Bound the response read using only portable standard-library primitives, retain escaped fallback and no-install restart, and ensure replacement readiness cannot turn a timeout into another unbounded wait. Remove the write-only stderr thread field left by TASK-121 while preserving its worker-local diagnostic thread.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A positive response deadline handles both silent and incomplete-line workers, returns fully escaped input, and lets a replacement worker handle the next request.
- [x] #2 Replacement readiness is bounded, reader results are scoped to their original process/read, and EOF, invalid JSON, mismatched IDs, I/O failures and bounded stderr diagnostics retain their existing behavior.
- [x] #3 Real synthetic subprocess/pipe regressions fail against the old behavior; independent focused review and the complete mandatory-browser pre-push gate pass without new dependencies or relaxed checks.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Review base: 47e54fd653f65a33b394f52207602476dc14126b. Own only the Python sanitizer adapter and relevant sanitizer tests; preserve reader-side work and existing refs. 2. Commit this task plan before edits. Add bounded actual-pipe regressions for silent and partial replies, replacement usability and silent startup. Confirm red baseline. 3. Add a small worker-bound one-shot Queue/thread read helper with a deadline, reuse it for ready and reply reads, retain the total per-response budget, escaped fallback and no-npm restart. Remove the unused instance stderr-thread assignment; retain local binding and diagnostic limits. Do not redesign worker.js, dependency installation, protocol, schema or security policy. 4. Run focused adapter/actual-pipe tests and static checks, review the entire task against the fixed base, and obtain independent focused review via the coordinator. Commit with normal hooks. 5. Combine with separately reviewed reader corrections, run one unchanged complete required gate with the coordinated private Chromium interval, then close only on evidence and integrate locally as authorized. No remote or real-mail operations.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Selected directly from verified audit evidence under the user-authorized correction scope. The timeout is a baseline defect, not attributed to TASK-121 or TASK-123. A selector-only solution is unsuitable for Windows pipes; a small one-shot reader avoids a persistent stdout service and new lifecycle queues. The request write remains outside the response-read timeout contract; request/protocol redesign is excluded.

Implemented a portable one-shot worker-bound Queue/thread readline for ready and reply waits, retaining one total reply budget across invalid JSON and mismatched IDs. A timeout restarts without npm and returns escaped input. Removed only the write-only stderr-thread field; local bounded diagnostic draining remains. All three real subprocess/pipe regressions failed before the correction (silent reply, partial reply, silent readiness); the replacement handled the next request after both response failures. Focused sanitizer/provider run: 279 passed. Follow-up error-path tests cover both broken writes and errors propagated from the reader. Existing lifecycle, EOF, JSON, IDs and diagnostics tests retain their assertions; stderr-scheduling mocks stub only synchronous scripted stdout reads. The helper creates a short-lived daemon reader per line; if a descendant retains the old stdout pipe it may remain alive until that pipe closes, without accessing replacement state. Request writes and finite existing process-termination waits are outside the reply-read deadline. No new dependencies, process protocol or install policy. Independent review and the mandatory combined gate remain pending.

Enforce positive ready/reply pipe deadlines using a small process-bound one-shot Queue/thread reader, retaining one reply budget, escaped fallback and no-install restart. Actual silent/partial reply and silent startup regressions failed before correction; replacements handle subsequent requests. Removed the write-only stderr field while preserving local diagnostic draining. Independent review passed 42 tests, 11 subtests and six actual-pipe probes, including aggregate budgets, late-output isolation, bounded replacement startup and cleanup. Request writes and existing finite termination waits remain outside the read deadline; a descendant-held old pipe can retain its isolated daemon until closure. Final combined verification passed on 6f76b4398d83c6a6217a0e7049428d976e531c63: unchanged pre-commit run -a --hook-stage pre-push, mandatory Chromium enabled, 4163 tests passed in 287.30s, 96.72% aggregate branch-inclusive coverage against 95%. All normal hygiene, Ruff, formatting and deptry checks passed. Exact backend, reader and TASK-125 heads are ancestors; all merged source/test paths were checked against their reviewed contents. No real mail, credential changes or remote operations. The following closure commit changes task metadata only; code and tests remain the verified candidate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Enforce positive ready/reply pipe deadlines using a small process-bound one-shot Queue/thread reader, retaining one reply budget, escaped fallback and no-install restart. Actual silent/partial reply and silent startup regressions failed before correction; replacements handle subsequent requests. Removed the write-only stderr field while preserving local diagnostic draining. Independent review passed 42 tests, 11 subtests and six actual-pipe probes, including aggregate budgets, late-output isolation, bounded replacement startup and cleanup. Request writes and existing finite termination waits remain outside the read deadline; a descendant-held old pipe can retain its isolated daemon until closure. Combined required gate: 4163 passed, 96.72% coverage; implementation and independent review complete. Local integration is authorized; no public push.
<!-- SECTION:FINAL_SUMMARY:END -->
