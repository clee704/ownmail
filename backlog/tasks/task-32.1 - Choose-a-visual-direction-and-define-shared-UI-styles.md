---
id: TASK-32.1
title: Choose a visual direction and define shared UI styles
status: Done
assignee: []
created_date: '2026-09-12 18:33'
updated_date: '2026-09-12 21:31'
labels:
  - ui
  - ux
dependencies: []
parent_task_id: TASK-32
priority: high
ordinal: 1
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Choose a coherent visual direction for the archive UI before restyling individual pages. TASK-32 records the original design complaints; the current CSS uses a fixed page width, repeated literal colours, separate dark-mode overrides, and emoji controls.

Create two lightweight visual alternatives using synthetic messages: a compact mail-client layout and a calmer reading-focused layout. Compare list, sidebar and message detail at narrow and wide widths. Record the selected direction and rationale, incorporating user feedback when available without claiming an unreviewed choice was approved. Define shared colour, typography, spacing and control styles, including a monochrome SVG icon vocabulary. Existing attachment icons are a starting point. Apply the shared foundations to the app shell, Help, Settings and shared form controls, including their icons. Detailed navigation, result rows and reading layout belong to the following subtasks. Those component tasks finish migrating their styles; the parent closes only after all app UI themes use the shared tokens.

Evidence: ownmail/static/style.css (body, sidebar, result rows and dark-mode section); ownmail/templates/base.html. This task does not choose a framework or add a runtime dependency.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Two comparable visual alternatives show the list, sidebar and message detail with synthetic content; the selected direction and rationale are recorded in the backlog.
- [x] #2 Semantic CSS custom properties define light/dark colours, typography and spacing; the app shell, Help, Settings and shared form controls use them, with remaining component migrations assigned to TASK-32.2 through TASK-32.4.
- [x] #3 A consistent monochrome SVG vocabulary replaces emoji in the app shell, inherits currentColor, and defines the icons needed by the remaining UI tasks.
- [x] #4 The shared foundations are visually checked in light and dark at 390px, 768px and 1440px widths with long labels, long senders and CJK text; synthetic examples and findings are recorded.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Compact approved after comparing synthetic Compact and Calm previews. User requested a denser list and a more polished interface, informed by a survey of established apps. Implementing shared styles first, followed by navigation, list and reader integration; no framework or runtime dependency changes.

Design sources: Linear’s 2026 refresh (https://linear.app/now/behind-the-latest-design-refresh) for quieter navigation, smaller icons and consistent action placement; Things (https://culturedcode.com/things/features/) for text hierarchy and progressive disclosure; Superhuman (https://blog.superhuman.com/improve-productivity-through-design-digital/) for obvious actions. Selected compact interpretation: 36px desktop rows, 13px app text, 12px metadata, 16px reader text, neutral surfaces and one indigo accent. Values are ownmail design choices, not measurements copied from those products. CSS variables now define both themes; authored HTML email keeps its existing light/dark rendering boundary.

The actual templates were visually checked in both themes at 390px, 768px and 1440px using only synthetic messages, including CJK text, long sender/label names and 200 labels. Shared shell, list, reader, Help and Settings styles now use the same tokens. Browser measurements confirm the selected desktop and phone row sizes.

Final validation: pre-commit run -a --hook-stage pre-push passed, including formatting, dependency checks and the full test suite with its coverage gate. Implementation committed in a7d6062.
<!-- SECTION:NOTES:END -->
