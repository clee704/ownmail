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
ordinal: 40
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Carried over from ROADMAP.md's 'Web UI Polish' section, filed verbatim as an open question: 'Verify CJK attachment filename encoding (RFC 5987) - check if this is still an issue.' Non-ASCII attachment filenames (Korean, Japanese, Chinese) are encoded per RFC 2231/5987 as filename*=UTF-8''%XX... in Content-Disposition. Confirm whether the download path in web.py and the filename extraction in parser.py handle that correctly end-to-end, or whether it mangles/mojibakes. Start by checking against a real CJK-attachment email in the archive - tests/fixtures/ already has Korean encoding fixtures (korean_encoded.eml, split_multibyte_rfc2047.eml) but those cover header encoding, not attachment filenames. If it turns out to already work, close this task with a regression test proving it rather than deleting it silently.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Determined whether CJK attachment filenames are handled correctly on both extraction and download
- [ ] #2 A test fixture + test covers a CJK attachment filename either way (regression guard if it works, failing-then-fixed if it doesn't)
<!-- AC:END -->
