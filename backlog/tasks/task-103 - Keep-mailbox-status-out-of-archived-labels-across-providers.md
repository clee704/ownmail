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
- [ ] #1 Gmail API single, batch and Active capture omit status labels while retaining organizational labels and lifecycle decisions.
- [ ] #2 IMAP capture omits status views and Gmail status labels without dropping real similarly named folders or labels.
- [ ] #3 Owned snapshots remain unchanged by later server status changes, and documentation explains the actual scope of unfinished-message discovery.
- [ ] #4 Regression tests, review, full pre-push checks and clean committed work are complete.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base c37c2d1. Filter status at provider label boundaries, retaining raw lifecycle/scope metadata and existing archive snapshots. Use an isolated worktree to avoid interrupting live refresh during development.
<!-- SECTION:PLAN:END -->
