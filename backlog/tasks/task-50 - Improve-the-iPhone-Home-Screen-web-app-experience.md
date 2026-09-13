---
id: TASK-50
title: Improve the iPhone Home Screen web app experience
status: To Do
assignee: []
created_date: '2026-09-13 04:50'
updated_date: '2026-09-13 05:06'
labels:
  - ui
  - mobile
dependencies: []
references:
  - ownmail/templates/base.html
  - ownmail/static/result-state.js
  - ownmail/static/message-actions.js
  - >-
    https://webkit.org/blog/17333/webkit-features-in-safari-26-0/#every-site-can-be-a-web-app-on-ios-and-ipados
  - 'https://webkit.org/blog/7929/designing-websites-for-iphone-x/'
  - 'https://www.w3.org/TR/service-workers/#secure-context'
priority: medium
type: enhancement
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make ownmail reliable and comfortable when launched from the iPhone Home Screen. Prioritize navigation, resuming after backgrounding, and validation on an actual iPhone, then complete installation metadata and connection recovery.

TASK-49 added a minimal manifest with root navigation scope and configured branding, prevented automatic search focus on return, and improved list restoration and loading feedback. Its standalone navigation was verified in an iPhone simulator. Remaining work includes app icons and theme colors, app-managed reading-position recovery, connection recovery, and physical-device checks.

Implement this incrementally in the existing Flask UI. A cached offline fallback depends on a trusted HTTPS origin over LAN; record that dependency before selecting a service-worker strategy. Full offline mail storage is a separate product decision.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 List-to-message-to-list navigation preserves the search, sort, page, scroll position, and focused message without toolbar jumps or disruptive intermediate layouts.
- [ ] #2 Backgrounding and reopening preserve the current view and reading position where valid; stale or missing messages recover to a usable view.
- [ ] #3 Controls and content remain usable around the status bar, home indicator, keyboard, and landscape cutout; desktop and keyboard navigation still work.
- [ ] #4 Installation has a manifest, app icons, name, launch URL, navigation scope, and theme colors, verified from the iPhone Home Screen.
- [ ] #5 Connection loss and an unavailable server produce recoverable feedback with Retry; loading states terminate and failed actions never appear successful. Document the HTTPS prerequisite and intended scope for a cached offline fallback.
- [ ] #6 Record actual iPhone Home Screen checks for cold launch, Back, long-message scrolling, background/resume, keyboard use, portrait/landscape, and connection recovery, including the tested iOS version. Add focused regression coverage for changed navigation and recovery behavior.
<!-- AC:END -->
