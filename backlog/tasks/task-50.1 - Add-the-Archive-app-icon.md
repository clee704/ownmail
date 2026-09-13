---
id: TASK-50.1
title: Add the Archive app icon
status: Done
assignee: []
created_date: '2026-09-13 08:47'
updated_date: '2026-09-13 09:28'
labels:
  - ui
  - mobile
dependencies: []
parent_task_id: TASK-50
type: enhancement
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Use the selected Bauhaus Archive design as the Home Screen and website icon: a yellow letter, red stamp, and black tray on ivory. Export web icon sizes and connect them to the shared page head and manifest.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Shared pages declare an Apple touch icon served as an opaque square PNG.
- [x] #2 The manifest declares reachable PNG icons with sizes matching their image dimensions.
- [x] #3 Icon files are included in built packages and the required repository checks pass.
- [x] #4 Shared pages declare the Archive PNG as their browser tab icon.
- [x] #5 The Archive symbol is slightly larger and its artwork uses flat fills without shading, bevels, or embossed edges.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The Archive icon has a flat SVG source at ownmail/static/icon.svg. Its letter, stamp, and tray preserve the selected proportions at 112% scale around the center. Solid fills use ivory #f4f0e6, gold #edb928, red #d83a26, and black #191919. There are no gradients, filters, shadows, or bevels. Exported opaque 180px, 192px, and 512px PNGs with rsvg-convert, without adding a runtime dependency.

Shared pages declare the Apple touch icon and browser tab icon; the Original-message view also declares the browser icon. Both manifest icons and all HTML icon links use ?v=2. Existing app identity, launch URL, and scope are unchanged.

Verified uniform interior pixels, opacity, dimensions, enlarged bounds, HTTP responses, and exact asset inclusion in wheel and source distribution. Reviewed 512px and 60px renders. All pre-push checks pass. New physical iPhone installation remains unverified; installed Home Screen apps may need to be added again, and system-applied outer highlights are separate from the artwork. Other Home Screen behavior remains in TASK-50.
<!-- SECTION:NOTES:END -->
