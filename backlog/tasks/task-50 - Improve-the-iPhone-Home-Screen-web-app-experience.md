---
id: TASK-50
title: Improve the iPhone Home Screen web app experience
status: In Progress
assignee:
  - Ownmail audit IC4
created_date: '2026-09-13 04:50'
updated_date: '2026-09-30 19:47'
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

TASK-49, TASK-51, TASK-52, and TASK-53 cover most navigation and resume behavior; physical-device confirmation remains. TASK-49 added a minimal manifest with root navigation scope and configured branding, prevented automatic search focus on return, and improved list restoration and loading feedback. Its standalone navigation was verified in an iPhone simulator. TASK-50.1 adds the Archive app icon through Apple touch and manifest declarations. The reviewed code checkpoint adds theme colors, app-managed reading-position recovery and in-page connection recovery. Actual iPhone validation remains open, including the unavailable-cold-launch boundary described below.

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

The branch was reconciled with completed master 625aa4258d7ab738bd597f5155e00e9700bc3b6d using a non-rewriting merge; the original reviewed candidate remains preserved. Implemented theme metadata using the existing light/dark palette, one session-only reader identity/version/vertical-offset checkpoint, and a reader-only unavailable-message view with a validated local return. Shared action and label loading now bound fetch plus JSON waits to 30 seconds and suppress late success; Retry is an explicit safe navigation/reload, never a replayed mutation. Native page loading has a cancellable 30-second deadline and the latest destination owns Retry. No mail bodies, attachments, service worker, HTTPS setup, network/security setting or private source state were added or changed. README distinguishes loaded-page recovery from the browser error screen on an unavailable cold launch and documents trusted HTTPS plus a future static-only fallback boundary.

Verification checkpoint: original metadata/action-timeout/unavailable-reader regressions produced 8 red cases; missing reading restoration/cleanup produced 2 red with 15 controls; native navigation recovery produced 3 red; a self-review caught and corrected stale Retry destinations with another red/green case. Four private-source safety mutations were caught (stale version, uncancelled navigation deadline, unsafe POST retry destination and JSON outside the deadline). Focused synthetic Flask/JSDOM checks pass; actual-browser restoration/Retry and retained browser/CSP/navigation checks are prepared but await the exclusive browser lease, independent review and mandatory pre-push gate. Original task acceptance criteria remain unchanged and unchecked. Actual iPhone Home Screen cold launch, background/resume, keyboard, cutout/orientation and connection checks with an iOS version remain required; no emulation is claimed as that evidence. Next action is focused independent review and the browser-leased gate, then an honest open device-validation checkpoint.

Independent focused review found one introduced P2: message-action finally cleanup called hideLoading and cancelled a newer native-navigation deadline, including successful Trash starting Back to results. A call-site survey confirmed message actions do not start the native loading spinner; they own feedback and disabled controls only. The minimal correction removes that single cross-owner cleanup call, preserving native lifecycle/Escape/deadline cleanup. Five new regressions reproduce the original issue for successful Trash, older success/failure/timeout interleavings, and repeated explicit actions; all five were red before correction and all 54 affected synthetic checks now pass. Existing cleanup-spy assertions now verify that actions leave native loading alone; original loading timing and subprocess limits remain unchanged.

Browser evidence: 26 affected reader/navigation/label/CSP cases passed on the original checkpoint. The unchanged real 30-second native deadline and explicit GET Retry passed in a separate synthetic browser probe. After the correction, the actual trusted Trash button, held Back destination, 30-second failure, discarded late response and successful explicit Retry passed, with exactly one POST. An earlier synthetic-clock diagnostic exceeded its existing harness timeout and established no product result; its evidence was preserved, and the real-time probe used the existing 45-second reader harness without changing the application deadline or existing assertions. The first mandatory full pre-push gate completed normally and passed before correction. The corrected checkpoint still needs the same reviewer's narrow recheck and the required full gate; actual iPhone acceptance criteria remain open.

Reviewed code checkpoint complete; task remains In Progress. The same independent reviewer approved exact d6fe017b27728a19451c8c94b9289e6b9ce1e9b2 after all 13 narrow recheck cases passed, including the unchanged original P2 reproductions. The corrected mandatory pre-push gate passed: 4,411 test cases plus 370 subtests, zero failures/errors/skips, 96.60% branch-inclusive coverage, with unchanged requirements. All 161 observed browser subprocesses exited successfully and the private-profile process check was clear; the browser lease is released. The final progress checkpoint changes only this ledger; production code and tests remain byte-for-byte equivalent to the reviewed/tested d6fe017 tree. Local integration preserves the prior clean master and all existing branch/evidence history.

All original acceptance criteria remain unchecked pending the physical-iPhone evidence needed to evaluate the complete task. Next action: on an already authorized reachable server with synthetic messages, record the tested build, iPhone model and iOS version, then check (1) Home Screen install/name/icon/theme/scope and cold launch, (2) query/sort/page/scroll/focus through list-message-Back, (3) long-message background/resume/reload plus stale or missing message recovery, (4) keyboard and portrait/landscape cutout/home-indicator usability, (5) interrupted navigation/action and explicit Retry without mutation replay, and (6) unavailable cold-launch behavior. No emulation substitutes for these checks. This checkpoint does not authorize HTTPS/public service setup, device permissions, private-mail caching or a new offline/security policy.
<!-- SECTION:NOTES:END -->
