---
id: TASK-99
title: Expose post-scan progress during live downloads
status: To Do
assignee: []
created_date: '2026-09-21 04:08'
labels: []
dependencies: []
references:
  - ownmail/live_sync.py
  - ownmail/static/downloads.js
priority: medium
type: bug
ordinal: 101000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A web-triggered download can look stalled after live enumeration even while the worker continues checking and refreshing messages. The refreshing UI omits skipped counts, and live_sync does not advance progress for discarded messages or final cached-message reconciliation. Sequential provider reads can therefore leave visible counters unchanged for extended periods. LiveLookupError also collapses underlying provider failures into a generic active_refresh reason, which prevents operators from distinguishing slow work from request failures. Make post-scan work and safe failure categories observable while preserving lifecycle safety.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Terminal and web progress remain useful throughout owned-message skips, discarded-message checks, active refresh, capture, and final reconciliation, without unbounded output or private message details.
- [ ] #2 The web view includes ongoing skipped or processed work rather than showing only archive, Active, and failure totals during refreshing.
- [ ] #3 Recognized provider timeout and connection failures retain safe diagnostic categories through live lookup wrapping; unknown failures remain generic and retryable.
- [ ] #4 Synthetic regressions reproduce unchanged visible counters while work advances, cover silent reconciliation paths and safe error classification, and pass the full pre-push gate.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed against a real archive running after TASK-97: successive worker reports and the web status endpoint showed advancing counters and transitions between sources. Native sampling showed SSL reads during a quiet interval; it does not identify the exact IMAP command or prove a permanent network stall. No running process was interrupted. Code inspection locates the hidden skipped count in ownmail/static/downloads.js and unreported work and generic LiveLookupError handling in ownmail/live_sync.py. The underlying causes of the observed earlier message failures remain unverified.
<!-- SECTION:NOTES:END -->
