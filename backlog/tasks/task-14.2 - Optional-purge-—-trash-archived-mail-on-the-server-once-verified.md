---
id: TASK-14.2
title: Optional purge — trash archived mail on the server once verified
status: In Progress
assignee: []
created_date: '2026-07-25 05:39'
updated_date: '2026-09-20 15:33'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
  - TASK-28
  - TASK-38
  - TASK-90
parent_task_id: TASK-14
priority: high
ordinal: 9
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement optional server cleanup under
[Ownership philosophy](../../docs/philosophy.md). This retains TASK-14's
verification, dry-run, resumability, and provider-specific deletion safeguards.
Server cleanup deletes user mail and may require wider OAuth scopes: obtain
explicit sign-off before implementation and land through a PR under the
repository's existing rules.

Cleanup moves a server copy to the provider's Trash only when all of these hold:

- Ownmail owns a complete archive copy, with a fresh content-hash check of
  its local `.eml` and readable, durable metadata for the required labels.
  Incomplete capture, an Active cache, local Trash, and expired or deleted
  local copies cannot qualify. Required label retrieval must have succeeded;
  TASK-90 closes the current failure-to-empty-labels path.
- The current server candidate demonstrably corresponds to that owned copy
  within the correct source and account. A stored provider ID or Message-ID
  alone is insufficient where the provider cannot guarantee its identity.
- Current server state shows the message is outside Inbox, unfinished outgoing
  state, Trash, and Spam. Earlier capture does not override present activity.
- The thread is no longer Active, as verified by TASK-38. Unknown or incomplete
  state postpones cleanup.

Cleanup sweeps previously captured messages as well as this run's captures.
Reading current server roles for these checks never changes the archived copy
or its labels. Sent and filed mail follow the same rules: either may be archived
immediately while its server copy stays available during a live conversation.

Plain IMAP identity checks must handle folder moves, UIDVALIDITY changes,
reused UIDs, and duplicate Message-IDs. Use content correspondence where stable
provider identity cannot establish the match; skip uncertain candidates. This
does not require downloading every message again when provider guarantees
already establish the correspondence.

Revalidate local eligibility, server identity, and message/thread activity as
late as the provider supports before each mutation. Detected changes postpone
cleanup. Test activity arriving during a sweep and local Trash or deletion
after candidate selection. Document any remaining provider race; do not claim
an atomic check unless the provider supplies one.

Downloading Inbox or draft content for the Active view (TASK-28) must never
permit cleanup. The previous coupling of download filters to deletion safety
is superseded: ownership and current activity supply that boundary. Existing
capture configuration remains separate from these cleanup preconditions.

Purge is opt-in and dry-run by default. It means moving to provider Trash,
never hard deletion. Verify and document each provider's actual Trash move
and retention behavior before enabling its path, including whether and when
Trash is emptied. A successful move does not guarantee permanent removal.
Preserve read-only access for users who do not enable cleanup.

