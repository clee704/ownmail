---
id: TASK-40
title: >-
  Recover body text when charset validation or sampling selects the wrong
  encoding
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-11 10:43'
updated_date: '2026-09-30 04:26'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Body charset recovery has four gaps reproduced with synthetic HTML in both the web decoder and EmailParser._safe_get_content:

- Valid UTF-8 containing a literal U+FFFD is rejected, so `<p>Café �</p>` declared as UTF-8 becomes `<p>CafÃ© ï¿½</p>`.
- UTF-8 `<p>Café</p>` declared as ISO-8859-1 becomes `<p>CafÃ©</p>` because the declared codec decodes cleanly and passes validation.
- Undeclared EUC-KR `<p>한글</p>` becomes `<p>ÇÑ±Û</p>` because the CJK fallback requires more than ten high bytes.
- Undeclared EUC-KR `<html><head><!--` + 4,200 ASCII `a` characters + `--></head><body>안녕하세요 반갑습니다</body></html>` falls back to Latin-1 because only the first 4,000 bytes are sampled.

Review charset selection and validation for these cases. Keep display and indexing consistent, and define conservative recovery for conflicting declarations so correctly labelled legacy content remains intact. Unicode preview padding is a separate fix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Valid UTF-8 containing a literal U+FFFD preserves the remaining text in display and indexing.
- [ ] #2 Conflicting Latin-1 declarations have a documented recovery rule, with regression coverage for UTF-8 payloads and correctly labelled legacy text.
- [ ] #3 Undeclared short EUC-KR content and EUC-KR content after a long ASCII HTML preamble decode correctly in display and indexing.
- [ ] #4 Synthetic regression tests cover all four reproductions and pass with the required repository checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC2. Reserved for TASK-40. Review base: 654e88c2836e1426732b46b87ec8fa5ea3ced40c. Branch: fix/body-charset-recovery.
Intended scope: ownmail/parser.py EmailParser._safe_get_content and its charset selection/validation helpers, including _validate_decoded_text and _try_decode; ownmail/web.py _try_decode, _decode_text_body and _decode_html_body; tests/test_parser.py body charset regressions and tests/test_web.py TestDecodeTextBody, TestDecodeHtmlBody, TestTryDecode and TestDecodeHtmlBodyCharsetEdges, plus dedicated synthetic body-charset tests; this task file. Preserve valid UTF-8 containing U+FFFD, correctly labelled legacy text and header behavior while defining conservative recovery for conflicting declarations.
Ownmail IC1 owns HtmlSanitizer dependency/startup handling, web.run_server sanitizer guidance, tests/test_sanitizer.py and TestRunServer. Both tasks touch ownmail/web.py and tests/test_web.py in separate function/test families. Preserve IC1's functions and tests; integration is serialized after TASK-118. Shared imports or helpers, overlap and any new scope requirement must be reported before expanding scope. The integration checkout, README files and execution-order document are reserved for the manager. No real mail files, archive database, credentials, live providers or server state may be changed.
Next action: Ownmail IC2 creates its isolated worktree from the common claim base, verifies the four synthetic charset reproductions and existing alternatives, and records its bounded implementation plan before substantive work.
<!-- SECTION:NOTES:END -->
