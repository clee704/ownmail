---
id: TASK-40
title: >-
  Recover body text when charset validation or sampling selects the wrong
  encoding
status: To Do
assignee: []
created_date: '2026-09-11 10:43'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 43000
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
