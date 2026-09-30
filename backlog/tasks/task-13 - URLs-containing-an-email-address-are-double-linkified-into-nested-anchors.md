---
id: TASK-13
title: URLs containing an email address are double-linkified into nested anchors
status: Done
assignee:
  - Ownmail IC1
created_date: '2026-07-24 21:07'
updated_date: '2026-09-30 11:17'
labels: []
dependencies: []
priority: medium
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
_linkify("https://example.com/unsubscribe?email=user@example.com") emits:

    <a href="https://example.com/unsubscribe?email=<a href="mailto:user@example.com" ...>user@example.com</a>" ...>

An anchor nested inside another anchor's href attribute. The link is broken in the rendered message view. Unsubscribe/preference URLs carrying an email parameter are common, so this shows up on real mail.

Cause: the guard in _linkify_line (ownmail/web.py) is

    last_href = preceding.rfind('href="')
    last_close = max(preceding.rfind('>'), preceding.rfind('"'))
    if last_href > last_close: return email_addr   # skip

last_close picks up the opening quote of href=" itself, which always sits after the href= position, so last_href > last_close is never true and the skip never fires.

Not an injection risk: _linkify escapes its input before substituting, so only its own markup is malformed. Note this body path does NOT pass through the DOMPurify sanitizer (_linkify runs after sanitizer.sanitize in web.py), so nothing downstream repairs it.

Fix candidates: linkify emails first then URLs, or do a single combined pass with one alternation regex so matches cannot nest.

tests/test_web.py::TestLinkify::test_email_inside_url_is_not_double_linked is marked xfail(strict=True) and will fail once this is fixed -- remove the marker then.

Found while writing web tests for TASK-3.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 HTTP(S) URLs containing email addresses produce exactly one complete URL anchor with unchanged href and display text, without nested or embedded mailto anchors.
- [x] #2 Standalone email linking, existing URL/email regex meanings and flags, HTML escaping, link attributes, and quote/header rendering retain their behavior.
- [x] #3 The former strict-xfail becomes a passing regression, synthetic plaintext-reader coverage verifies the complete link, and failing-before/passing-after evidence plus required repository validation are recorded.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Claim TASK-13 on isolated branch fix/linkify-email-containing-urls from clean tested review base dbe5bf90e9966b3e11ac02d582af5666db927e89. Record explicit criteria and commit this task-only plan with normal hooks before code/tests; retain the same review base across checkpoints.
2. Limit production edits to _linkify_line. Treat each original URL_RE match as one atomic span, and apply EMAIL_RE only to the original escaped text outside those spans. Keep both regex definitions/flags, HTML escaping, HTTP(S)/mailto link attributes and surrounding quote/header rendering unchanged. Remove the obsolete generated-href guard rather than adding another markup parser.
3. Convert the existing strict xfail in TestLinkify into a real regression asserting exactly one complete URL anchor, intact href and display text, no nested anchors or embedded mailto links. Cover query/path/fragment addresses, standalone email addresses beside multiple URLs, uppercase HTTP(S), escaped punctuation and quoted/header lines within existing test families. Prove an actual synthetic plaintext reader route preserves the complete link without invoking the sanitizer.
4. Preserve a failing baseline against the original helper, then run focused and retained web/linkifying tests, Ruff check/format-check, deptry and author review. Use fresh Astra Ultra review support for the bounded diff when useful.
5. Coordinate the required browser-only interval after TASK-99, then run the complete mandatory-browser pre-push gate with private runtime state, unchanged coverage floor/timeouts/assertions and the existing observer/maxfail=1. Record only verified ACs and clean local commits with normal hooks; no integration/publication or unrelated changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read-only preflight verified this next recorded task (doc-4 row 19, no dependencies) on dbe5bf90e9966b3e11ac02d582af5666db927e89. Source and independent Astra Ultra probes confirm that the email replacement pass rewrites generated URL attributes and display text; the current guard cannot detect its own opening href quote. Synthetic query/path/fragment cases reproduce the corruption, including quoted/header lines. An actual plaintext reader request returns HTTP 200 but no anchor with the expected complete URL, while an adjacent standalone email remains correctly linked. The existing strict-xfail encodes the known failure. The manager authorized this bounded fix while preserving existing URL/email regex meanings, escaping and link attributes. Scope is only _linkify_line, existing TestLinkify/necessary quote-header and plaintext reader regressions in tests/test_web.py, and this ledger. No new URL recognition policy, sanitizer/provider/progress/template/JavaScript changes, dependency/schema changes, real mail/config/credentials or external service operations are in scope. TASK-99 retains the next browser interval; blocked TASK-37/95/125 remain paused.

Task-only acceptance/plan checkpoint de9e5b85e33a62b34cf7e31c1e5cb3c33a6a62b3 preceded all implementation and test edits. _linkify_line now uses captured original URL spans and applies the existing email regex only to intervening original text, removing the ineffective generated-href guard. Both regex definitions/flags and all escaping/link attributes remain unchanged; no production code outside the helper changed. The former strict xfail now asserts a single complete URL anchor with exact href/text and attributes for query, path, fragment and case variants. Existing tests also cover adjacent standalone emails, multiple URLs, escaped markup, quote/header wrappers and the actual plaintext reader route. Ten cases failed against the original helper; all 19 focused cases and all 389 retained web/config tests now pass without xfails. Ruff check, format-check, deptry and whitespace checks passed. Author review and independent Astra Ultra review found no correctness findings or blocking test gaps; additional isolated probes verified 19 unchanged-behavior and 12 atomic-URL cases. All inputs and message files were synthetic. At implementation checkpoint df7adfd0e849787b8f95319a2c75a252aea95a63, the required pre-push gate was still pending the browser-only interval after TASK-99; AC3 and task completion correctly remained open.

After TASK-99 released Chromium, the complete required pre-commit run -a --hook-stage pre-push --verbose passed on clean reviewed implementation checkpoint df7adfd0e849787b8f95319a2c75a252aea95a63: 3996 tests passed in 190.93 seconds, with no skips or xfails, and branch-inclusive coverage was 96.57% against the unchanged 95% floor. All file-hygiene, Ruff and deptry hooks passed. Mandatory headless browser coverage used private synthetic fixtures and profiles with the existing runtime-only lifecycle observer and maxfail=1; all 13 probe launches returned zero and recorded clean Chromium exits, with a maximum probe duration of 0.670 seconds. No test selection, assertion, timeout or coverage threshold was weakened. The aggregate process exited zero before the browser interval was released. Local validation used Python 3.14.6; the supported-Python CI matrix remains a later integration check. Closure changes only this ledger; product and test files remain those of the tested implementation checkpoint. No integration, publication, real mail/config/credential operations or next task were performed.

Next action: hand off the clean completed branch and validation evidence to the manager for separately coordinated integration; no further task implementation is authorized in this handoff.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed email-bearing HTTP(S) URLs by linking complete original URL spans atomically and applying the existing email regex only outside those spans. Preserved regex behavior, HTML escaping, link attributes, standalone emails and quote/header rendering. Converted the strict xfail into exact passing anchor regressions and verified a synthetic plaintext reader. Ten red baseline failures became 19 focused passes; 389 retained tests and the complete 3996-test mandatory-browser gate passed, with 96.57% branch-inclusive coverage. Author and independent Astra Ultra reviews found no issues. Local branch only; integration and publication remain separately coordinated.
<!-- SECTION:FINAL_SUMMARY:END -->