[TASK-14's cleanup acceptance criteria](<task-14 - Drain-remote-servers-—-delete-archived-mail-once-verified-locally.md#acceptance-criteria>)
apply in full. TASK-38 supplies thread protection before cleanup is enabled.
The integration criteria below verify that the Active view, capture, local
management, and cleanup preserve the same ownership boundary. TASK-28 is a
dependency for those checks. Local label changes can use the existing sidecar
representation; the label editor UI is not a prerequisite. Earlier comments
below are historical; their proposal to accept incomplete client threads is
superseded by this design.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 TASK-14's cleanup acceptance criteria are verified by this implementation; its existing capture-filter criteria remain fulfilled by TASK-14.1
- [x] #2 Synthetic provider integration covers Active reading and search, successful capture of contents and labels, local label edits, and eligible server cleanup while preserving the owned contents and labels
- [x] #3 Synthetic provider integration rejects cleanup for Active-only caches, live messages or threads, local Trash or deleted copies, incomplete capture, failed local verification, and ambiguous or incomplete server state
- [x] #4 Provider-specific tests verify Gmail source/account, message/thread identity, and content correspondence; unsupported IMAP cleanup stays held before authentication or remote queries. UIDVALIDITY changes, UID reuse, folder moves, and duplicate Message-IDs must be verified before any future IMAP cleanup is enabled.
- [x] #5 Tests introduce new activity and local Trash or deletion after candidate selection, verify the supported final revalidation postpones cleanup, and cover retry after a partial cleanup result
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add a standalone cleanup command with a preview as the default and an explicit apply option. Keep preview separate from download, capture, cache refresh, local Trash expiry, and index initialization or migration. Read existing capture provenance and the index without changing archive files or labels. Require a regular owned message and sidecar, a freshly verified content hash, complete label metadata, and matching source/account/provider identity; hold ambiguous legacy captures and local Trash or missing copies. Query current provider state and thread protection without capture filters, report candidates and hold reasons, and repeat local and remote checks immediately before each eventual Trash request. Initially no IMAP candidate may clear because complete thread visibility is unavailable; preserve the explicit unknown-state hold. After the required server-cleanup sign-off, implement and test the provider Trash operation with synthetic providers, resumable outcomes, Ctrl-C, late activity, late local changes, and uncertain results. Gmail authorization changes require their own explicit sign-off; preserve existing read-only access for users who do not enable cleanup. Do not run cleanup on a real account as part of implementation.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approval checkpoint, 2026-09-14: implementation still requires explicit server-cleanup sign-off, plus separate Gmail OAuth sign-off if enabled. Proposed boundary: opt-in command, dry-run by default, fresh archive hash/sidecar and source/account identity verification, fresh candidate/thread checks, provider Trash only, no hard deletion or local archive deletion. Keep Gmail read-only credentials for non-cleanup users; request gmail.modify only through an explicit cleanup authorization/re-consent path. IMAP mutation must remain unavailable wherever complete thread state or safe Trash semantics cannot be verified. Next action: finish TASK-28/TASK-38, obtain these sign-offs, then implement and deliver through a PR; do not run cleanup on a real account as part of implementation.

Legacy metadata qualification must be explicit: existing sidecars do not distinguish deliberately omitted/empty labels from captures finalized before TASK-90 after label failure. Cleanup cannot infer complete required-label acquisition from an empty legacy sidecar or resnapshot owned labels automatically. Establish durable capture-completeness evidence for qualifying copies, and retain ambiguous legacy copies until their eligibility can be proved.

Implementation planning is concrete, but server-cleanup and OAuth sign-offs remain pending. The consolidation helper owned_match accepts legacy identity evidence and local Trash for reading purposes, so it cannot authorize cleanup. A preview must avoid cmd_download, which expires local Trash, and ordinary archive initialization, which can create or migrate the index. Reuse validated new capture provenance where appropriate; ambiguous legacy metadata remains held. Existing Gmail authentication can refresh saved tokens or start consent, so implementation verification must use synthetic providers and must not silently introduce an authentication mode. Next decision is approval of optional server-Trash behavior; do not recreate the closed Active-cache PR.

The user explicitly approved optional cleanup implementation and synthetic tests after reviewing preview-by-default behavior, final local/message/thread checks, Gmail Trash retention, IMAP holds, and provider observation limits. Approval does not cover OAuth/credential changes or running cleanup on a real account. Implementation starts on feat/server-cleanup at d660e9d in a separate worktree. Preserve existing read-only Gmail authorization; permission denials must be reported without modifying scopes or tokens. Local verification must avoid archive initialization/migration and must leave owned files, labels, cache, and local Trash unchanged. The Active feature is already pushed directly to master; PR #1 remains closed.

Implemented preview/default and explicit apply with read-only local verification, bounded index traversal, fresh authenticated-account/message/body/thread checks, final owned-copy revalidation, and a single message-level Gmail Trash request without automatic retries. Confirmed server state makes restart resumable after partial or uncertain outcomes. Synthetic integration covers Active reading/capture/local labels/refresh/cleanup, late activity and local Trash/deletion, source/account and result-scope mismatches, and failure/retry without changing owned files or labels. Gmail account and Trash methods preserve the existing readonly OAuth flow unchanged. Focused cleanup suites passed 164 tests before the final interruption case; independent runner/provider reviews found no unresolved defect. Mutations bypassing thread checks, final local revalidation, capture-completeness/hash gates, default preview, account identity, and Trash response validation were rejected. Full repository checks and the implementation commit remain pending.

Next single approval proposal: implement explicit ownmail authorize-cleanup --source NAME, requesting Google's minimum Trash-capable gmail.modify scope through browser consent. This scope also permits broader mailbox changes and sending mail; ownmail would use it for the approved Trash operation. Store a separate credential under keychain service ownmail, account key oauth-token-cleanup/<account>; preserve oauth-token/<account> and the existing readonly setup/download/preview flows. Apply would load and refresh only the cleanup credential, never start consent implicitly, and fail with authorization guidance when missing or invalid. Verify actual granted scope and the selected Gmail profile before saving, retaining expiry and granted-scope metadata; cancelled, wrong-account, or failed consent leaves saved credentials untouched. This OAuth/credential change is not yet approved and no account authorization or cleanup has run. Source: https://developers.google.com/workspace/gmail/api/auth/scopes .

The approved cleanup scope explicitly leaves IMAP accounts held. AC #4 now distinguishes verified Gmail correspondence and unconditional IMAP exclusion from the identity qualification required before any future IMAP enablement. Existing tests prove IMAP cleanup does not authenticate or query the server; no claim is made that UID reuse, moves, or duplicate Message-ID cleanup qualification has been implemented. The full required pre-push gate passed with browser tests: 3,318 passed, one existing expected failure, and 96.19% branch coverage. OAuth/credential changes remain the only unapproved implementation stage; AC #1 and workstream completion remain open pending that stage and final verification.

Implementation checkpoint: 50190ad on feat/server-cleanup, with all required checks passing. ACs #2-#5 are verified within the approved Gmail cleanup/IMAP-held scope. Separate Gmail cleanup authorization has been presented as the next single approval and remains unanswered. Do not repeat cleanup-behavior approval or change OAuth/keychain code until that answer arrives.
Pause checkpoint: the user explicitly approved implementing and synthetically testing separate Gmail cleanup authorization. This supersedes the pending-approval notes above. The approved path is ownmail authorize-cleanup --source NAME, separate cleanup credentials, unchanged read-only download/preview access, and consent-free cleanup apply. This does not authorize connecting the account or running cleanup. Do not repeat either implementation approval.

The user then requested a checkpoint and pause. Preserve the current OAuth draft on feat/server-cleanup; no new PR or push is part of this pause. Separate keychain serialization and CLI routing have focused tests. The provider authorization module and Gmail wrappers are a draft: authorization-specific tests, actual keychain/provider/runner integration with a fake backend, and independent review remain unfinished. Resume those checks before treating cleanup authorization as ready or marking AC #1 complete. Verify granted-scope evidence and omission semantics, refresh and expiry handling, wrong-account and failed-consent preservation, log suppression, and apply never opening consent. Correct the authorize error text that currently guarantees saved credentials were kept even when the final keychain write itself fails. Existing read-only Gmail methods and scopes were verified unchanged. No real-account authorization or cleanup has run.
Checkpoint validation: the full pytest hook passed with required browser tests: 3,378 passed, one existing expected failure, and 95.12% branch coverage. The initial pre-push invocation returned a formatting-change result after formatting two files; tests ran successfully after those changes. The remaining file-hygiene, lint, formatting, and dependency checks are rerun at checkpoint commit. These passing existing and storage/CLI tests do not verify the new provider OAuth flow; its dedicated tests and integration remain required on resume.

Resumed the approved cleanup and separate authorization work. Review base remains d660e9d. Finish dedicated authorization tests and actual keychain/provider/runner integration with synthetic backends, correct verified defects, run independent OpenAI and Anthropic review and required checks, then deliver a review-ready PR. Real-account authorization and cleanup remain outside this implementation task.

Dedicated authorization and cross-layer fake-backend tests now pass. They cover grant omission and refresh semantics, expiry, cancellation, wrong-account and failed-save behavior, credential separation, log suppression, consent-free apply, and preserved owned contents/labels. Independent review exposed hidden HTTP POST retries beneath the Gmail client; mutation now uses one stdlib HTTPS request with no refresh, redirects, or retries. Real connection tests verify one transmission after lost responses, 401s, and redirects. Focused cleanup/authentication suites pass 302 tests, and deliberate regressions were rejected. Final full checks and PR delivery remain pending; no real-account operation ran.

The full required pre-push gate passed after updating the older provider integration to the new single-attempt transport: 3,455 passed, one existing expected failure, and 96.30% branch coverage. Parent cleanup criteria are verified except human-reviewed PR landing. TASK-14.2 remains In Progress until that landing criterion is met. TASK-5.4 remains Done with complete cleanup integration.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-25 06:46
---
IMAP purge has a delete-semantics question Gmail doesn't: RFC 3501 deletion is two-phase. Setting \Deleted only marks — the message stays fetchable until someone issues EXPUNGE, and another client can clear the flag. Following with EXPUNGE destroys it immediately.

Neither matches Gmail's model, where trashing gives a ~30-day retention window and the API exposes it as a TRASH label rather than a flag. So 'purge' means three different things depending on source type, and the task should say which it implements rather than leaving it to whoever writes the IMAP path:

- \Deleted only — reversible, closest in spirit to Gmail's trash, but leaves the server in a state some clients render as strikethrough and others hide. Disk space is not reclaimed.
- \Deleted + EXPUNGE — irreversible, actually frees the server, no recovery if ownmail's verification was wrong.
- Move to the trash folder (role-resolved, doc-7) then \Deleted — closest analogue to Gmail, and the server's own retention policy applies.

Bears on the STOP status: this task deletes user email, and the failure mode of the middle option is unrecoverable. Surfaced while auditing IMAP flags for TASK-19; see doc-7 'IMAP message flags' for why nothing should *read* \Deleted.
---

created: 2026-07-25 06:57
---
doc-8 (Archival semantics) records why purge puts a deadline on capture decisions: once the server copy is trashed, nothing can re-derive metadata that was never captured. Bears on the \Flagged decision in TASK-19 and on this task's delete-semantics question above.
---

created: 2026-07-31 22:55
---
The LEFT OPEN paragraph above ("defer purge for any message whose thread still has a message in the inbox") is now TASK-33, filed 2026-07-31 so the decision is visible in the ledger instead of buried here. TASK-33 records both candidate answers, why the deferral belongs on purge rather than on download, and that it stays evidence-gated. Nothing about this task changes — purge still has no exemptions, and TASK-33 is sequenced after it.
---
<!-- COMMENTS:END -->
