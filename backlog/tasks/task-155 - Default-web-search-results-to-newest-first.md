---
id: TASK-155
title: Default web search results to newest first
status: Done
assignee: []
created_date: '2026-10-24 17:33'
updated_date: '2026-10-24 17:36'
labels: []
dependencies: []
type: bug
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Text searches currently default to relevance. Use newest first for web searches when the sort is omitted or invalid, while preserving explicit sort choices and their pagination links.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Web text searches without a sort use date_desc and select Newest first.
- [x] #2 Invalid sort values fall back to date_desc.
- [x] #3 Explicit relevance and date sorts remain selected across pagination; relevance without search terms falls back to date_desc.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The web sort default and invalid-sort fallback now use date_desc. Explicit relevance remains available for text searches, and filter-only relevance requests still use date_desc. The default-order and invalid-sort regressions both failed against the previous implementation; all 22 focused route and sort-menu checks pass. Full pre-push checks pass, including the complete suite and coverage gate.

Implemented and committed in 440bd28.
<!-- SECTION:NOTES:END -->
