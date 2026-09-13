---
id: TASK-58
title: Prevent message overflow from capturing vertical swipes
status: In Progress
assignee: []
created_date: '2026-09-13 06:52'
updated_date: '2026-09-13 20:33'
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
- [x] #1 Normal-width and fitted HTML messages do not create an independent vertical scrolling area, including content with tiny overflow; complete message content remains readable even with authored height or max-height rules.
- [x] #2 Wide messages remain readable at actual size, with horizontal scrolling and fit controls working after image loading and resizing.
- [x] #3 Browser regressions cover a synthetic message with tiny overflow, and iPhone touch verification confirms that swipes scroll the page without trapping gestures.
- [x] #4 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented an application viewport around HTML message content. Normal and fitted messages use page scrolling; actual-size wide messages retain horizontal scrolling and their horizontal position through image loads and resizing. The viewport reserves overflowing content above attachments without changing sender root heights, percentage sizing, margins, floats or flex layouts. Plain-text overflow behavior is unchanged.

Before/after checks on the exact recorded message at five phone, tablet and desktop widths in Chromium 145 and WebKit 26.5 remove its inner vertical scroll range without changing measured text, image or table dimensions or introducing page-level horizontal overflow. External resources were blocked during local checks; private content and recordings remain outside the repository.

Nine synthetic browser regressions pass in both engines. They cover tiny overflow, wide tables/images, fit/actual-size modes, horizontal reachability and position retention, image loading, resizing, fixed/max/percentage heights, complete footer visibility, attachment placement, floats, margins and sender flex layout. Original-code comparisons and targeted mutations verify that the tests detect the regressions. Independent review also checked root margins, borders, box sizing and floated wide content.

Native XCTest swipes on an iPhone 17 Pro simulator running iOS 26.5 reproduce the original capture on the exact message and synthetic narrow fixture. With the fix, the same gestures scroll the page with zero inner vertical offset and range. Wide actual-size horizontal swipes pan the message; subsequent vertical swipes scroll the page while retaining horizontal position. Returning to fit exposes both edges and leaves no inner scroll range. Trusted touchstart/touchmove instrumentation verifies native gesture delivery. Physical-device hardware was not tested.

The full pre-push gate passes with browser tests required. Implementation is ready to commit.
<!-- SECTION:NOTES:END -->
