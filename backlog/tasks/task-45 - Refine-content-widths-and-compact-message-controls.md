---
id: TASK-45
title: Refine content widths and compact message controls
status: In Progress
assignee: []
created_date: '2026-09-13 03:12'
updated_date: '2026-09-13 03:28'
labels:
  - ui
  - ux
dependencies:
  - TASK-32
priority: medium
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Apply feedback from the compact UI review: limit desktop workspace and reading widths, size the sender column to its content within a compact cap, move Original and Download into the message menu, and reduce mobile padding. Preserve search, selection, reading navigation and authored message behavior.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Desktop list and message content have bounded widths, and sender tracks avoid expanding with the viewport or exceeding the useful content width.
- [x] #2 Back, subject and More share the message heading; Original and Download remain available with their existing destinations inside More.
- [x] #3 Mobile header, list and reader spacing are reduced while touch controls and long content remain usable without page-level horizontal overflow.
- [ ] #4 Browser checks cover wide desktop and mobile layouts, both themes and reader menu interaction; required repository validation passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The desktop workspace now caps at 1280px, with a 216px sidebar and an 800px reader. Plain text uses a 70ch measure; authored HTML retains its fit/actual-size behavior. Sender tracks fit the displayed names up to 180px using shared CSS grid tracks, with a compact fallback for browsers without subgrid. Browser measurements verified that a short synthetic sender uses its actual text width rather than a viewport percentage. A resize handle was omitted because automatic sizing addresses the reported excess space without adding another interaction.

Original and Download now appear inside More; Back, subject and More share the heading. Menu link activation closes the disclosure and returns focus without canceling navigation. Mobile header height is 84px, list rows are 52px, and reader side padding is 8px; coarse-pointer control sizing remains intact.

Browser checks covered light/dark layouts at 390px, 768px, 1440px and 1920px, plus a long-subject reader at 320px. No page-level horizontal overflow was observed. Wide authored HTML remains horizontally scrollable inside the reader at actual size. Selection, explicit return and menu keyboard behavior were checked. Independent review identified the Download menu-dismissal issue, which was fixed and protected by a mutation-checked regression. Full repository validation is pending.
<!-- SECTION:NOTES:END -->
