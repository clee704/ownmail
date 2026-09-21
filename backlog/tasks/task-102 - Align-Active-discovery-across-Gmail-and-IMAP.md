---
id: TASK-102
title: Align Active discovery across Gmail and IMAP
status: Done
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
- [x] #1 Standard IMAP repeat scans avoid retained filed-message metadata without manual exclusions while discovering old-UID drafts, pending and unknown flags.
- [x] #2 Finished or removed pending messages are reconciled without losing capture candidates; failed and partial checks do not advance checkpoints.
- [x] #3 Gmail-over-IMAP uses the same narrowed policy and retains exceptional-folder state checks and scoped identities.
- [x] #4 Documentation and protocol-count/lifecycle tests describe the consistent policy and necessary fallback behavior.
- [x] #5 Review, full pre-push checks, committed changes and clean working tree are complete.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base 60ee350. Reuse capture excluded membership to retain unresolved live identities; combine server-side Active searches, new UIDs and prior unresolved candidates. Keep legacy opt-out unchanged. Implement in isolated worktree before updating running server.
<!-- SECTION:PLAN:END -->

## Implementation Notes

- Standard IMAP and Gmail over IMAP now combine targeted Active searches, new UIDs and prior unresolved identities. Retained eligible filed mail requires no repeat metadata fetch without manual exclusions. Opt-out continues to use the existing legacy path.
- Unresolved standard IMAP identities retain folder and UIDVALIDITY; Gmail identities remain stable across folder moves. A versioned checkpoint forces one migration scan. Finished or deleted pending identities leave the next checkpoint.
- Gmail scheduled and uncertain folders retain full membership checks even when excluded from Active. Unusable flag catalogs or rejected searches fall back to full metadata; failed full scans and partial fetches do not propose a checkpoint.
- Protocol-count tests verify zero retained metadata fetches for 1,000 filed messages in both IMAP modes. Lifecycle tests cover older UID flag changes, eventual capture, excluded exceptional folders, removed pending messages, migration, malformed state and incomplete responses. Mutation checks rejected full-scan regression and missing exceptional membership checks.
- Initial full pre-push gate passed. Independent Claude Opus 5 review found excluded Gmail exceptional-folder membership and strict KEYWORD syntax issues; both were reproduced and fixed with tests. Root review checked pending identity validation, cursor behavior and fallback semantics. Review follow-up confirmed both findings closed with no direct regressions. Final full pre-push gate passed: 3,749 tests passed, one expected failure, 96.33% branch-inclusive coverage; required browser checks ran.

Implementation committed as `9cc1f30`; all acceptance criteria verified.
