---
id: TASK-119
title: Keep message style blocks that contain HTML-like text
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-29 06:39'
updated_date: '2026-09-30 11:29'
labels:
  - ui
dependencies: []
priority: medium
type: bug
ordinal: 19500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The sanitizer worker drops a message's whole style block in two cases. When the block wraps its rules in HTML comment markers (<!-- ... -->), a legacy convention some mail generators still emit, PostCSS fails to parse the closing --> and the worker replaces the stylesheet with /* CSS parse error */. Chromium applies the same rules. When the CSS text contains < followed by a letter, / or ! that PostCSS does not escape, as in a comment such as /* reset <p> margins */ or a content string, DOMPurify's markup probe removes the style element. Both cases reproduce with synthetic messages on DOMPurify 3.3.1 with PostCSS 8.5.6 and on DOMPurify 3.4.16 with PostCSS 8.5.28. PostCSS 8.5.28 escapes only <style, </style and <!-- as \3c in its output, so those sequences no longer trigger the probe. Keep the authored rules in both cases without letting style text close the style element.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A synthetic message whose style rules are wrapped in <!-- --> keeps its scoped rules after sanitization
- [x] #2 A synthetic message whose CSS comments or strings contain markup-like text keeps its scoped rules, and no style text can close the style element
- [ ] #3 The full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve exact review base 62875a5c627e9d1d964a945c2176507c4e93b58e on isolated branch fix/message-style-text. Commit this task-only claim and plan before changing product code or tests. Completed worktrees stay preserved.
2. Establish failing regressions through the actual Node worker for genuine outer HTML-comment CSS wrappers and markup-like comments/strings, retaining a plain scoped-stylesheet control. Add synthetic reader fixtures for CSS/string semantics and style-closing injection attempts; no real mail or network operations.
3. Limit production changes to sanitizer/worker.js CSS parsing/serialization and the existing style hook. Preserve DOMPurify protections, selector scoping, declaration/import filtering, source-map suppression, string/escape meaning and CSS operators. Do not change sanitizer settings, dependencies, versions, installation/lifecycle code, web.py, templates or body-selector behavior. If safe preservation cannot be achieved in this scope, pause and escalate rather than bypass a protection.
4. Extend existing tests/test_sanitizer.py and tests/test_reader_body_style.py, with all assertions covering reachable behavior. Check real worker output, reparsed DOM and rendered CSS, including mixed-case style-closing attempts, scoped styling, escaped strings, unchanged app shell and preserved filtering. Keep Chromium idle until TASK-13 releases it; focused private Node/static checks may proceed.
5. Run focused checks, repository Ruff check/format-check and deptry, author self-review against the original base, and a fresh independent Astra Ultra correctness/security review. Resolve findings, run the full required pre-push gate with mandatory private browser coverage and unchanged thresholds/assertions, then close all verified criteria with normal hooks and a clean branch. No denied TASK-37/95/125 work, main changes, merge/rebase, publication, real mailbox/credential operations or security-setting changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC2. Branch: fix/message-style-text. Review base: 62875a5c627e9d1d964a945c2176507c4e93b58e. TASK-119 is next after TASK-13 in execution order, unassigned with no dependencies before this claim. The approved read-only premise ran the actual installed worker on synthetic inputs: a plain stylesheet retained its scoped rule, a genuine HTML-comment wrapper became CSS parse error, and markup-like text in a CSS comment or content string removed the whole style element. Body text survived. The relevant source is independent of TASK-13 linkification, TASK-56 body-selector relationships and denied TASK-37/95/125 actions. Owned paths are ownmail/sanitizer/worker.js, tests/test_sanitizer.py, tests/test_reader_body_style.py and this task record only. No new dependency or STOP-category change is planned. Existing DOMPurify markup/breakout checks remain enabled; preservation must not rely on disabling them or restoring raw styles after sanitization. Fresh independent Astra Ultra security/correctness review is required by the manager. TASK-13 currently owns Chromium. Next action: commit this supported claim/plan checkpoint before implementation.

Implemented token-aware stylesheet preparation before PostCSS serialization. Genuine outer HTML-comment markers are removed only outside strings/comments; literal less-than characters in CSS strings/comments are serialized safely while preserving escape parity and CSS meaning. Existing DOMPurify protections, selector scoping, declaration/import filters, source-map suppression and dependency versions remain unchanged.

Regression evidence: the actual original worker failed 14 new subtests; the six new route/browser cases all failed against a private original-worker copy and pass with the change. All 103 sanitizer tests and all 10 reader-body-style browser cases pass. Rendered fixtures compare original CSS in an isolated reference against sanitized computed content, borders and range-query widths, and verify outside-scope controls and absence of injected DOM/events. Ruff check, Ruff format-check and deptry pass. The first development check caught missing map:false on the additional PostCSS Input; this was corrected and the existing/extended source-map guard now passes. Author self-review against the original base found the diff confined to the approved worker/tests/task scope. Independent Astra Ultra security/correctness review is in progress; full pre-push coverage remains pending. No main integration or publication performed.
<!-- SECTION:NOTES:END -->
