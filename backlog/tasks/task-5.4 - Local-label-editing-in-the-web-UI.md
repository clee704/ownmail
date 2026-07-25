---
id: TASK-5.4
title: Local label editing in the web UI
status: To Do
assignee: []
created_date: '2026-07-25 07:04'
updated_date: '2026-07-25 07:04'
labels: []
milestone: m-3
dependencies: []
parent_task_id: TASK-5
priority: medium
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The 'manage' half of ownmail, and the feature that makes doc-8's ownership-transfer model real: after capture, ownmail owns a message's labels and the user edits them locally.

Nothing exists today. web.py has trash/restore/delete-forever routes (1912-1958) but no label mutation — no route, no database helper, no UI affordance. Local *deletion* of archived mail is already owned by ownmail; labels are the missing half.

## Shape

- Sidecar is the write target and the source of truth (invariant #1). The email_labels table is updated alongside as the derived index, exactly as the download path already does (archive.py:410-425).
- Writes must stay atomic — sidecar.write_labels already does temp-file + rename.
- rebuild --only sidecars must continue to treat the sidecar as authoritative, so a local edit survives any rebuild. It already does.
- Interacts with TASK-19: exclude_labels filters the index, not the sidecar, so a locally added label behaves like any other. Confirm an excluded label cannot be 'added' into invisibility.

## Constraint from doc-8

Nothing may overwrite a locally edited label with server state. update-labels currently would (see TASK-20) — that command needs scoping or removal before or alongside this, or a user's edits are one sync command away from being lost.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Labels can be added and removed on an archived message from the web UI
- [ ] #2 The sidecar is the write target; email_labels is updated as the derived index
- [ ] #3 A locally edited label survives rebuild and rebuild --only sidecars unchanged
- [ ] #4 No sync or maintenance command silently overwrites a local edit with server state
<!-- AC:END -->
