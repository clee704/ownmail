---
id: TASK-14.2
title: Optional purge — trash archived mail on the server once verified
status: To Do
assignee: []
created_date: '2026-07-25 05:39'
updated_date: '2026-09-15 04:07'
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
- [ ] #2 Synthetic provider integration covers Active reading and search, successful capture of contents and labels, local label edits, and eligible server cleanup while preserving the owned contents and labels
- [ ] #3 Synthetic provider integration rejects cleanup for Active-only caches, live messages or threads, local Trash or deleted copies, incomplete capture, failed local verification, and ambiguous or incomplete server state
- [ ] #4 Provider-specific tests cover account/source ID collisions, plain IMAP UIDVALIDITY changes and reused UIDs, folder moves, duplicate Message-IDs, and content that differs from the owned copy
- [ ] #5 Tests introduce new activity and local Trash or deletion after candidate selection, verify the supported final revalidation postpones cleanup, and cover retry after a partial cleanup result
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
