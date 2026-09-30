---
id: TASK-40
title: >-
  Recover body text when charset validation or sampling selects the wrong
  encoding
status: In Progress
assignee:
  - Ownmail audit IC4
created_date: '2026-09-11 10:43'
updated_date: '2026-09-30 16:10'
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
- [x] #4 Synthetic regression tests cover all four reproductions and pass with the required repository checks.
- [x] #5 Undeclared short Western plain/HTML bodies preserve Noel, Munich and facade accent bytes through display and indexing while retained Korean, declared-charset and garbage-rejection controls pass.
- [x] #6 Web no longer reexports decoder helpers solely for tests; canonical parser helper tests retain unique assertions without duplicate helper families.
- [ ] #7 Audit follow-up receives independent review and the final combined repository gate before reclosure.
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

Final combined validation passed after the authorized clean rebase onto integrated TASK-118 base 9dcfdc77c16497bd70b26007f46618804711fed8. The exact required pre-commit run -a --hook-stage pre-push completed with all hooks passing and OWNMAIL_REQUIRE_BROWSER_TESTS=1; complete pytest coverage is 96.506% with branches included. The suite collects 3,971 tests and retains its existing strict TASK-13 expected failure. Direct repo-wide ruff check, ruff format --check and deptry pass. All four synthetic message cases render correctly in Chromium; 115 focused original/new charset checks pass, including control-garbage rejection and declared legacy preservation. Original-base regressions demonstrably failed before the fix.

Author self-review of the final combined diff found no remaining actionable introduced findings. Integrated TASK-118 run_server/TestRunServer behavior and sanitizer implementation/tests are preserved. Header decoding, dependencies, real mail files and running systems were not changed. TASK-126 remains the separately recorded pre-existing Cyrillic whitelist limitation; this task does not claim every legacy charset is correct.

Implementation and follow-up are committed locally on fix/body-charset-recovery; tested implementation revision: 698d10ac4da989433aa1ffedc33a3d35bc18c8b5. All acceptance criteria are verified. The manager owns subsequent integration and the shared README proposal; no push or publication is required or authorized. No TASK-40 blocker remains.

Authorized audit follow-up, review base 47e54fd653f65a33b394f52207602476dc14126b, isolated branch fix/audit-reader-regressions. Existing closure evidence is preserved; this task is reopened only for verified audit findings. No real mail, providers, credentials or running systems; no dependency, schema or main-branch change. Independent review and final combined mandatory-browser gate remain with the coordinator/integration owner before reclosure. Plan: (1) add failing synthetic Western cases to existing shared body regression matrix; (2) restrict newly added short-payload fallback to the verified Korean path while keeping the previous broad-CJK threshold over the complete payload; (3) remove only web.py lines 31-36 helper reexports and consolidate their callers into canonical parser tests, preserving unique character/alias/control cases; (4) run focused red/green, retained decoder and fixture checks, normal commit hooks and self-review; (5) hand off clean commits and exact evidence for independent review/combined gate.

Audit correction checkpoint: new exact Western regressions failed for all three undeclared examples in both plain and HTML bodies at the combined base. The bounded fix preserves the shared declaration/UTF-8 rules, always tries the existing Korean candidates for non-ASCII bodies, and retains the broader CJK fallback threshold of more than ten high bytes over the complete payload. This restores prior Western fallback behavior without sacrificing short/late Korean recovery. Focused charset and real-worker sanitizer checks pass: 154 tests and 368 subtests; no browser was used. Helper-test consolidation, affected browser checks, independent review and final combined gate remain pending. No claim of universal encoding inference is made.

Affected mandatory-browser matrix passed: 60 tests, including all nine recovered-body browser cases and seventeen spacing cases. The three Western bodies render correctly; short/late Korean, declared Cyrillic and UTF-8 recovery controls remain intact. Browser processes exited and the exclusive interval was released. AC5 is verified. Helper-test consolidation and independent review/final combined gate remain pending.

Helper consolidation complete: removed only the two test-only decoder reexports from web.py, consolidated 46 prior helper test methods into canonical parser families, and preserved unique valid/invalid codec, empty/control, CJK/kana/Latin, UTF-8 alias and authored-U+FFFD assertions. The former permissive invalid-decode assertion is strengthened to exact None. A semantic mapping is retained in private evidence; all unrelated test ASTs and every remaining web.py AST node are identical to the prior checkpoint. Focused decoder/charset/fixture checks pass: 210 tests. Four runtime-only mutations are rejected by the canonical assertions (valid-result loss, omitted validation, rejection of authored U+FFFD, unconditional text acceptance). No source mutation was used for those checks. Full-task self-review against the pinned combined base found no remaining introduced issue; declared charset precedence and garbage rejection are unchanged. AC6 is verified. Independent review and the integration owner final combined required gate remain outstanding; do not close from this checkpoint alone.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed body charset recovery for display and indexing through one shared selector. Authored UTF-8 U+FFFD is preserved while surrounding text validation still rejects garbage. Complete readable UTF-8 takes precedence over a Latin-1 declaration; other usable declarations retain precedence. The fallback no longer misses short Korean bodies or non-ASCII bytes after long ASCII preambles. Combined required-browser pre-push coverage passed at 96.506%, focused regressions passed, and final author self-review found no remaining introduced issue. Pre-existing Cyrillic validation is tracked separately in TASK-126. Work is committed locally for manager integration.

Audit follow-up: the bounded Western regression correction and decoder-helper consolidation are implemented and locally verified. Historical closure above is preserved. Status remains In Progress pending the newly added independent-review and final combined gate criterion.
<!-- SECTION:FINAL_SUMMARY:END -->
