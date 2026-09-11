---
id: TASK-39
title: Preserve UTF-8 bodies with hidden preview padding
status: Done
assignee: []
created_date: '2026-09-11 10:43'
updated_date: '2026-09-11 10:45'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Correctly declared UTF-8 HTML can begin with dense hidden preview padding made of U+2007 FIGURE SPACE and U+034F COMBINING GRAPHEME JOINER. The readability validators reject these characters, fall back to Latin-1, and corrupt visible bullets and dashes. Confirmed against a real archive; the original message bytes are valid UTF-8.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 HTML body decoding preserves UTF-8 preview padding and visible Unicode punctuation.
- [x] #2 Indexing and web rendering use consistent validation for these padding characters.
- [x] #3 A synthetic regression fails before the fix and passes afterward; full pre-push checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The shared parser readability validator now accepts figure spaces and combining grapheme joiners used in hidden preview padding. The web decoder reuses it, removing the duplicate validator. Both synthetic regressions failed before the fix, then passed. Read-only validation against the original message confirms exact UTF-8 preservation in both decoding paths and correct punctuation through the detail route with the real sanitizer. Full pre-push checks passed, including ruff, deptry, and the complete test suite with the 95% coverage gate. Independent review found no actionable regressions. Broader charset fallback limitations are tracked in TASK-40.
<!-- SECTION:NOTES:END -->
