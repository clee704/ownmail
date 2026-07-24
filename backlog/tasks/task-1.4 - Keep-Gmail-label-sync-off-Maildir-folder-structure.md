---
id: TASK-1.4
title: Keep Gmail label sync off Maildir folder structure
status: Done
assignee: []
created_date: '2026-07-23 18:44'
updated_date: '2026-07-23 19:22'
labels:
  - sync
  - gmail
dependencies: []
parent_task_id: TASK-1
priority: medium
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
If any IMAP-based path ever touches Gmail accounts, it must only sync [Gmail]/All Mail to avoid per-label folder duplication. Labels come from GmailProvider (Gmail API) or X-GM-LABELS, never from folder membership. See doc-1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No IMAP sync path for Gmail accounts pulls per-label folders
- [x] #2 GmailProvider remains the label source of truth for Gmail accounts
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Moot: TASK-1.2 (mbsync) was reverted after review - there is no IMAP-based sync path in the codebase at all now, so there is nothing that could pull per-label Maildir folders for a Gmail account. GmailProvider (Gmail API) remains the only sync path and label source of truth for Gmail, unchanged throughout this entire epic.

Kept as Done since the constraint holds true today (trivially - there's no competing code path), and the rule stays documented in doc-1 in case an IMAP-based Gmail path is ever proposed again in the future.
<!-- SECTION:NOTES:END -->
