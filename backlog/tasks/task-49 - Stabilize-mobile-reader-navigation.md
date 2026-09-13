---
id: TASK-49
title: Stabilize mobile reader navigation
status: In Progress
assignee: []
created_date: '2026-09-13 04:43'
updated_date: '2026-09-13 05:06'
labels: []
dependencies: []
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Stabilize the mobile reader toolbar while returning to results. Hide the approved mobile branding row and keep Back, Trash, and More in one top row.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Returning to results keeps the mobile reader toolbar stable until navigation.
- [x] #2 Back preserves the result URL, list scroll position, and focus.
- [x] #3 The agreed mobile reader header layout keeps message actions and metadata accessible, without changing the desktop layout.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened after the brief Back glitch persisted. In an iOS 26.4 Home Screen simulator installation without a manifest, opening a reader displayed Safari View Controller with its own top and bottom controls. A fresh installation using the new manifest keeps list and reader navigation in the same standalone view. The manifest declares root scope, a stable app ID, the search launch URL, and configured branding. Existing Home Screen installations should be re-added from Safari to pick up the new configuration.

Also removed automatic search focus, which reopened the iOS keyboard accessory bar on return and stole focus from the restored row. List restoration now runs when the DOM is ready, retaining pageshow for cached documents. A controlled delayed-resource comparison measured the old first frame at scroll zero before settling at the saved position; the fixed first frame already matched that position. Loading feedback waits 200 ms, avoiding the brief overlay recorded on fast navigation while retaining feedback for slow loads.

Verified list-to-reader-to-Back in the fresh iOS simulator installation, restored row focus without keyboard chrome, and the controlled first-frame comparison. Focused regression tests and mutation checks cover root scope, DOM-ready restoration, cached-page restoration, and delayed-overlay cancellation. The full pre-push checks pass. Physical-device confirmation remains useful; the original no-manifest scope heuristic is not assumed to be specified behavior.

Apple documents that out-of-scope links open in Safari View Controller: https://developer.apple.com/videos/play/wwdc2023/10120/
<!-- SECTION:NOTES:END -->
