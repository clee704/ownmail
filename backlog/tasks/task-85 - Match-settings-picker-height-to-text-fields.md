---
id: TASK-85
title: Match settings picker height to text fields
status: Done
assignee: []
created_date: '2026-09-14 07:43'
updated_date: '2026-09-14 07:50'
labels: []
dependencies: []
type: bug
ordinal: 89000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The desktop timezone picker renders shorter than adjacent text fields in Safari. Give settings selects consistent sizing while preserving native selection behavior and mobile touch targets.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Desktop settings selects match text-field height in WebKit and Chromium in both themes.
- [x] #2 Mobile controls retain their existing height and selection and focus behavior work.
- [x] #3 Full pre-push checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
WebKit rendered the standalone timezone select at 21px, compared with 33.5px text fields; the download select reached 31.5px through flex stretching. An explicit settings-select height now matches the text-field line box, padding, and borders. The existing mobile override remains 44px. Chromium and WebKit passed all eight combinations of desktop/phone width and light/dark theme, including selection, form values, focus borders, native appearance, and page overflow. Inspected both desktop themes. The unrelated repository-governance task remains In Progress.

Implementation committed in 2f1c3ec. Full pre-push checks passed with browser tests required; the suite passed 2,614 tests with one expected failure and 95.83% coverage.
<!-- SECTION:NOTES:END -->
