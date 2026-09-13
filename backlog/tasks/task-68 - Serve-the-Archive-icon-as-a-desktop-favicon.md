---
id: TASK-68
title: Serve the Archive icon as a desktop favicon
status: Done
assignee: []
created_date: '2026-09-13 20:09'
updated_date: '2026-09-13 20:12'
labels:
  - ui
dependencies: []
type: bug
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The page declares only a 192px app PNG as its favicon, and /favicon.ico returns 404. Serve the existing Archive artwork at desktop favicon sizes and update browser icon links.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Shared pages and the Original-message view link a reachable favicon containing 16px, 32px, and 48px images.
- [x] #2 The conventional /favicon.ico URL serves the same artwork, and built packages include it.
- [x] #3 Required repository checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added a 16/32/48px ICO exported from the existing SVG with rsvg-convert and packed using the Python standard library. Shared pages and the Original-message view use /favicon.ico?v=2; the unversioned root URL also serves it with an explicit ICO MIME type. The existing PNG was confirmed reachable before this change, so the original desktop failure remains unconfirmed; this adds standard desktop sizes and a new icon URL. Regression checks failed before the change and pass after it. An independent review verified the exact ICO bytes in freshly built wheel and source distributions. Live HTTP checks confirm the updated HTML and ICO are served. Browser UI confirmation remains unverified.

The full pre-push gate passes, including lint, dependency checks, and the complete test suite with its coverage gate.
<!-- SECTION:NOTES:END -->
