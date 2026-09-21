---
id: TASK-105
title: Hide Active details and report message freshness accurately
status: Done
assignee: []
created_date: '2026-09-21 07:28'
labels: []
dependencies: []
priority: high
ordinal: 106000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Remove Active/check-time text from message list rows. Hide reader Active details until a kebab-menu action opens them. Diagnose widespread incomplete warnings and show specific per-message freshness instead of treating unrelated source failures as unconfirmed message state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Message list rows contain no Active freshness line and retain valid attachment accessibility references.
- [x] #2 Reader Active details appear only after selecting a kebab-menu item, with accessible close behavior.
- [x] #3 Freshness distinguishes current confirmed messages, unknown lifecycle state, stale observations and account-level refresh problems; live warning causes are investigated and addressed where in scope.
- [x] #4 Relevant UI and state tests, required checks, review and clean committed delivery are complete.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base f471ad7. Use existing menu/panel patterns. Diagnose live status with aggregate metadata and read-only provider observations. Work in an isolated checkout before applying to the running server.
<!-- SECTION:PLAN:END -->

## Implementation Notes

- Removed the list freshness line and its obsolete layout/accessibility references. Reader status opens through Message status in the kebab menu; Close and Escape restore focus.
- Per-message freshness uses its own observation and scope. Account refresh errors remain available separately. Unknown lifecycle state stays unconfirmed.
- Confirmed on a real archive: ordinary non-junk IMAP keywords were mistaken for unknown lifecycle state, and empty mailboxes returning no SEARCH payload made enumeration incomplete. Recognize established non-junk markers and accept missing search data only after successful selection reported zero messages. Nonempty mailbox failures remain errors.
- One Gmail source also returned temporary HTTP 429 errors; a subsequent read-only enumeration succeeded. No account settings or retry policy changed.
- Focused tests and a real Chromium interaction check pass. Mutation checks reject broken message freshness, keyword classification and empty-folder handling.
- Full gate initially found one integration assertion that still required the removed list text; updated it to the requested behavior. Final pre-push gate passed: 3,785 tests, one expected failure, 96.34% coverage.
- A patched read-only IMAP enumeration completed successfully against a real server.
- Primary-agent code review completed. An additional Anthropic review is unavailable because its session quota is exhausted; no independent review is claimed.
- Committed implementation in a8d6fb1 and verified the running server: list freshness removed, reader status hidden behind its menu action. Resumed the download with the updated code; the full live refresh remains an operator run, not an acceptance requirement.
