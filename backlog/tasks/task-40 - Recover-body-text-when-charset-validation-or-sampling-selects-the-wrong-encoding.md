---
id: TASK-40
title: >-
  Recover body text when charset validation or sampling selects the wrong
  encoding
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-11 10:43'
updated_date: '2026-09-30 05:13'
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
- [x] #1 Valid UTF-8 containing a literal U+FFFD preserves the remaining text in display and indexing.
- [x] #2 Conflicting Latin-1 declarations have a documented recovery rule, with regression coverage for UTF-8 payloads and correctly labelled legacy text.
- [x] #3 Undeclared short EUC-KR content and EUC-KR content after a long ASCII HTML preamble decode correctly in display and indexing.
- [ ] #4 Synthetic regression tests cover all four reproductions and pass with the required repository checks.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Premise verified at c44eb0f: all four synthetic HTML reproductions corrupt display and parser/indexing text. No existing header decoder or charset validation helper resolves body selection. This is a bounded user-visible correctness fix, with no dependency, schema, archive-file or running-system changes.

1. Preserve strict UTF-8 output with literal U+FFFD while retaining validation for failed/legacy candidates. Define a body-only rule: for a Latin-1 declaration, prefer the complete payload when it is strict UTF-8; preserve declared legacy decoding otherwise and retain other correct declarations.
2. Apply the existing CJK fallback chain whenever any non-ASCII byte occurs anywhere in the full payload, removing the short-content threshold and 4,000-byte sampling cutoff. Keep MIME/meta charset precedence and graceful replacement fallback.
3. Keep display and indexing selection consistent using the existing parser body decoding helpers; coordinate any shared import/helper change with the manager before implementation. Limit web edits to assigned body decoder functions and the necessary import.
4. Add synthetic regressions for text/HTML display and parsed indexing, literal replacement characters, misdeclared UTF-8, correctly declared legacy text, short Korean content and long ASCII preambles. Verify the tests fail against the base, then pass after the fix.
5. Self-review the full task diff, coordinate the full-suite/pre-push browser slot, run required coverage/lint/format/deptry and browser gates, record evidence, commit locally and hand off shared README wording for manager integration.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC2. Reserved for TASK-40. Review base: 654e88c2836e1426732b46b87ec8fa5ea3ced40c. Branch: fix/body-charset-recovery.
Intended scope: ownmail/parser.py EmailParser._safe_get_content and its charset selection/validation helpers, including _validate_decoded_text and _try_decode; ownmail/web.py _try_decode, _decode_text_body and _decode_html_body; tests/test_parser.py body charset regressions and tests/test_web.py TestDecodeTextBody, TestDecodeHtmlBody, TestTryDecode and TestDecodeHtmlBodyCharsetEdges, plus dedicated synthetic body-charset tests; this task file. Preserve valid UTF-8 containing U+FFFD, correctly labelled legacy text and header behavior while defining conservative recovery for conflicting declarations.
Ownmail IC1 owns HtmlSanitizer dependency/startup handling, web.run_server sanitizer guidance, tests/test_sanitizer.py and TestRunServer. Both tasks touch ownmail/web.py and tests/test_web.py in separate function/test families. Preserve IC1's functions and tests; integration is serialized after TASK-118. Shared imports or helpers, overlap and any new scope requirement must be reported before expanding scope. The integration checkout, README files and execution-order document are reserved for the manager. No real mail files, archive database, credentials, live providers or server state may be changed.
Next action: Ownmail IC2 creates its isolated worktree from the common claim base, verifies the four synthetic charset reproductions and existing alternatives, and records its bounded implementation plan before substantive work.

Review base for this isolated implementation: c44eb0f620d79e9be10ff8449969408adac6341b. Four synthetic premises verified in display, content extraction and indexing; implementation pending manager coordination for one shared body decoder/import. No personal archive data used.

Implementation checkpoint: parser._decode_body now owns body-only MIME/meta declaration selection and the complete-payload fallback; web wrappers reuse it, and duplicate body helpers/constants were removed with manager coordination. Strict UTF-8 preserves authored U+FFFD; complete valid UTF-8 overrides only Latin-1 declarations, including aliases and HTML meta. Other previously correct legacy declarations retain precedence. Focused tests and four headless Chromium display checks pass. The initial synthetic regressions failed at the base, verifying they can detect the defect.

Baseline limitation: short correctly declared Windows-1251 Cyrillic already fails the readability whitelist before this task. Its exact plain/HTML reproduction is preserved in TASK-126, filed through Backlog with manager approval; no Cyrillic validator expansion is included here. AC2 covers conflicting Latin-1 recovery and preservation of previously correct Latin-1, Windows-1252 and Korean declarations, rather than claiming every legacy charset is correct.

Next action: author self-review, then coordinated complete coverage and browser/pre-push gates before closure; do not mark AC4 or Done until they pass. Shared README wording remains a manager integration proposal.

Author self-review against common base c44eb0f completed across the owned decoder/helper changes, declaration precedence, MIME/meta aliases, graceful fallbacks and synthetic regression/browser tests. No actionable introduced findings. Header decoding and IC1 startup/sanitizer functions are unchanged. Focused local hygiene, ruff and deptry hooks pass; complete coordinated pre-push coverage remains pending.

Combined integration checkpoint: rebased cleanly onto the integrated TASK-118 base 9dcfdc77c16497bd70b26007f46618804711fed8 with no conflicts. Shared startup/TestRunServer ASTs and sanitizer implementation/tests/README bytes match that base. UTF-8 recovery counts an authored U+FFFD as readable without bypassing validation of surrounding text; existing control-garbage rejection remains intact. Latin-1 recovery requires a complete readable strict UTF-8 payload. The corrected focused set, including all existing fixture charset families, passes 115 checks. Final combined required-browser pre-push coverage is the remaining closure gate.
<!-- SECTION:NOTES:END -->
