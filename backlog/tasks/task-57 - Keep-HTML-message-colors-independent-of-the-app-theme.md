---
id: TASK-57
title: Keep HTML message colors independent of the app theme
status: To Do
assignee: []
created_date: '2026-09-13 06:47'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An HTML email can become unreadable when ownmail activates sender dark-mode rules that change text without a matching background. Keep HTML message rendering independent of app appearance and preserve the sender's base design.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Changing the app or system theme leaves HTML message colors stable, including authored light and dark designs, inherited text and links.
- [ ] #2 Theme-dependent CSS uses a fixed light preference without losing nested, combined, negated or alternative conditions, HTML media attributes, or responsive layout rules.
- [ ] #3 Plain-text messages continue following the app theme, and HTML image controls, sizing and style scoping continue working.
- [ ] #4 Synthetic browser regressions verify readable foreground/background pairs in both app and system themes; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Research supports a fixed light preference for HTML messages, independent of the app theme. Preserve authored foreground/background colors, including permanently dark designs; keep plain text themed. The current updateEmailDarkMode function actively unwraps sender dark media rules, and the supports-dark heuristic allows app color inheritance. App link rules also reach HTML content.

Recommended scope: remove automatic message theme synchronization, establish stable HTML defaults, exclude message content from app color rules, and normalize color-scheme conditions in the existing PostCSS sanitizer. Preserve conjunctions, negation, comma alternatives, nesting, HTML media attributes and responsive conditions. Do not assume that deleting every media block mentioning dark is correct. The existing qualified-body-selector defect remains TASK-56.

A plain light container does not suppress document media queries in browser experiments. A light iframe isolates document styles and worked in controlled Chromium 145 and WebKit 26.5 checks, but requires image-control, sizing and sandbox changes. These checks do not verify a deployed iPhone. WebKit documents version-dependent iframe color-scheme behavior; avoid relying on it alone for the initial fix.

Sources: [CSS color adjustment](https://drafts.csswg.org/css-color-adjust-1/), [media-query semantics](https://www.w3.org/TR/mediaqueries-5/), [WebKit iframe support](https://bugs.webkit.org/show_bug.cgi?id=284973). [Outlook](https://support.microsoft.com/en-us/outlook/mail/dark-mode-in-outlook) and [Apple Mail](https://support.apple.com/guide/mail/change-viewing-settings-cpmlprefview/mac) document independent light message backgrounds. Research only; implementation and acceptance checks remain outstanding.
<!-- SECTION:NOTES:END -->
