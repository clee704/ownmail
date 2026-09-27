---
id: TASK-80
title: Preserve attachments around embedded messages
status: Done
assignee: []
created_date: '2026-09-14 04:07'
updated_date: '2026-09-27 14:48'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Synthetic multipart messages expose separate MIME traversal defects: ordinary attachments after a message/rfc822 part are omitted from the detail list because its embedded-message counter never resets; an explicitly attached message/rfc822 part is treated only as a digest entry, and its download returns an empty payload. Keep detail attachment indices aligned with downloads and serialize attached messages correctly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A top-level attachment after an embedded message remains listed and downloads its original bytes.
- [x] #2 An explicitly attached message/rfc822 file is listed and downloads a nonempty valid message.
- [x] #3 Synthetic regressions cover attachment ordering and existing digest display.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 8b97b68.
1. Build the detail attachment list and the download lookup from one helper that enumerates is_attachment parts in walk order, so indices cannot diverge.
2. Replace the never-reset embedded-message counter with the set of parts inside each message/rfc822 part, so later siblings reach the body and attachment handling.
3. Serialize an attached message/rfc822 part as its embedded message (original header folding, CRLF) for size and download.
4. Regression tests: attachment after a digest entry, explicitly attached message listed and downloaded, digest display and nested attachments unchanged.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The detail list and the download route now take attachments from one helper, _attachment_parts (every is_attachment part in walk order), so link indices and downloads cannot diverge. The body walk skips only the parts inside each message/rfc822 part, so later siblings reach the body again.

An attached message downloads as the message it holds, serialized with its received header folding and CRLF line endings; the regression gets the embedded bytes back exactly. It still renders inline as a digest entry, as before.

Side effects of sharing the list: a single-part message that is itself an attachment is now listed (the download route already served it at index 0), and attachments inside a nested attached message are no longer listed twice.

Known limitation: a message/rfc822 part with base64 or quoted-printable transfer encoding, which RFC 2046 forbids, parses as a headerless message, so its download and digest entry show the encoded text. Whether such mail occurs in practice is unverified; not filed.
<!-- SECTION:NOTES:END -->
