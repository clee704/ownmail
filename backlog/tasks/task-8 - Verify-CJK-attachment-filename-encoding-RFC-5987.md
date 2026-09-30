---
id: TASK-8
title: Verify CJK attachment filename encoding (RFC 5987)
status: In Progress
assignee:
  - '@codex-ic2'
created_date: '2026-07-24 20:29'
updated_date: '2026-09-30 13:34'
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
- [x] #1 Determined whether CJK attachment filenames are handled correctly on both extraction and download
- [x] #2 A test fixture + test covers a CJK attachment filename either way (regression guard if it works, failing-then-fixed if it doesn't)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 35329257b5e86c06be1f016ed50a19e03de908d0 (completed TASK-122); isolated branch test/cjk-attachment-downloads.
1. Preserve the current passing product behavior. Add one fully synthetic RFC2231 MIME fixture containing Korean, Japanese and Chinese attachment filenames with distinct payload bytes.
2. Extend only TestWebAttachmentRfc2231 to exercise actual parser filename extraction and actual Flask attachment responses, checking exact names, UTF-8 filename* encoding/round trip, download disposition and unchanged payload bytes. Preserve its existing message-route check.
3. Demonstrate meaningful assertions with runtime-only wrong-name/header/payload mutations; leave production files unchanged. Run focused fixture/parser/attachment tests, static checks and the complete required browser/coverage pre-push gate with private runtime resources and coordinated Chromium use.
4. Self-review the complete task diff, commit checkpoints, then record verified acceptance and clean closure without integration or publication.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verification task, not a production bug: nine private synthetic observations on the review base already preserve Korean/Japanese/Chinese extraction names, UTF-8 extended Content-Disposition filenames and original payload bytes through actual parser/Flask routes. The gap is durable coverage: the existing RFC2231 web test only requests the message page and checks status 200, and no committed MIME fixture uses filename*=.
Owned scope is the new synthetic RFC2231 fixture, the existing TestWebAttachmentRfc2231 family and this ledger. No production code, real attachments/mail/config/credentials, sanitizer lifecycle, host/security policy or dependencies change. TASK-121 lifecycle ownership and TASK-123 consolidation remain separate. Acceptance is verified for all three requested languages before closing; the mandatory full pre-push gate remains required even for this tests-only task.

Current behavior confirmed for all three requested languages. The committed synthetic MIME fixture uses RFC2231 UTF-8 extended filename parameters for Korean, Japanese and Chinese names and three distinct base64-encoded binary payloads. The existing RFC2231 web regression now checks actual EmailParser filename extraction plus actual attachment downloads: exact names, one UTF-8 filename* parameter in an ASCII response header, strict UTF-8 round trip and unchanged payload bytes. Its original message-page assertion is retained. No production code changed.
Focused verification: 31 parser/attachment tests passed. Runtime-only mutation checks prove the strengthened test rejects lost parser filenames, lost download filenames, missing extended filename parameters, incorrect header charset and corrupted payloads; the original smoke test incorrectly passed all five mutations. Both tests pass against the unchanged product. Ruff check, format --check and deptry pass. Author self-review and independent Astra Ultra read-only support review found no correctness or scope issues. Full required pre-push/browser/coverage validation remains pending before closure.
<!-- SECTION:NOTES:END -->
