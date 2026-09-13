---
id: TASK-59
title: Improve mobile text size and spacing
status: Done
assignee: []
created_date: '2026-09-13 07:09'
updated_date: '2026-09-13 07:16'
labels:
  - ui
  - mobile
dependencies: []
references:
  - ownmail/static/style.css
priority: medium
type: enhancement
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Increase mobile UI text size and spacing for comfortable reading and tapping in the phone Home Screen app. Keep the adjustment within the existing responsive styles.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Phone message lists use larger text and more vertical separation without sender, subject, or date overlap.
- [x] #2 Mobile reader controls, navigation, settings, and help have comfortable spacing while authored HTML message layouts remain intact.
- [x] #3 Verify narrow phone layouts, both themes, and unchanged desktop styling; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Mobile styles now use 15px primary text, 13px secondary text, 69px message rows, and 44px controls. The fixed header and its reserved space both grow to 96px. Reader margins increase to 16px and plain text to 17px; authored HTML keeps its own font sizes and conditional padding. Changes remain within the existing 600px breakpoint. WebKit required an explicit settings select height in addition to min-height. Independent CSS review found no remaining issue.

Synthetic pages rendered through Flask and the real sanitizer passed 224 Chromium/WebKit checks across 320, 375, 390, 430, 600, 768, and 1440px in both themes. Checks cover list alignment, selection toolbar, navigation, settings fields, reader metadata and menus, page overflow, and authored HTML. All 64 tablet/desktop measurements match the original stylesheet. Another 16 checks passed with subgrid disabled. The original stylesheet failed all 160 phone readability checks. Phone screenshots were inspected; physical iPhone Home Screen validation remains part of TASK-50.

The full pre-push gate passed, including lint, dependency checks, and the complete test suite with its coverage gate.

Implementation committed in the preceding fix commit.
<!-- SECTION:NOTES:END -->
