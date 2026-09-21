---
id: TASK-107
title: Decode HTML entities in message previews
status: Done
assignee: []
created_date: '2026-09-21 08:21'
updated_date: '2026-09-21 08:25'
labels: []
dependencies: []
type: bug
ordinal: 108000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Search previews can display literal character references such as &#8199; when the snippet contains no HTML tags. Decode entities once before whitespace and invisible-padding cleanup, while retaining template escaping.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Tag-free previews decode numeric and named entities and normalize padding.
- [x] #2 HTML parsing and regex fallback decode entities once and keep encoded markup safe in rendered search results.
- [x] #3 Regression tests fail before the fix and the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added one-pass entity decoding to tag-free snippets and the HTML regex fallback. Existing lxml parsing continues to decode once. Regression coverage verifies numeric/named whitespace, invisible padding, literal encoded markup, and safe rendering in Active search. Six regression cases failed against the original implementation.

Verified the corrected live search response. Web tests passed (326 passed, one existing expected failure), followed by the full pre-push gate including the coverage requirement. The fix changes display cleanup only; no reindex is needed.
<!-- SECTION:NOTES:END -->
