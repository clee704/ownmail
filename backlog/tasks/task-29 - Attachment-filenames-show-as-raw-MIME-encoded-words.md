---
id: TASK-29
title: Attachment filenames show as raw MIME encoded-words
status: In Progress
assignee: []
created_date: '2026-07-31 18:48'
updated_date: '2026-07-31 18:59'
labels:
  - bug
dependencies: []
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Attachment filenames encoded as unquoted RFC 2047 encoded-words in Content-Disposition (`filename==?UTF-8?B?...?=`) are displayed verbatim in the web UI and used verbatim as the download filename. Python's `get_filename()` does not decode encoded-words in parameter values, and `_extract_attachment_filename()` in web.py reaches `_fix_mojibake_filename()` first — which returns an all-ASCII name unchanged — so the `if "=?" in filename` decode branch below it is unreachable for exactly the case it was written for. `parser.py` has the same gap on the indexing side: it sanitizes `get_filename()` without decoding, so the encoded-word text goes into the FTS `attachments` column and `attachment:` search cannot match the real name. Confirmed against a real archive. Distinct from TASK-8, which covers RFC 2231/5987 percent-encoded CJK names.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Encoded-word filenames decode for display and download in the web UI
- [x] #2 Fixture + regression test covering an unquoted RFC 2047 filename parameter
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause: the message is parsed with email.policy.default, which rejects `filename==?UTF-8?B?...?=` as an InvalidParameter — the encoded-word is not a valid parameter token unquoted. The whole parameter is dropped, so `get_filename()` returns None and every attachment rendered as the generic 'attachment'. (Under compat32 the same header yields the raw encoded-word instead; either way the name never reaches the page.)

Fix is in `_extract_attachment_filename` in web.py, which already reads the raw part bytes for RFC 2231 cases:
- The raw scan is now scoped to the part's header block and unfolded first. Previously it searched the entire part including the base64 payload, where a filename= parameter can appear by chance.
- The plain filename= path accepts a bare token as well as a quoted value, and decodes RFC 2047 encoded-words found in either.
- In the get_filename() fallback, the encoded-word branch moved ahead of the mojibake fix. It was unreachable before: `_fix_mojibake_filename` returns an all-ASCII name unchanged and the caller returned on that truthy value.

`as_bytes()` was verified to preserve the invalid parameter verbatim, so the raw scan can still see what the parsed view discarded.

Verified against a real archive: attachment names that rendered as 'attachment' now show their real names, Latin and Hangul both.

Not covered here — filed as TASK-30: the indexing side. parser.py also calls `get_filename()`, so for this encoding it records no attachments at all and `has_attachments` is stored as 0, leaving the message invisible to `has:attachment` and `attachment:` search. The quoted encoded-word form already works there — the default policy decodes it — so only the unquoted form is affected.
<!-- SECTION:NOTES:END -->
