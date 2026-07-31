---
id: TASK-30
title: Attachments named with unquoted encoded-words are not indexed
status: To Do
assignee: []
created_date: '2026-07-31 18:59'
labels:
  - bug
dependencies: []
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
parser.py collects attachment filenames with `part.get_filename()`. Under email.policy.default an unquoted RFC 2047 encoded-word parameter (`filename==?UTF-8?B?...?=`) is rejected as invalid and dropped, so get_filename() returns None: the name never reaches the FTS `attachments` column and `has_attachments` is stored as 0. Such a message is invisible to both `has:attachment` and `attachment:<name>` search even though the web detail page now shows the names correctly (TASK-29).

web.py's `_extract_attachment_filename` already recovers these from the raw header, but parser.py cannot import it — web.py imports parser.py, so the dependency would be circular. Fixing this properly means moving that helper (and `_fix_mojibake_filename` plus web.py's `decode_header`, which it calls) into parser.py and re-exporting from web.py so existing imports keep working. Worth confirming first whether parser.py's existing `_decode_header_value` can serve in place of web.py's `decode_header`, which would shrink the move.

Note the quoted form `filename="=?UTF-8?B?...?="` already works — the default policy decodes it — so only the unquoted variant is affected. Requires a reindex (`ownmail rebuild`) to take effect on an existing archive.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 parser.py records attachment names for unquoted encoded-word filename parameters
- [ ] #2 has_attachments is set for such messages, so has:attachment finds them
- [ ] #3 Filename extraction lives in one place rather than being duplicated across web.py and parser.py
- [ ] #4 Regression test covering the unquoted encoded-word case through parse_file
<!-- AC:END -->
