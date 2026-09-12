---
id: TASK-32
title: Visual design pass across the web UI
status: To Do
assignee: []
created_date: '2026-07-31 19:45'
updated_date: '2026-09-12 18:35'
labels:
  - enhancement
  - ui
  - ux
dependencies: []
priority: medium
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Umbrella for the web UI redesign and usability improvements. TASK-5 covers label semantics and editing; this task owns visual consistency, responsive layout, reading navigation and interaction quality. It was split into six implementation tasks on 2026-09-12 following renewed feedback that the current UI needs improvement.

Observed on a real archive, in rough order of how much each costs:

1. Emoji used as system iconography. The sidebar sets every system folder and every label with an emoji, and the attachment rows did the same until they were changed. Emoji are not icons: each platform draws its own, they bring their own colour into a neutral palette, they do not inherit currentColor so they cannot theme, and they sit off the text baseline. A single monochrome inline SVG set that inherits currentColor replaces all of it. The attachment rows already moved this way and can serve as the reference.

2. No type scale or weight hierarchy. Sender and subject share the body typography; the date is smaller, but the row still lacks a clear hierarchy. The subject and preview share a single clipped line, and their hierarchy needs improvement.

3. Fixed narrow columns truncate constantly. Sender names and label names both clip mid-word at widths that do not respond to the viewport, on a page with a lot of unused horizontal space.

4. Spacing rhythm is inconsistent between regions — the sidebar is tight where the result rows are loose, and there is no shared spacing scale behind either.

5. The sidebar mixes system folders and labels with only a small caps heading between them, and shows two separate Trash entries.

6. Colour is carried almost entirely by one blue button; there is no defined palette, and no semantic roles for surface, border, muted text and accent, so dark mode is maintained as a list of per-rule overrides.

Worth deciding before any of it: whether the target is a restrained system-native look or something with its own identity, and whether to introduce CSS custom properties for the palette and spacing so light and dark stop being two parallel rule sets. Both answers change how much of style.css is touched.

Not in scope: which labels are shown at all. Raw provider labels (CATEGORY_*, IMPORTANT) and malformed label values crowding the sidebar are TASK-19 and TASK-27.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision recorded on visual direction and on whether the palette and spacing move to CSS custom properties
- [ ] #2 Emoji removed as iconography, replaced by a monochrome SVG set that inherits currentColor
- [ ] #3 A type scale and spacing scale applied across search results, sidebar and message detail
- [ ] #4 Sender and label columns stop truncating at fixed widths on wide viewports
- [ ] #5 Light and dark both derive from the same tokens rather than parallel rule sets
- [ ] #6 Folder and label navigation remains available on narrow screens, with the active destination visible.
- [ ] #7 Message reading provides an explicit return to the originating query, sort and page, restoring list position in the same tab.
- [ ] #8 Controls have meaningful accessible names, visible focus and predictable keyboard/menu behavior.
- [ ] #9 Empty views and pending, successful and failed message actions provide clear, accessible feedback.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Split into TASK-32.1 through TASK-32.6 on 2026-09-12 after source inspection and a browser review using synthetic list/detail content. No personal archive was opened.

Suggested sequence: visual direction and shared styles (32.1), responsive navigation (32.2), list/search layout (32.3), message reading (32.4). Accessibility (32.5) and empty/action states (32.6) can proceed independently. Detailed sequencing is recorded in doc-4; this work remains unscheduled relative to the existing milestones.

Original acceptance criteria remain open: 32.1 owns the design direction, shared styles and shell icons; 32.2-32.4 apply them across components. The added criteria cover the newly explicit usability gaps. Filing these tasks does not complete the redesign.

Related work remains separate: TASK-5.4 local label editing; TASK-6 conversation view; TASK-28 active messages; TASK-19/26/27 label filtering and correctness. Preserve the distinction between local Trash and server-trash labels described in doc-9. A specific visual direction has not yet been selected.
<!-- SECTION:NOTES:END -->
