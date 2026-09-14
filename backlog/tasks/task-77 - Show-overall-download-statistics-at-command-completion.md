---
id: TASK-77
title: Show overall download statistics at command completion
status: In Progress
assignee: []
created_date: '2026-09-14 03:58'
updated_date: '2026-09-14 04:02'
labels: []
dependencies: []
type: enhancement
ordinal: 81000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Append an overall summary after the per-source download summaries so users can see run-wide download and error counts and the final archive size.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The final summary sums download and error counts across Gmail and IMAP sources while preserving per-source summaries.
- [x] #2 The archived total uses the final database count without double-counting repeated accounts; source selection, skipped sources, zero downloads, and paused results are covered.
- [ ] #3 The complete pre-push gate passes and the change is committed.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The final archived count covers the whole archive. Run counts cover only selected sources. Existing provider and interruption behavior is preserved.

All CLI tests pass, including combined Gmail/IMAP results, repeated-account configurations, source selection, skipped sources, zero downloads, and interruption of either provider. The new regression tests failed against the previous implementation. TASK-78 records the existing per-account overcount when successful content-dedup skips do not add archive rows.

Independent review found no actionable issues. A deliberate in-memory mutation replacing download-count addition with assignment made both mixed-provider regression cases fail; production files remained unchanged.

The complete pre-push gate passed: file hygiene, Ruff, deptry, and the full pytest suite with the 95% branch-coverage gate.
<!-- SECTION:NOTES:END -->
