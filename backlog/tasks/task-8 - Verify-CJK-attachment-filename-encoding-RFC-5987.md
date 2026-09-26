---
id: TASK-8
title: Verify CJK attachment filename encoding (RFC 5987)
status: To Do
assignee: []
created_date: '2026-07-24 20:29'
labels: []
milestone: m-3
dependencies: []
priority: low
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Carried over from ROADMAP.md's 'Web UI Polish' section, filed verbatim as an open question: 'Verify CJK attachment filename encoding (RFC 5987) - check if this is still an issue.' Non-ASCII attachment filenames (Korean, Japanese, Chinese) are encoded per RFC 2231/5987 as filename*=UTF-8''%XX... in Content-Disposition. Confirm whether the download path in web.py and the filename extraction in parser.py handle that correctly end-to-end, or whether it mangles/mojibakes. Extraction is now covered: tests/test_parser.py tests extract_attachment_filename with Korean filename*=UTF-8'' and unknown-8bit values, and TASK-29 added tests/fixtures/rfc2047_filename_param.eml, a Korean RFC 2047 attachment filename. Remaining: no fixture uses the RFC 2231 filename*= form, and no test asserts the Content-Disposition that the /attachment/ route produces for a non-ASCII name. Close this task once a download test covers that.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Determined whether CJK attachment filenames are handled correctly on both extraction and download
- [ ] #2 A test fixture + test covers a CJK attachment filename either way (regression guard if it works, failing-then-fixed if it doesn't)
<!-- AC:END -->
