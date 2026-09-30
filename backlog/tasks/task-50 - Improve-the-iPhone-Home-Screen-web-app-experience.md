---
id: TASK-50
title: Improve the iPhone Home Screen web app experience
status: In Progress
assignee:
  - Ownmail audit IC4
created_date: '2026-09-13 04:50'
updated_date: '2026-09-30 18:57'
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
priority: low
type: enhancement
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make ownmail reliable and comfortable when launched from the iPhone Home Screen. Prioritize navigation, resuming after backgrounding, and validation on an actual iPhone, then complete installation metadata and connection recovery.

TASK-49, TASK-51, TASK-52, and TASK-53 cover most navigation and resume behavior; physical-device confirmation remains. TASK-49 added a minimal manifest with root navigation scope and configured branding, prevented automatic search focus on return, and improved list restoration and loading feedback. Its standalone navigation was verified in an iPhone simulator. TASK-50.1 adds the Archive app icon through Apple touch and manifest declarations. Remaining work includes theme colors, app-managed reading-position recovery, connection recovery, and physical-device checks.

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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pinned code/review base is reviewed combined candidate ca2911c883ba7b0a178b22f4faac694a322360af while its final gate runs. This is the explicitly authorized code slice of TASK50; retain every original acceptance criterion and keep all actual-iPhone requirements open. 1. Add manifest/app theme colors from the existing light/dark palette; reuse theme preference application before paint and on resume/preference changes. 2. Extend existing session-scoped result state to save only the selected local message identity/version and scroll position on lifecycle boundaries. Restore the same valid reader conservatively without overriding native history restoration, anchors or user movement; do not redirect a list launch into old mail or store message contents. Give missing reader pages a usable local return view and clear stale saved positions. 3. Reuse the action feedback area for explicit Retry navigation/reload. Bound message-action and label-loading requests including response-body waits; clear loading/disabled states on failure and suppress late success. Do not automatically replay mutations. Give held native page navigation a bounded stop/retry path without changing successful fast navigation. 4. Add focused synthetic metadata, preference, reading-state, unavailable-message and connection recovery regressions, including red/green and meaningful safety mutations. Retain navigation/focus, CSP/untrusted-email, desktop and keyboard controls. Browser checks require the actual exclusive browser lease; no native/device actions are included. 5. Document the trusted HTTPS prerequisite and a future static-only offline fallback boundary; do not install a service worker, cache private mail, expose services or alter network/security settings. Reconcile forthcoming clean main, obtain independent focused review, run normal hooks and the mandatory full gate, then preserve a clean honest In Progress checkpoint until the physical-iPhone criteria are actually checked with an iOS version.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise inspected against the execution order and exact task: manifest/root scope/icons and most list navigation already exist in completed TASK49/50.1/51/52/53. Missing code includes theme colors, app-managed message reading-position recovery, bounded unresolved requests and explicit recovery controls. Preserve the prior verified navigation fixes; do not redesign the shell or infer a cutout defect merely from the default viewport. Source ownership is base.html/email.html plus a reader-only unavailable template; app-preferences.js, app-shell.js, result-state.js, message-actions.js and label-editor.js; narrow shared feedback styles; web.py manifest and view_email hunks; relevant tests/docs and TASK50. Frozen PDF/export and JSON-reader implementation remain unchanged. Physical iPhone Home Screen checks, any device access and a trusted deployed HTTPS origin are not implied by the code authorization. No acceptance criterion is marked complete from emulation or existing partial evidence.
<!-- SECTION:NOTES:END -->
