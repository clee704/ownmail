---
id: TASK-32.6
title: Add clear empty states and message action feedback
status: To Do
assignee: []
created_date: '2026-09-12 18:33'
labels:
  - ui
  - ux
dependencies: []
parent_task_id: TASK-32
priority: medium
ordinal: 6
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Explain empty screens and make message action outcomes visible. An empty archive with an empty query currently renders no explanatory main content. Trash, restore and permanent-delete fetch handlers react only to successful responses, leaving HTTP errors and network failures without useful feedback. Selection can therefore appear stuck after an unsuccessful action.

Provide distinct empty-archive, no-match and empty-Trash states with useful next actions. Add pending, success and failure feedback to existing message actions, prevent accidental repeat submissions while pending, and retain selection when an action fails. Use precise labels such as Move to Trash, Restore and Delete forever. Preserve existing confirmation and server-side deletion behavior. Storage, retention, bulk-operation atomicity and deletion policy changes require separate tasks and authorization.

Evidence: ownmail/templates/search.html (empty state and trashSelected), trash.html and email.html (fetch handlers); base.html loading overlay.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Empty archive, no search matches and empty Trash each explain the state and offer a relevant next action without exposing implementation details.
- [ ] #2 Message and bulk actions show a pending state, prevent repeat submission while pending, and report success only after the server confirms it.
- [ ] #3 HTTP errors and network failures show an accessible error and retry path, retain the current context and selection, and clear any pending/loading state.
- [ ] #4 Move to Trash, Restore and Delete forever use distinct wording and preserve existing confirmations and server behavior; synthetic success/error cases and empty views are verified.
<!-- AC:END -->
