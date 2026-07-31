---
id: TASK-30
title: Attachments named with unquoted encoded-words are not indexed
status: Done
assignee: []
created_date: '2026-07-31 18:59'
updated_date: '2026-07-31 19:13'
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
- [x] #1 parser.py records attachment names for unquoted encoded-word filename parameters
- [x] #2 has_attachments is set for such messages, so has:attachment finds them
- [x] #3 Filename extraction lives in one place rather than being duplicated across web.py and parser.py
- [x] #4 Regression test covering the unquoted encoded-word case through parse_file
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Moved `extract_attachment_filename` and `_fix_mojibake_filename` (plus the four header regexes) from web.py into parser.py, which is the lower module — web.py already imports it, so the dependency runs the right way and there is one implementation rather than two. web.py imports the name and its three call sites are unchanged otherwise.

The move dropped web.py's `decode_header` from the picture: the two calls inside now use parser.py's existing `EmailParser._decode_header_value`, which decodes RFC 2047 the same way and additionally groups adjacent same-charset encoded-words. All the pre-existing extraction tests pass against it unchanged, so web.py's `decode_header` stayed where it is for header use.

parse_file now calls `extract_attachment_filename(part)` instead of `part.get_filename()`.

Verified end to end on a temporary archive: an unquoted encoded-word attachment indexes as 'Holiday Calendar 2026.pdf', has_attachments is stored as 1, and `has:attachment`, `attachment:Holiday` and `attachment:Calendar` each return the message while `attachment:Nonexistent` returns none.

Tests moved with the code: `TestExtractAttachmentFilenameEncodings` went from test_web.py to test_parser.py. Three duplicate `_fix_mojibake_filename` tests in test_coverage_boost.py were deleted rather than retargeted — test_fixtures.py already covers the same cases, with a stronger assertion in the Korean one.

Existing archives need `ownmail rebuild` before search reflects this.
<!-- SECTION:NOTES:END -->
