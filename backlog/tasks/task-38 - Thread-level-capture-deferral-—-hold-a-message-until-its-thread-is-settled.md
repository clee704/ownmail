---
id: TASK-38
title: Thread-aware server cleanup — retain copies while a thread is active
status: To Do
assignee: []
created_date: '2026-08-06 19:51'
updated_date: '2026-09-14 08:53'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
priority: medium
ordinal: 6
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement thread protection for server cleanup under
[Ownership philosophy](../../docs/philosophy.md). This supersedes the capture
deferral settled in TASK-33 on 2026-08-06.

Archive eligible messages immediately, including sent replies in ongoing
conversations. Keep their server copies available to mail clients while any
message in the thread remains in Inbox or unfinished outgoing state. Once the
thread clears, TASK-14.2 may clean up verified archived copies.

Trash and Spam members do not keep a thread active. A candidate that itself
returns to Inbox or unfinished outgoing state is protected even if it was
archived earlier. Uncertain thread membership or an incomplete view postpones
cleanup; it must not delay archival or alter the archived contents and labels.

A thread left active indefinitely retains its server copies indefinitely. There
is no age limit or override in this task. A later reply protects copies still
present, without restoring copies already removed.

Reuse existing provider enumeration and thread identity support where possible.
Use provider thread identifiers when available; validate the plain IMAP approach
against its available headers and identity guarantees. Do not assume that a
partial header match proves a thread is inactive.

Build and verify this protection before enabling TASK-14.2 cleanup. The old
evidence gate for implementing capture deferral no longer applies: preserving
live client conversations is part of the cleanup design. This task changes no
server data by itself; TASK-14.2 retains its existing approval requirements.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An eligible message is captured immediately even when its thread contains Inbox or unfinished outgoing mail
- [ ] #2 Server cleanup is held while the candidate or any thread member is Active, and becomes eligible after the thread clears
- [ ] #3 Trash and Spam thread members do not hold cleanup; sent and filed messages use the same protection rule
- [ ] #4 Incomplete or uncertain server/thread state skips cleanup, with provider-specific tests including plain IMAP
- [ ] #5 Archived contents and labels remain unchanged when the server copy becomes Active again
- [ ] #6 Configuration documentation explains that a thread left Active retains its server copies indefinitely, while eligible messages still enter the archive
- [ ] #7 A later reply protects server copies still present and does not restore previously removed copies
<!-- AC:END -->
