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
- [ ] #1 A verified owned identity is skipped before live body reads regardless of its current server state.
- [ ] #2 Existing Active duplicates are removed using verified local ownership, including excluded or omitted live entries; missing or ambiguous owned evidence retains the cache.
- [ ] #3 IMAP folder moves with new scoped identities do not create Active duplicates when exact contents verify an owned match; unrelated accounts and sources remain isolated.
- [ ] #4 Documentation supersedes the prior return-to-Inbox policy; regression tests, review and full pre-push checks pass with clean committed work.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base 8b022de. Reuse scoped owned_match/OwnedLookup and cache removal. Do not delete or modify owned email files, change schema or server state. Implement in an isolated worktree.
<!-- SECTION:PLAN:END -->
