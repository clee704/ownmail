---
id: TASK-38
title: Thread-aware server cleanup — retain copies while a thread is active
status: Done
assignee: []
created_date: '2026-08-06 19:51'
updated_date: '2026-09-15 04:09'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
priority: medium
ordinal: 8
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement thread protection for server cleanup under
[Ownership philosophy](../../docs/philosophy.md). This supersedes the capture
deferral settled in TASK-33 on 2026-08-06.

Archive eligible messages immediately, including sent replies in ongoing
conversations. Keep their server copies available to mail clients while any
message in the thread remains in Inbox or unfinished outgoing state. Once the
thread clears, TASK-14.2 may clean up verified archived copies.

Trash and Spam members do not keep a thread active. A candidate that itself
returns to Inbox or unfinished outgoing state is protected even if it was
archived earlier. Uncertain thread membership or an incomplete view postpones
cleanup; it must not delay archival or alter the archived contents and labels.

A thread left active indefinitely retains its server copies indefinitely. There
is no age limit or override in this task. A later reply protects copies still
present, without restoring copies already removed.

Reuse existing provider enumeration and thread identity support where possible.
Use provider thread identifiers when available; validate the plain IMAP approach
against its available headers and identity guarantees. Do not assume that a
partial header match proves a thread is inactive. Thread identifiers and
lookups must remain scoped to the source and account; capture filters must
not hide Active members from the protection check. Enumeration failures must
remain distinguishable from an empty result.

Expose enough freshness and completeness information for TASK-14.2 to
revalidate protection before mutation as far as each provider supports. Test
new active members and role changes after the initial scan, including between
cleanup batches. Document provider limits instead of promising an atomic
check where none exists.

Build and verify this protection before enabling TASK-14.2 cleanup. The old
evidence gate for implementing capture deferral no longer applies: preserving
live client conversations is part of the cleanup design. This task changes no
server data by itself; TASK-14.2 retains its existing approval requirements.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An eligible message is captured immediately even when its thread contains Inbox or unfinished outgoing mail
- [x] #2 Server cleanup is held while the candidate or any thread member is Active, and becomes eligible after the thread clears
- [x] #3 Trash and Spam thread members do not hold cleanup; sent and filed messages use the same protection rule
- [x] #4 Incomplete or uncertain server/thread state skips cleanup, with provider-specific tests including plain IMAP
- [x] #5 Archived contents and labels remain unchanged when the server copy becomes Active again
- [x] #6 Configuration documentation explains that a thread left Active retains its server copies indefinitely, while eligible messages still enter the archive
- [x] #7 A later reply protects server copies still present and does not restore previously removed copies
- [x] #8 Thread checks remain scoped to the source and account and include Active members regardless of capture filters; failed enumeration cannot establish an empty or inactive thread
- [x] #9 Provider-specific tests introduce new Active members and role changes after enumeration; supported revalidation updates protection before cleanup, and remaining provider race limits are documented
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement a fresh read-only provider thread-protection check, scoped by source/account and message identity. Gmail API checks current candidate and full thread state independently of capture filters; incomplete or unknown unfinished state holds cleanup. IMAP remains held where complete account-wide membership cannot be established. Add provider and archive integration tests for activity changes, immediate capture, and frozen ownership; document provider limits and repeat checks before future cleanup mutations. No server mutation, OAuth, schema, or archive-file movement changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-90 is complete. TASK-28 awaits explicit approval of the external Active-cache schema and disposable cache file replacement. Continuing TASK-38 under the documented workstream fallback. Public Gmail API docs do not establish a reliable Scheduled-mail state; treat unfinished state as unknown where it cannot be established, and do not present an Inbox/Draft-only check as complete protection.

Partial implementation checkpoint: Gmail reads current candidate and thread state without capture filters; the base provider holds unsupported IMAP checks. Synthetic archive integration passes for Sent and filed candidates: capture proceeds while a sibling is Active, and later server activity preserves owned bytes and labels. Blocking AC #2: current public provider contracts do not prove finished state for all filed/received Gmail members (Scheduled differs from Draft), and IMAP does not establish complete account-wide thread visibility. The implementation holds those cases instead of claiming full cleanup eligibility. Next action: establish supported provider evidence for those states or obtain an explicit scope decision on unavailable cleanup paths; keep TASK-38 open and TASK-14.2 dependent. Continue the independent TASK-5.4 after a reviewed, committed checkpoint.

Reviewed partial checkpoint against 4deb404. Provider regression suite and archive integration pass; checks cover read-only queries, source/account isolation, fresh activity changes, malformed and failed requests, Ctrl-C propagation, and unsupported IMAP state. Two isolated mutations (ignoring Active protection and ignoring unknown finished state) were rejected by the tests. Known candidate activity survives a failed thread read. Sent copies with otherwise unknown labels require a fresh user-label catalog entry; unknown system labels remain held. Review raised a hypothetical Scheduled-member omission but found no reproducing evidence; completeness follows the documented Thread.messages member-list contract, with unfinished-state limits still recorded above. ACs #2, #3, and #9 remain open for broader clearance and cleanup integration. Full repository checks will run before the session ends.

Checkpoint commit: b18454c. Final pre-commit run -a --hook-stage pre-push passed with OWNMAIL_REQUIRE_BROWSER_TESTS=1; total branch coverage 95.97%. Remaining ACs #2, #3, and #9 are not waived. No cleanup mutation is enabled; resume from the provider-evidence blocker above.

The authorized observed-state policy removes the former blanket Sent-only blocker. Gmail now applies the same protection rule to ordinary filed and Sent members; current Inbox/Draft activity holds, Trash/Spam members do not hold, and unrecognized system state or failed reads retain protection. The task contract explicitly permits incomplete-state holds: Gmail IMAP and standard IMAP remain unavailable for cleanup clearance because account-wide thread membership cannot be established. This documents the existing required hold behavior and does not authorize server cleanup or OAuth changes. Focused provider and capture tests pass. Final provider revalidation acceptance and the integrated gate remain pending; actual cleanup sweep and mutation integration belongs to TASK-14.2.

Final read-only acceptance evidence extends the existing freshness regression across successive Sent and filed candidates: newly arriving Inbox or Draft activity after enumeration protects the next candidate, and filing the new reply permits fresh clearance. Both cases reject a deliberately stale observation. All 85 focused thread/capture tests pass. Complete now explicitly means known membership and interpretable reported state, not an atomic or hidden-state guarantee. All TASK-38 criteria are verified for the provider capabilities and required unknown-state holds; full checks and commit remain pending. TASK-14.2 still owns actual sweep revalidation, mutation integration, and its separate sign-off.

Completed in 8657a68 on master. All nine acceptance criteria now have provider/capture evidence, including current Sent and filed clearance, new Inbox/Draft activity between successive candidates, role changes after enumeration, unknown-state holds, and scoped identity. The final integrated suite passed 3,153 tests with one existing expected failure and 96.12% branch coverage. Gmail API observations can clear protection; both IMAP paths retain the task-required unavailable-state hold. Actual cleanup, its sweep/mutation tests, and OAuth authorization remain TASK-14.2 and have not been enabled.
<!-- SECTION:NOTES:END -->
