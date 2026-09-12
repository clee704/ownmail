---
id: TASK-32
title: Visual design pass across the web UI
status: Done
assignee: []
created_date: '2026-07-31 19:45'
updated_date: '2026-09-12 21:31'
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
- [x] #1 A decision recorded on visual direction and on whether the palette and spacing move to CSS custom properties
- [x] #2 Emoji removed as iconography, replaced by a monochrome SVG set that inherits currentColor
- [x] #3 A type scale and spacing scale applied across search results, sidebar and message detail
- [x] #4 Sender and label columns stop truncating at fixed widths on wide viewports
- [x] #5 Light and dark both derive from the same tokens rather than parallel rule sets
- [x] #6 Folder and label navigation remains available on narrow screens, with the active destination visible.
- [x] #7 Message reading provides an explicit return to the originating query, sort and page, restoring list position in the same tab.
- [x] #8 Controls have meaningful accessible names, visible focus and predictable keyboard/menu behavior.
- [x] #9 Empty views and pending, successful and failed message actions provide clear, accessible feedback.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Compact was approved after two synthetic visual alternatives; the requested denser implementation is complete across TASK-32.1 through TASK-32.6. Shared light/dark tokens, monochrome SVG icons, responsive navigation, dense result rows, reader return navigation, accessible controls and action feedback replace the previous presentation. The actual app was checked with synthetic content in both themes at 390px, 768px and 1440px; no personal archive was opened. Detailed evidence and reference links are recorded in the subtasks. Independent code reviews found no verified introduced issues in layout/navigation, action requests or wide-message fitting. Final validation: pre-commit run -a --hook-stage pre-push passed, including formatting, dependency checks and the full test suite with its coverage gate. Implementation committed in a7d6062.

Related work remains separate: TASK-5.4 label editing; TASK-6 conversation view; TASK-28 active messages; TASK-19/26/27 label filtering and correctness. Local Trash remains distinct from historical server-trash labels. TASK-44 records an existing trusted-sender persistence error-reporting problem discovered during review.
<!-- SECTION:NOTES:END -->
