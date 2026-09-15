---
id: TASK-94
title: Preserve message fonts and body styling when embedding HTML
status: In Progress
assignee: []
created_date: '2026-09-15 03:04'
updated_date: '2026-09-15 03:21'
labels:
  - ui
dependencies: []
priority: high
type: bug
ordinal: 97000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The HTML embedding step drops font stylesheet links that the sanitizer allowed, and discards sanitized body inline styles. A real message consequently uses a fallback font and shows a white canvas below its gray layout. The sanitizer also corrupts font-face family descriptors and CSS-wide font-family keywords by appending generic fallbacks. Preserve supported sender font declarations, trusted font links, and body styling while keeping plain-text rendering and sanitizer boundaries intact.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Allowed font stylesheet links survive the real message route and the authored font loads in browser regression checks.
- [x] #2 Sanitized body inline styling reaches the message container, including its background behind trailing content, without styling the app shell.
- [x] #3 Font-face family descriptors and CSS-wide font-family keywords remain valid; ordinary font-family declarations retain their existing generic fallback.
- [ ] #4 Phone and desktop regressions preserve plain text, message fitting and image blocking, and the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Preserved sanitized font stylesheet links in cascade order and transferred only body style/background metadata to the message container. Kept font-face descriptors and CSS-wide font-family values valid, and refit messages after fonts finish loading. Chromium and WebKit regressions verify actual font loading, trailing background color, shell isolation, and blocked image restoration at phone and desktop widths. A replay of the reported message confirms the authored font and gray footer canvas. Regression checks failed when font/body preservation was removed. Independent review found a quoted CSS URL image-blocking bypass; decoded and safely re-escaped inline attributes, then verified quoted and unquoted backgrounds stay blocked until Load images.
<!-- SECTION:NOTES:END -->
