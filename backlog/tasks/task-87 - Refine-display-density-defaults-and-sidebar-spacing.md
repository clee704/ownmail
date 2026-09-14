---
id: TASK-87
title: Refine display density defaults and sidebar spacing
status: In Progress
assignee: []
created_date: '2026-09-14 08:23'
updated_date: '2026-09-14 08:26'
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
- [ ] #3 Mobile and tablet spacing remains unchanged; browser checks and the full pre-push gate pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Follow-up to TASK-86. Keep the existing browser preference key and density values; label the setting Display density to include sidebar spacing.

Standard is now the JavaScript, stylesheet, and Settings default. Desktop message heights are 36/40/48px and sidebar heights are 30/34/38px for Compact/Standard/Comfortable. Label section spacing follows the same choice. Explicit minimum heights keep collapsed navigation consistent with expanded navigation. Both browsers passed desktop layout checks in both themes; screenshots were inspected.

All seven density cases pass in Chromium and WebKit, including expanded/collapsed sidebar rows and unchanged mobile drawers. Mutations restoring the Comfortable default or removing sidebar density styles fail the intended checks. Full test suite passed 2,621 tests with one expected failure and 95.83% coverage; rerun pre-push after final test edits to clear its concurrent-file-change detection.
<!-- SECTION:NOTES:END -->
