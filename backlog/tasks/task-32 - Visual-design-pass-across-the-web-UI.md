---
id: TASK-32
title: Visual design pass across the web UI
status: To Do
assignee: []
created_date: '2026-07-31 19:45'
labels:
  - enhancement
dependencies: []
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No task owns the look of the web UI. TASK-5 covers label UX and provider label semantics, TASK-5.1 label navigation — both functional. This is the visual layer, filed after the maintainer called the current styling and iconography poor.

Observed on a real archive, in rough order of how much each costs:

1. Emoji used as system iconography. The sidebar sets every system folder and every label with an emoji, and the attachment rows did the same until they were changed. Emoji are not icons: each platform draws its own, they bring their own colour into a neutral palette, they do not inherit currentColor so they cannot theme, and they sit off the text baseline. A single monochrome inline SVG set that inherits currentColor replaces all of it. The attachment rows already moved this way and can serve as the reference.

2. No type scale or weight hierarchy. In a result row the sender, subject and date share a size and weight, so nothing leads the eye. The subject and its preview run together separated by an en-dash rather than by colour or weight.

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
<!-- AC:END -->
