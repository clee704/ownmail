---
id: TASK-93
title: Recognize HTML layouts beyond inline root backgrounds
status: To Do
assignee: []
created_date: '2026-09-15 02:56'
labels:
  - ui
dependencies: []
priority: medium
type: bug
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The padding detector still misses sender backgrounds supplied by scoped CSS classes or nested beyond the first wrapper child. Synthetic cases include a class-styled root canvas, a background table under multiple div wrappers, and a background applied only to a table cell. Recognize these authored layouts without removing readable padding from simple HTML or changing sender markup. Body attribute extraction remains tracked in TASK-56.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Synthetic class-styled and nested layout canvases render without a second reader frame in both themes.
- [ ] #2 Simple HTML retains readable padding, including messages with decorative or hidden background elements.
- [ ] #3 Browser checks exercise the real sanitizer at phone and desktop widths and fail against the previous behavior.
<!-- AC:END -->
