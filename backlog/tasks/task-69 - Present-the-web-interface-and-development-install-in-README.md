---
id: TASK-69
title: Present the web interface and development install in README
status: Done
assignee: []
created_date: '2026-09-13 20:10'
updated_date: '2026-09-13 20:23'
labels: []
dependencies: []
priority: medium
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Restructure the README around browser-based archive use. Distinguish the current development version from the older PyPI release, preserve useful setup and maintenance instructions in linked guides, and correct misleading claims. Screenshots and a demo site are deferred.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README leads with implemented desktop and mobile web capabilities and a browser-first quick start.
- [x] #2 Development and PyPI installation paths are explicitly distinguished and development install/update commands are verified.
- [x] #3 Detailed setup and archive maintenance remain accessible through valid links; privacy and prerequisite claims match current behavior.
- [x] #4 Documentation checks and the full pre-push gate pass; changes are committed with no screenshots or release publication.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
README now leads with implemented browser features and separates the moving GitHub development installation from PyPI 0.3.0, whose web extra is required for Flask. Verified fresh GitHub installation, same-version pipx reinstall, CLI help/version, and bundled UI assets in an isolated temporary environment. Setup and archive maintenance are preserved in linked guides. Screenshots, demo hosting, and release publication remain deferred.

Independent documentation review confirmed provider, storage, browser, and link claims. Fifteen local links and anchors pass. Remote-image blocking retains some active image sources; the README and setup guide now state that limitation, with implementation repair filed separately. The shared-tree pre-push run overlapped concurrent reader edits and reported three reader failures, so final validation uses an isolated snapshot of committed source plus this documentation change.

The isolated full pre-push gate passed against committed source revision 90ffac4: lint, formatting, dependency checks, 2,418 tests passed, one expected failure, no skips, and 95.55% branch-inclusive coverage. Browser tests were required. TASK-72 tracks the confirmed remote-image blocking gap.

Documentation changes were committed in b2876c8 after verification. Screenshots, demo hosting, and release publication are deferred.
<!-- SECTION:NOTES:END -->
