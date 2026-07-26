---
id: TASK-14.2
title: Optional purge — trash archived mail on the server once verified
status: To Do
assignee: []
created_date: '2026-07-25 05:39'
updated_date: '2026-07-25 06:57'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
parent_task_id: TASK-14
priority: high
ordinal: 5
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Knob 1 of doc-6, split out of TASK-14. Keeps ALL of TASK-14's STOP-item weight: it deletes user email and needs an OAuth scope widening from gmail.readonly to gmail.modify. Requires explicit human sign-off and lands via PR, not straight to master.

Depends on TASK-14.1 because purge requires download: anything the filter excludes is automatically never purged, and that coupling is what keeps the inbox safe without a dedicated inbox rule.

SENT MAIL MUST BE EXEMPT FROM PURGE (user, 2026-07-26). The one place the capture model does not carry over to purge, found by asking what the model says about outgoing mail.

The model is: capture a message once its owner is done with it. For incoming mail the inbox exclusion supplies that — a message sits on the server through its whole active period and only becomes eligible once triaged, so by the time purge can touch it the exchange is usually over. OUTGOING MAIL HAS NO TRIAGE STEP. Nobody files their Sent folder. A sent message is eligible the instant it exists, so capture happens within one sync and purge follows immediately after.

The failure that produces: purge trashes the server copy of a reply while the conversation is still live, and the user's own half of the thread disappears from every mail client rendering it. Sending is the START of an exchange, not the end of one. This is the exact harm the inbox exclusion exists to prevent, arriving through the door the inbox exclusion does not cover.

Note doc-6's grace-period reasoning does not save this. 'Servers own the grace period' via Gmail's 30-day Trash retention buys RECOVERABILITY, not usability — a trashed message is still gone from the thread view. The two are different properties and doc-6 only argued the first.

RESOLUTION: purge never touches messages with role sent. Capture is unaffected — sent mail is still downloaded immediately, which is correct, since sending is final and there is no later action to wait for.

Cost, and why it is acceptable: sent mail stays on the provider, so 'no mail left on third-party servers' becomes 'no RECEIVED mail left'. Sent is a small fraction of a typical mailbox, so the goal is substantially met. Weigh that against replies vanishing mid-conversation.

Note this is an exemption of the kind doc-6 explicitly rejected as speculative (it declined to exempt \Flagged, and declined a 'keep' hold label). Those had no demonstrated failure mode. This one does, and it is not rare — it fires on the next reply after purge is enabled. Recording the distinction so the rejection is not cited against it.

Open, for whoever implements: whether an exemption is enough or sent should eventually purge once its thread is resolved. That needs threading (TASK-6.1) and is not worth blocking on — the exemption is correct on its own and can be narrowed later.

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
<!-- COMMENTS:END -->
