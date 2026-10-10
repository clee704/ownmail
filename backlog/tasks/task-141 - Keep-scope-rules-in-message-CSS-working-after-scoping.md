---
id: TASK-141
title: Keep @scope rules in message CSS working after scoping
status: To Do
assignee: []
created_date: '2026-10-10 08:12'
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
- [ ] #1 Rules inside a message @scope whose root is confined to the reader container are emitted without the container prefix.
- [ ] #2 The output check accepts those rules and still discards a stylesheet whose @scope rules could match elements outside the container.
- [ ] #3 A synthetic browser test shows a rule inside @scope (.card) applying to the message element, and fails before the fix.
- [ ] #4 Synthetic browser tests show that :scope and & sibling selectors inside @scope cannot style the container's siblings or other application UI, in Chromium and, where installed, WebKit.
- [ ] #5 The full pre-push gate passes with browser tests required.
<!-- AC:END -->
