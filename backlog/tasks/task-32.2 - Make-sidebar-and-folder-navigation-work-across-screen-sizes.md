---
id: TASK-32.2
title: Make sidebar and folder navigation work across screen sizes
status: To Do
assignee: []
created_date: '2026-09-12 18:33'
labels:
  - ui
  - ux
dependencies:
  - TASK-32.1
parent_task_id: TASK-32
priority: medium
ordinal: 2
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Keep archive destinations reachable and understandable across screen sizes. The current sidebar is fixed at 180px and hidden entirely below the 600px breakpoint. The hamburger offers theme, Settings and Search help, leaving no mobile navigation to labels, system folders or local Trash. Long label names are clipped even on wider screens.

Use TASK-32.1's styles for responsive navigation, visible current location and usable long label lists. Preserve each destination's search meaning and count semantics from doc-9. Server-trash labels and the local bin represent different states; clarify their presentation without merging or hiding destinations to disguise the distinction. Label exclusion, classification and storage repairs remain TASK-19, TASK-26 and TASK-27.

Evidence: ownmail/static/style.css (.ownmail-sidebar and max-width:600px rule); ownmail/templates/base.html; backlog/docs/doc-9.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All Mail, available system roles, user labels and local Trash are reachable at 390px, 768px and 1440px without manually typing a search query.
- [ ] #2 Long labels have a discoverable full name usable by touch and keyboard; a synthetic set of 200 labels remains navigable without displacing message controls.
- [ ] #3 The active destination is visible and exposed programmatically; mobile navigation opens, closes and returns focus predictably.
- [ ] #4 Local Trash and historical server-trash labels remain distinguishable, and navigation keeps existing filter and count semantics; narrow/wide screenshots verify the result.
<!-- AC:END -->
