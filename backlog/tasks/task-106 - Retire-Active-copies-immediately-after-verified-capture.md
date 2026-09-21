---
id: TASK-106
title: Retire Active copies immediately after verified capture
status: Done
assignee: []
created_date: '2026-09-21 07:53'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 107000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A successful capture removes its Active copy before the next provider read, including partial and interrupted refreshes.
- [x] #2 Freshly verified owned-content matches retire stale Active entries immediately; failed captures keep their retryable copies.
- [x] #3 Regression tests, required checks and live verification pass; changes are committed with a clean working tree.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base 6dd70a4. Work in the isolated checkout, reuse verified capture and cache boundaries, preserve conservative server-deletion handling, and verify the reported message after applying.
<!-- SECTION:PLAN:END -->

## Implementation Notes

- Confirmed on a real archive: a successful capture remained in Active while the source refresh continued because cache retirement was deferred until the account completed without errors.
- Remove the matching disposable entry immediately after capture or a fresh verified owned-content match, and drop it from the pending cache map. Keep conservative deferred handling for server deletions and discarded mail.
- Regressions cover visibility before the next provider read, interruption, unrelated lookup failure, partial listing, and omitted identities. Existing failed-write tests continue to retain retryable cache data.
- The regression tests fail against the previous implementation. Primary-agent review checked durable-save ordering and the distinction between local ownership and server absence; an additional Anthropic review remains unavailable because of its session quota.
- Full pre-push gate passed: 3,787 tests, one expected failure, 96.36% coverage. Deployment waits for the existing download to finish so its checkpoint can advance.
- Applied committed fix 373b214 after the running download finished. Live verification confirmed the reported message is absent from Active results and has no Active reader status; its archived bytes and sidecar are unchanged. Verified that no remaining cached entry matches a verified owned file.
