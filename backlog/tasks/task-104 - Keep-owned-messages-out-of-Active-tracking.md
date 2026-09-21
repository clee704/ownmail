---
id: TASK-104
title: Keep owned messages out of Active tracking
status: In Progress
assignee: []
created_date: '2026-09-21 07:06'
labels: []
dependencies: []
priority: high
ordinal: 105000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Once a message is owned, returning its server copy to Inbox must not create an Active copy. Preserve archived contents, labels and local Trash. Remove previously cached duplicates only after verifying an owned copy; retain uncertain matches and unowned live mail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A verified owned identity is skipped before live body reads regardless of its current server state.
- [x] #2 Existing Active duplicates are removed using verified local ownership, including excluded or omitted live entries; missing or ambiguous owned evidence retains the cache.
- [x] #3 IMAP folder moves with new scoped identities do not create Active duplicates when exact contents verify an owned match; unrelated accounts and sources remain isolated.
- [ ] #4 Documentation supersedes the prior return-to-Inbox policy; regression tests, review and full pre-push checks pass with clean committed work.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base 8b022de. Reuse scoped owned_match/OwnedLookup and cache removal. Do not delete or modify owned email files, change schema or server state. Implement in an isolated worktree.
<!-- SECTION:PLAN:END -->

## Implementation Notes

- Supersedes TASK-28 return-to-Inbox behavior: verified owned identities are skipped in every server state before live body reads. An exact-content ownership check also prevents caching when a folder move changes the remote identity.
- Existing duplicate cache copies are pruned using verified local ownership before server enumeration. Source/account boundaries, local Trash, file integrity and ambiguous matching rules reuse owned_match. Unverifiable local ownership retains the cache; server failure or Active exclusions do not prevent retiring a verified duplicate.
- Lifecycle tests now assert no Active result/cache/body read for returned owned mail. Reader assertions follow the new policy. Old duplicate fixtures are explicitly seeded to retain read-time compatibility coverage during upgrade.
- Focused lifecycle/search/reader and ownership regressions passed (137 tests). Full pre-push checks passed: 3,774 tests, one expected failure, 96.34% branch-inclusive coverage; required browser checks ran. Mutation tests rejected unwanted body reads, retained duplicates and the old database-only identity shortcut.

- Independent Claude Opus 5 review found a legacy identity shortcut that could leave an unrefreshable cached copy. Reproduced with legacy and scoped database IDs lacking capture provenance. The early skip now requires verified identity evidence; exact-byte matching still uses freshly read content. Removed the obsolete hash shortcut. Root review and regression/mutation tests verified closure. An independent follow-up attempt was unavailable because the reviewer reached its session limit.
