---
id: TASK-14.2
title: Optional purge — trash archived mail on the server once verified
status: To Do
assignee: []
created_date: '2026-07-25 05:39'
updated_date: '2026-07-31 22:55'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
parent_task_id: TASK-14
priority: high
ordinal: 6
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Knob 1 of doc-6, split out of TASK-14. Keeps ALL of TASK-14's STOP-item weight: it deletes user email and needs an OAuth scope widening from gmail.readonly to gmail.modify. Requires explicit human sign-off and lands via PR, not straight to master.

Depends on TASK-14.1 because purge requires download: anything the filter excludes is automatically never purged, and that coupling is what keeps the inbox safe without a dedicated inbox rule.

PURGE HAS NO EXEMPTIONS, INCLUDING SENT (settled 2026-07-26, after proposing a sent exemption and rejecting it).

THE PROPOSAL was: purge never touches role sent, because outgoing mail has no triage step. Received mail is protected by the inbox exclusion — it sits on the server through its whole active period and only becomes eligible once triaged, so purge arrives after the exchange is over. Sent mail is eligible the instant it exists, so purge trashes a reply while the conversation is live and the user's own half of the thread vanishes from clients rendering it.

WHY THAT IS WRONG, three reasons, any one sufficient:

1. IT SOLVES A GENERAL PROBLEM WITH A SPECIFIC RULE. A purged message disappears from client thread views. That is true of every purged message, not just sent ones — archive a received message while its thread is still active and the same gap appears. Sent merely hits it more often, because it has no triage delay. Carving out sent treats a symptom and leaves the general case untouched.

2. IT LEAVES A SECOND AUTHORITY IN PLACE PERMANENTLY. doc-8: purge "completes the handoff: the server copy is trashed and reaped under the provider's own retention policy, so no second authority survives". Exempt sent and its server copy lives forever, so a user who later trashes or re-labels a sent message diverges from the archive with nothing to reconcile it — doc-8's accepted staleness cost, normally bounded by purge, made permanent for one category.

3. IT CONTRADICTS THE REASON THE TOOL EXISTS. doc-6's driving requirement is no mail left on third-party servers, and privacy is the motive. Sent mail is what the user wrote; it is not the category to leave behind. An exemption that grows without bound on the provider inverts the priority the product is built on.

RESOLUTION: purge treats sent like everything else. The thread gap is real, and it is recorded once as a general property of purge rather than worked around per-role.

MITIGATION IS OWNMAIL'S OWN THREAD VIEW (TASK-6), not server retention. Once purge is on, the provider is not where threads are read — ownmail is. That is the consistent answer and it needs no special case. Worth noting as a soft sequencing preference: enabling purge before TASK-6 exists means no good thread view anywhere.

LEFT OPEN, if the annoyance turns out to be real in practice: defer purge for any message whose thread still has a message in the inbox. Note this is general, not sent-specific, which is what makes it the right shape. It needs threading (TASK-6.1), so it is not a blocker — and it should only be built on evidence, not on the anticipation recorded above.

Scope, ACs and hazards are otherwise unchanged from TASK-14 - see that task and doc-6. In particular: purge means move to provider Trash (never hard delete), confirmation is a per-message content-hash re-check at purge time, sweep semantics rather than download-time-only, dry-run by default, and the hazard that narrowing the filter makes the next purge run delete more.
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
