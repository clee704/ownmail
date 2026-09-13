---
id: TASK-51
title: Prevent flashes after returning to the message list
status: Done
assignee: []
created_date: '2026-09-13 05:14'
updated_date: '2026-09-13 05:43'
labels:
  - ui
  - mobile
dependencies: []
priority: medium
type: bug
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An intermittent visual flash occurs after the message list appears when returning from a reader in the iPhone Home Screen app. The earlier reader-toolbar navigation glitch is confirmed fixed. Investigate destination-page restoration and loading state without changing the agreed layout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Returning from a message renders the list without a delayed visual reset.
- [x] #2 List position and keyboard return focus remain correct.
- [x] #3 The reproduced cause has a regression check and required repository checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reproduced on the synthetic preview by delaying only the external result-state script: the returned list painted at scrollY 0 around 30 ms, then restored scrollY about 800 ms later when that deferred script arrived. The loading overlay remained inactive. DOMContentLoaded restoration still waits for deferred script delivery. Move restoration into the rendered page after list and shell layout initialization, retaining one-time state consumption and browser-history fallback.

Implemented a shared inline template at the end of the page, after the list footer and shell initialization. The same delayed-resource experiment now restores at the first measured frame (about 29 ms), with no later position change; verified mid-list and bottom-of-list positions. An iOS 26.4 Home Screen simulator trace also restores focus during parsing, before load/pageshow. The rendered-page regression fails the former external-script implementation and a DOMContentLoaded-delay mutation. All reader and shell tests plus the full pre-push gate pass. Temporary preview instrumentation was removed. Physical-device confirmation of the intermittent symptom remains useful.

Committed as eaca55b. A separate missing message-row loading-feedback issue is tracked in TASK-52.

Follow-up: the intermittent flash is still reported after the inline restoration change. Confirmed the active development server serves the new inline script and no external restoration script. The delayed-resource reproduction is fixed, but it is not sufficient evidence that the reported symptom is resolved. Reopened pending classification of the remaining visual change and a matching reproduction.

The supplied recording identifies the remaining path: an iPhone native swipe Back reveals the cached list at its prior position, then jumps upward after the swipe finishes. The earlier reproduction exercised the toolbar Back link instead. Investigate browser-history restoration separately. Pointer-return focus styling is tracked in TASK-53.

Matched the recording in iOS 26.4 standalone with native history Back: a pointer row click focuses the main ancestor because it has tabindex=-1. On return, the trace shows the saved list position followed by a jump to the main offset. Removing only that tabindex in a controlled preview preserves the saved position after native restoration; no history mode or scroll timing change was needed. Verified Skip to content followed by Tab enters the main controls using native keyboard events.

Removed the permanent focusable main container while preserving its native skip-link fragment target. The focus regression fails the prior markup. Native iPhone history Back now settles at the saved list position without the subsequent main-offset jump; native keyboard Skip to content still moves subsequent Tab navigation into the main controls. All 16 shell tests and the full pre-push gate pass. Both active servers serve the corrected markup, and temporary instrumentation was removed.

Committed as 43486c9. Existing cached lists must be reloaded once to use the corrected focus behavior.
<!-- SECTION:NOTES:END -->
