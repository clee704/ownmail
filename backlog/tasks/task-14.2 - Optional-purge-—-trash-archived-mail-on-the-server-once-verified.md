---
id: TASK-14.2
title: Optional purge — trash archived mail on the server once verified
status: To Do
assignee: []
created_date: '2026-07-25 05:39'
updated_date: '2026-09-14 08:53'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
  - TASK-38
parent_task_id: TASK-14
priority: high
ordinal: 7
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

- Ownmail owns a successfully captured archive copy, and a fresh content-hash
  check verifies the local `.eml`. An Active cached copy is insufficient.
- Current server state shows the message is outside Inbox, unfinished outgoing
  state, Trash, and Spam. Earlier capture does not override present activity.
- The thread is no longer Active, as verified by TASK-38. Unknown or incomplete
  state postpones cleanup.

Cleanup sweeps previously captured messages as well as this run's captures.
Reading current server roles for these checks never changes the archived copy
or its labels. Sent and filed mail follow the same rules: either may be archived
immediately while its server copy stays available during a live conversation.

Downloading Inbox or draft content for the Active view (TASK-28) must never
permit cleanup. The previous coupling of download filters to deletion safety
is superseded: ownership and current activity supply that boundary. Existing
capture configuration remains separate from these cleanup preconditions.

Purge is opt-in and dry-run by default. It means moving to provider Trash,
never hard deletion; final removal follows the provider's retention policy.
Verify each provider's move and retention behavior before enabling its path.
Preserve read-only access for users who do not enable cleanup.

TASK-14 holds the acceptance criteria. TASK-38 supplies thread protection before
cleanup is enabled. Earlier comments below are historical; their proposal to
accept incomplete client threads is superseded by this design.
<!-- SECTION:DESCRIPTION:END -->

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
