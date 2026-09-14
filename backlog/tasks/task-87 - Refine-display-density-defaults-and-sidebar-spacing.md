---
id: TASK-87
title: Refine display density defaults and sidebar spacing
status: Done
assignee: []
created_date: '2026-09-14 08:23'
updated_date: '2026-09-14 08:29'
labels: []
dependencies: []
type: enhancement
ordinal: 91000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make Standard the default density, tighten Standard and Comfortable message rows, and apply the same preference to desktop sidebar folders and labels.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Missing or invalid preferences use Standard; explicit saved choices remain respected.
- [x] #2 Desktop message rows are 36px Compact, 40px Standard, and 48px Comfortable, with sidebar rows at 30px, 34px, and 38px respectively.
- [x] #3 Mobile and tablet spacing remains unchanged; browser checks and the full pre-push gate pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented in ab0875a. Standard is the default in JavaScript, CSS, and Settings. Compact/Standard/Comfortable message rows are 36/40/48px; sidebar folders and labels use 30/34/38px rows in both expanded and collapsed navigation. Label section spacing follows the preference. Saved choices remain respected; the setting is named Display density. Mobile and tablet spacing is unchanged.

All seven density cases pass in Chromium and WebKit. Visual checks pass in both themes at desktop widths, and screenshots were inspected. Mutations restoring the old default or removing sidebar density styles fail their regressions. Independent review found no remaining source issues. The full pre-push gate passes with 2,621 tests passed, one expected failure, and 95.83% coverage.
<!-- SECTION:NOTES:END -->
