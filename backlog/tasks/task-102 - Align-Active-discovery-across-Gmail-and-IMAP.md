---
id: TASK-102
title: Align Active discovery across Gmail and IMAP
status: In Progress
assignee: []
created_date: '2026-09-21 06:22'
labels: []
dependencies: []
priority: high
ordinal: 103000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Use a consistent default Active policy across Gmail API and IMAP: discover unfinished or uncertain mail without repeatedly fetching metadata for retained eligible history. Keep ordinary capture incremental, preserve exclusions as Active-only controls, and retain conservative behavior when state cannot be safely narrowed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Standard IMAP repeat scans avoid retained filed-message metadata without manual exclusions while discovering old-UID drafts, pending and unknown flags.
- [ ] #2 Finished or removed pending messages are reconciled without losing capture candidates; failed and partial checks do not advance checkpoints.
- [ ] #3 Gmail-over-IMAP uses the same narrowed policy and retains exceptional-folder state checks and scoped identities.
- [ ] #4 Documentation and protocol-count/lifecycle tests describe the consistent policy and necessary fallback behavior.
- [ ] #5 Review, full pre-push checks, committed changes and clean working tree are complete.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base 60ee350. Reuse capture excluded membership to retain unresolved live identities; combine server-side Active searches, new UIDs and prior unresolved candidates. Keep legacy opt-out unchanged. Implement in isolated worktree before updating running server.
<!-- SECTION:PLAN:END -->
