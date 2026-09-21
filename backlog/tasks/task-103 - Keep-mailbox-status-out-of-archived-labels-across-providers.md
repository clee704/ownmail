---
id: TASK-103
title: Keep mailbox status out of archived labels across providers
status: In Progress
assignee: []
created_date: '2026-09-21 06:54'
labels: []
dependencies: []
priority: high
ordinal: 104000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Apply one capture policy across Gmail API and IMAP: omit read, starred and important status while preserving organizational labels and folders. Keep lifecycle observations separate from persisted labels and preserve owned snapshots.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Gmail API single, batch and Active capture omit status labels while retaining organizational labels and lifecycle decisions.
- [x] #2 IMAP capture omits status views and Gmail status labels without dropping real similarly named folders or labels.
- [x] #3 Owned snapshots remain unchanged by later server status changes, and documentation explains the actual scope of unfinished-message discovery.
- [ ] #4 Regression tests, review, full pre-push checks and clean committed work are complete.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base c37c2d1. Filter status at provider label boundaries, retaining raw lifecycle/scope metadata and existing archive snapshots. Use an isolated worktree to avoid interrupting live refresh during development.
<!-- SECTION:PLAN:END -->

## Implementation Notes

- Gmail API filters UNREAD, STARRED and IMPORTANT by system ID. IMAP filters advertised status-view folder names and Gmail special status labels at the label boundary; real similarly named organizational labels survive. Raw lifecycle and Active exclusion scope still use full server state.
- Existing owned labels and files remain unchanged. The generic legacy UNREAD reservation is not broadened: doing so would reinterpret local labels and alter historical reconciliation protections.
- The retained-Archive example was misleading: later status changes do not update owned snapshots. Unknown-state discovery protects capture of unfinished, not-yet-owned messages. Existing return-to-Inbox behavior still represents live state separately while preserving the owned snapshot.
- Focused provider and lifecycle tests pass (401 tests). Added cross-provider on-disk capture and repeat-snapshot checks, status-view localization/scope coverage, and extended single/batch label tests. Root review checked capture boundaries, lifecycle/scope preservation and existing reconciliation protections. Independent Claude Opus 5 review found no actionable issues. Mutation checks rejected Gmail and IMAP status persistence regressions. Full pre-push checks passed: 3,762 tests, one expected failure, 96.34% branch-inclusive coverage; browser checks were required.
