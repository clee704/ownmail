---
id: TASK-80
title: Preserve attachments around embedded messages
status: To Do
assignee: []
created_date: '2026-09-14 04:07'
labels: []
dependencies: []
type: bug
ordinal: 84000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Synthetic multipart messages expose separate MIME traversal defects: ordinary attachments after a message/rfc822 part are omitted from the detail list because its embedded-message counter never resets; an explicitly attached message/rfc822 part is treated only as a digest entry, and its download returns an empty payload. Keep detail attachment indices aligned with downloads and serialize attached messages correctly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A top-level attachment after an embedded message remains listed and downloads its original bytes.
- [ ] #2 An explicitly attached message/rfc822 file is listed and downloads a nonempty valid message.
- [ ] #3 Synthetic regressions cover attachment ordering and existing digest display.
<!-- AC:END -->
