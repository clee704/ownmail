---
id: TASK-141
title: Keep @scope rules in message CSS working after scoping
status: Done
assignee:
  - '@codex'
created_date: '2026-10-10 08:12'
updated_date: '2026-10-20 04:17'
labels: []
dependencies: []
references:
  - ownmail/sanitizer/worker.js
  - tests/test_sanitizer.py
  - tests/test_reader_body_style.py
priority: low
type: bug
ordinal: 9960
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Message CSS scoping prefixes every rule with #ownmail-email-content, including rules inside @scope, and since TASK-131 it also scopes the @scope root. `@scope (.card) { img { ... } }` therefore becomes `@scope (#ownmail-email-content .card) { #ownmail-email-content img { ... } }`. Selectors inside @scope are relative to the scope root, so the inner rule looks for the container inside `.card` and never matches. In Chromium a declaration in the inner rule computed to its initial value, while the same rule left unprefixed applied. Earlier versions also prefixed inner rules, so this is not a regression. Email rarely uses @scope.

Likely fix: once the @scope root is confined to the container, leave the rules inside it unprefixed, and teach the output check in isScopedStylesheet (ownmail/sanitizer/worker.js) to accept unprefixed rules inside a scoped @scope. A synthetic check found that unprefixed `:scope ~ .t`, `:scope + .t` and `& ~ .t` inside `@scope (#ownmail-email-content)` did not reach the container's siblings in Chromium or WebKit. The output check must still reject anything that does, and the fix must keep the containment that TASK-131 established.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Rules inside a message @scope whose root is confined to the reader container are emitted without the container prefix.
- [x] #2 The output check accepts those rules and still discards a stylesheet whose @scope rules could match elements outside the container.
- [x] #3 A synthetic browser test shows a rule inside @scope (.card) applying to the message element, and fails before the fix.
- [x] #4 Synthetic browser tests show that :scope and & sibling selectors inside @scope cannot style the container's siblings or other application UI, in Chromium and, where installed, WebKit.
- [x] #5 The full pre-push gate passes with browser tests required.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 18d014a. Direct commit to master under the maintainer workflow.
1. Reproduce the scoped @scope mismatch on the Print/PDF path using synthetic messages.
2. Keep descendants of a confined @scope relative to its root, and retain the browser-token output check for containment, including nested scopes.
3. Extend sanitizer checks and Print page browser probes for matching rules and :scope / & sibling containment; verify Chromium and installed WebKit.
4. Review the full task diff, prove regression tests fail with the protected behavior removed, run the full pre-push gate with browser tests required, commit, then close the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-19 scope: TASK-142 moved reader HTML into a sandboxed frame; this task changes the container-scoped sanitizer path used by Print pages and PDF export. Scope is @scope matching and its containment check. Other CSS features, renderer sandbox startup, and reader architecture are out of scope.

2026-10-19 implementation and focused verification:
- Prefix only outer @scope roots; leave their style rules and nested scope roots relative. The browser-token output check tracks confinement through grouping blocks and releases it when the scope closes. Existing rules outside @scope keep their prefixes. Nested-scope behavior follows CSS Cascade 6 sections 2.5.3-2.5.5 (https://www.w3.org/TR/css-cascade-6/#scoped-rules).
- Extend the existing sanitizer cases for root lists, nested/grouped scopes, and string/URL parser mismatches that expose unscoped rules or a scope with an unconfined root.
- Print-page browser probes verify matching inside .card, grouped and nested rules, unchanged elements outside .card, :scope and & adjacent/general sibling selectors, two actual container siblings, and trusted header/attachments. A working inner canary and preserved selector text prevent vacuous containment results.
- Chromium 145.0.7632.6: sanitizer plus Print isolation, 148 passed. WebKit 26.0: all 14 Print isolation cases passed. Both screen and print media are checked. Ruff and diff whitespace checks pass.
- Break-to-fail: original worker fails the new .card matching test (7px instead of 37px). Keeping confinement active after a scope closes fails the new string/URL escape cases. The corrected worker was restored and all 148 focused cases passed again.
- Full diff reviewed against 18d014a; no outstanding findings. Full pre-push gate remains pending.

2026-10-19 final gate: OWNMAIL_REQUIRE_BROWSER_TESTS=1 pre-commit run -a --hook-stage pre-push passed, including the full test suite and coverage gate. All acceptance criteria are verified; implementation commit and task closure follow.

Implementation committed as a486eee on master. Task closure follows after the verified implementation commit; no outstanding findings or acceptance criteria remain.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Restore native @scope matching on Print pages and PDF exports by confining outer roots and preserving relative inner selectors. Browser-token validation retains containment, including parser-mismatch rejection. Verified with 148 focused tests, all 14 Print-isolation probes in Chromium and WebKit, break-to-fail checks, and the full pre-push gate with browser tests required. Implementation: a486eee.
<!-- SECTION:FINAL_SUMMARY:END -->
