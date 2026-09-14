---
id: TASK-86
title: Configure desktop message list density
status: Done
assignee: []
created_date: '2026-09-14 08:09'
updated_date: '2026-09-14 08:19'
labels: []
dependencies: []
type: enhancement
ordinal: 90000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add a browser preference for desktop message row spacing so readers can choose a roomier list or retain a compact view.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Settings offers Comfortable, Standard, and Compact density choices with a comfortable default and a browser-persisted selection.
- [x] #2 Search and Trash reflect the selected desktop density without clipping content or breaking row selection.
- [x] #3 Mobile list spacing remains unchanged and invalid stored preferences fall back safely.
- [x] #4 Browser regression checks and the full pre-push gate pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implement as a browser appearance preference alongside theme. Use the existing shared message list and responsive CSS; no archive or database changes.

Implemented Comfortable (52px), Standard (44px), and Compact (36px, the previous desktop spacing), with Comfortable as the default. Density applies above 900px and is restored before first paint, on history restoration, and after changes in another tab. Chromium preference tests pass; visual checks across both themes and five widths confirm spacing, sender alignment, and no horizontal overflow.

Seven Chromium regression cases pass, covering defaults, persistence, Search/Trash selection, unchanged mobile spacing, cached-page restoration, and cross-tab updates. In-memory mutations removing the density CSS or pageshow listener each fail the intended regression. Independent review found no implementation defects. Full pre-push hooks passed with browser tests required.

Implemented in b5a349b. All seven density regression cases also pass in WebKit using the matching browser build. The full pre-push gate and commit hooks pass.
<!-- SECTION:NOTES:END -->
