---
id: TASK-50.1
title: Add the Archive app icon
status: Done
assignee: []
created_date: '2026-09-13 08:47'
updated_date: '2026-09-13 08:51'
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
Use the selected Bauhaus Archive design as the Home Screen icon: a yellow letter, red stamp, and black tray on ivory. Export web icon sizes and connect them to the existing shared page head and manifest.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Shared pages declare an Apple touch icon served as an opaque square PNG.
- [x] #2 The manifest declares reachable PNG icons with sizes matching their image dimensions.
- [x] #3 Icon files are included in built packages and the required repository checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added the selected Archive design as an opaque 180px Apple touch icon and 192px/512px manifest icons. The shared page head declares the touch icon. Verified HTTP responses, PNG dimensions and opacity, and byte-identical inclusion in both wheel and source distribution. Reviewed the 180px preview for readability. All pre-push checks pass: 2,384 tests passed, one expected failure, and 95.55% coverage. Physical iPhone installation remains unverified; theme colors, navigation, connection recovery, and device validation remain in TASK-50.
<!-- SECTION:NOTES:END -->
