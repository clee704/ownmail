---
id: TASK-57
title: Repair text contrast regressions caused by message dark styles
status: To Do
assignee: []
created_date: '2026-09-13 06:47'
updated_date: '2026-09-13 07:20'
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
- [ ] #1 Working sender-authored dark designs remain enabled without requiring an appearance toggle or sender-specific exceptions.
- [ ] #2 For normally laid-out text with a verified unchanged opaque background, a severe contrast regression caused by dark styles restores only the affected base foreground colors; existing readable content and explicitly styled links remain intact.
- [ ] #3 Hidden, disabled, decorative and ambiguous content is excluded; uncertain backgrounds and rendering effects do not trigger speculative recoloring.
- [ ] #4 Repairs reset correctly on theme changes and relevant layout/resource changes without modifying archived HTML, refetching remote resources, visible theme flashes, or unbounded repeated scans.
- [ ] #5 Synthetic browser regressions cover the observed failures, working dark styles and conservative exclusions in light/dark app and system themes; the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The proposed manual appearance switch was rejected as poor UX. A blanket fixed-light policy also discards working sender designs. The current recommendation is an automatic, narrowly scoped repair of contrast regressions caused by applying sender dark styles.

Compare the same normally laid-out text before and after dark styles apply, while keeping the app theme unchanged. Qualify only text whose foreground changes, whose known opaque solid background and geometry remain unchanged, and whose contrast drops from clearly readable to nearly invisible. Restore the qualifying foreground from the base appearance; retain the message's working dark backgrounds and other styles. The prototype used base contrast >=4.5:1 and dark contrast <=1.5:1. These are initial engineering thresholds, not a claim that every low-contrast design should be rewritten.

A local browser prototype using the actual message renderer corrected both observed failure types: white text on white panels and pale text in white callouts. Previously working designs were unchanged. In the checked sample, the repair changed only the intended text nodes and no backgrounds; callout links retained their separate colors. Synthetic controls left coordinated dark colors, gradients, shadows, translucent text, clipped preview text, and pre-existing white-on-white text unchanged. This is feasibility evidence from a small selected sample, not broad reliability validation.

Conservative limits are necessary. Ignore hidden/disabled/decorative or offscreen preview content, theme-swapped elements, changing geometry, images, gradients, translucent layers, filters, blending, text shadows/strokes, overlays and other uncertain surfaces. CSS table backgrounds have layers outside the ancestor chain; establish the actual opaque surface rather than assuming the nearest ancestor background always suffices. Restoring a parent's color can affect inherited descendants and currentColor decoration, so verify links and descendants after a repair.

Implementation must compare pristine styles rather than learning prior patches as the baseline, restore prior inline declarations on theme changes, avoid duplicate external resource requests, and reassess after relevant layout/image changes without visible theme flashes or mutation loops. Keep processing bounded for large messages. Existing theme-query rewriting and TASK-56's body selector defect are relevant renderer constraints, not permission to expand this into general CSS repair.

The prototype ran in WebKit 26.5 with remote resources blocked. It has not been integrated into ownmail or verified on a physical iPhone. No archive files were changed. Public regression fixtures must be synthetic and contain no copied message content.

Sources: [computed styles](https://developer.mozilla.org/en-US/docs/Web/API/Window/getComputedStyle), [W3C contrast test and its limitations](https://www.w3.org/WAI/standards-guidelines/act/rules/afw4f7/), [table background layers](https://www.w3.org/TR/CSS2/tables.html#table-layers), [automated contrast limitations](https://dequeuniversity.com/rules/axe/4.12/color-contrast).
<!-- SECTION:NOTES:END -->
