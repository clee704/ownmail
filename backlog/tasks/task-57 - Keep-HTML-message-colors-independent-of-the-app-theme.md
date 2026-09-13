---
id: TASK-57
title: Repair text contrast regressions caused by message dark styles
status: In Progress
assignee: []
created_date: '2026-09-13 06:47'
updated_date: '2026-09-13 19:08'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Detect when sender dark styles make previously readable text nearly invisible on an unchanged solid background, and automatically restore only the affected base text colors while preserving working dark designs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Working sender-authored dark designs remain enabled without requiring an appearance toggle or sender-specific exceptions.
- [x] #2 For normally laid-out text with a verified unchanged opaque background, a severe contrast regression caused by dark styles restores only the affected base foreground colors; existing readable content and explicitly styled links remain intact.
- [x] #3 Hidden, disabled, decorative and ambiguous content is excluded; uncertain backgrounds and rendering effects do not trigger speculative recoloring.
- [x] #4 Repairs reset correctly on theme changes and relevant layout/resource changes without modifying archived HTML, refetching remote resources, visible theme flashes, or unbounded repeated scans.
- [x] #5 Synthetic browser regressions cover the observed failures, working dark styles and conservative exclusions in light/dark app and system themes; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The renderer compares native dark text with its base foreground in the same synchronous browser task. It repairs only text whose contrast falls from at least 4.5:1 to at most 1.5:1 on the same opaque solid surface with unchanged geometry. Temporary spans restore qualifying text colors while preserving original elements, links and currentColor decoration. Repairs roll back if sender selectors change existing paint or layout.

Pristine styles are retained in a WeakMap. Theme changes remove prior repairs; image, font and layout changes schedule a debounced reassessment. Style-load events are excluded to prevent repeated probing. Traversal is bounded at 2,500 elements and 1,500 nonempty text nodes. Hidden, disabled, clipped, animated, translucent, shadowed and other ambiguous content remains unchanged. Table-column layers and overlapping painted siblings are treated conservatively. Messages with CSS resource references or lazy images skip baseline probing to avoid additional asset requests.

Integrated browser checks against a real archive corrected both observed failure types, including nested transparent layout tables, while preserving the checked working dark designs, backgrounds and geometry. This is a selected sample, not broad reliability validation. No archive files changed. Physical iPhone rendering was not checked.

All 32 synthetic browser regressions pass in WebKit and Chromium. Tests cover repaired headings and callouts, working dark designs, descendant colors, currentColor decoration, conservative exclusions, theme resets, image and resize changes, resource requests and bounded processing. Deliberately weakening the contrast threshold or unchanged-background requirement makes the relevant regression fail. The positive regression also failed before implementation.

Independent review identified shadow, sibling-background and wrapper-selector side effects. The fixes were verified against the original reproductions. The full suite passed with 2,416 tests, one expected failure and 95.55% coverage. Browser tests are required in the Python 3.12 CI job; Playwright is a development dependency only.

Existing media-query rewriting and TASK-56 body-selector behavior remain outside this task. Separate sanitizer dependency audit findings are tracked in TASK-67.

References: [computed styles](https://developer.mozilla.org/en-US/docs/Web/API/Window/getComputedStyle), [W3C contrast test limitations](https://www.w3.org/WAI/standards-guidelines/act/rules/afw4f7/), [table background layers](https://www.w3.org/TR/CSS2/tables.html#table-layers).
<!-- SECTION:NOTES:END -->
