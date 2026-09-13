---
id: TASK-58
title: Prevent message overflow from capturing vertical swipes
status: To Do
assignee: []
created_date: '2026-09-13 06:52'
updated_date: '2026-09-13 06:53'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 61000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An HTML message can move and spring back inside the reader while the subject remains stationary. Ensure vertical swipes scroll the page when messages do not need their own scrolling area.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Normal-width and fitted HTML messages do not create an independent vertical scrolling area, including content with tiny overflow; complete message content remains readable even with authored height or max-height rules.
- [ ] #2 Wide messages remain readable at actual size, with horizontal scrolling and fit controls working after image loading and resizing.
- [ ] #3 Browser regressions cover a synthetic message with tiny overflow, and iPhone touch verification confirms that swipes scroll the page without trapping gestures.
- [ ] #4 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Research complete; implementation remains outstanding. The supplied recording shows message content moving and springing back inside a stationary subject/header before later swipes scroll the page. No reader touch or drag handler cancels scrolling.

The served stylesheet matched the checkout at 56ac9dd. Local inspection of the affected rendered message, with external requests blocked, reproduced 2px of independent vertical overflow in Chromium 145 and WebKit 26.5 at a phone viewport. A footer div forces height:1px while retaining a taller line box around an inline image. Changing only that footer height to auto removes the overflow in both engines. A synthetic long table ending in a 1px div with font-size:13px, line-height:1 and an inline 1px image similarly produces 4px of overflow. The reader can scroll those few pixels while document scroll remains unchanged.

The app enables this through #ownmail-email-content overflow:auto in static/style.css and scaleToFit() in templates/email.html. The fitting script resets overflow on initial layout, image load and resize; normal-width messages retain auto. This supports nested scrolling and iOS rubber-banding as the cause of the recorded symptom. The native touch gesture has not been reproduced under instrumentation, so its exact latching behavior remains unverified.

Proposed scope: avoid independent scroll containers for normal-width and fitted messages while preserving horizontal access in wide actual-size mode. Update both CSS and fitting JS. A browser-only clip plus flow-root experiment eliminates inner scrolling in the synthetic case; preserve float/margin containment and check WebKit text sizing, since the affected page changed height in that experiment. Do not apply it as an untested one-line fix. Existing jsdom fitting tests mock dimensions and cannot verify native gesture behavior.

Reference: https://www.w3.org/TR/css-overflow-3/#valdef-overflow-clip documents that hidden remains a scroll container while clip does not. Keep all regression fixtures synthetic. No runtime files changed during this investigation.
<!-- SECTION:NOTES:END -->
