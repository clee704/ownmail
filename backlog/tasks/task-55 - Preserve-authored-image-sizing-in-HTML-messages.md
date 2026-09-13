---
id: TASK-55
title: Preserve authored image sizing in HTML messages
status: In Progress
assignee: []
created_date: '2026-09-13 06:30'
updated_date: '2026-09-13 06:34'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The global border-box reset applies inside HTML messages. Images with explicit dimensions and padding lose content width, distorting their aspect ratio. Keep the app reset outside authored message content.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Images inside HTML messages use the sender or browser box-sizing rules; padded images preserve their authored content dimensions.
- [x] #2 The app shell and message wrapper retain border-box sizing, and explicit sender border-box rules remain effective.
- [x] #3 Verify mobile and desktop rendering, reproduce the failure without the fix, and pass the full pre-push checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed against a real archive; the running server used the same stylesheet. The reset now excludes descendants of the message container and keeps zero selector specificity. WebKit checks at 390px and 1440px reproduced the squeezed image with the old reset and preserved content dimensions with the fix, including proportional fit-to-width zoom and explicit sender border-box styling. The regression compares reader and standalone computed styles; restoring the universal reset makes it fail. Independent review found no issues. Full pre-push checks passed.
<!-- SECTION:NOTES:END -->
