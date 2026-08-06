---
id: TASK-38
title: Thread-level capture deferral — hold a message until its thread is settled
status: To Do
assignee: []
created_date: '2026-08-06 19:51'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
priority: medium
ordinal: 6
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build task for the rule settled in TASK-33 on 2026-08-06. TASK-33 holds the reasoning and the rejected alternatives; this is the implementation.

THE RULE. A candidate message is not captured while any member of its thread is in a TRANSIENT excluded role — inbox or drafts. Trash and spam members are ignored: they are permanently excluded (TASK-14.1), so counting them would mean a thread with one deleted or spammed member never settles.

Deferral acts on CAPTURE, not on purge. Purge requires download, so a deferred message keeps its server copy until the thread clears — it is late, not lost. See TASK-33 for why this reverses that task's original placement of the rule.

GENERAL, NOT SENT-SPECIFIC. Sent mail is where the effect is most visible, because it has no triage delay and so is eligible mid-conversation. But the rule takes no notice of the sent role, and must not grow one: the case a sent-only rule would miss is a FILED message whose thread gets a new inbox reply. That generality is what distinguishes this from the sent purge exemption rejected on 2026-07-26.

NO ESCAPE HATCH (user, 2026-08-06). No max defer age, no override flag. A thread that never clears defers indefinitely. A time cap would invent a policy ownmail otherwise refuses to hold — doc-6 puts the grace period on the provider and keeps time logic out of ownmail entirely. The lever is triage: clear the inbox message and the thread drains.

DOES NOT NEED FULL THREAD GROUPING (TASK-6.1). The question is only whether a candidate's thread intersects the live set, and the live set is the transient-excluded membership TASK-14.3 already enumerates every run:
- Gmail API: threadId on the candidate, matched against the threadIds of the excluded enumeration. Free.
- Gmail-over-IMAP: X-GM-THRID. Free.
- Plain IMAP: a Message-ID / In-Reply-To / References header fetch over the inbox and drafts folders only — bounded by their size, not a thread walk. Match a candidate by whether its References chain or Message-ID intersects that set.

Reuse TASK-6.1's derivation if it has landed by then rather than writing a second one; the point is only that this does not BLOCK on it.

EVIDENCE GATE, still in force for timing. TASK-33 said do not build on anticipation. The SHAPE is now settled, but whether to build it is still gated on the gap being observed in practice — which can happen before purge lands, since capture-without-purge already produces incomplete threads inside ownmail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A candidate whose thread has a member in inbox or drafts is not captured, and is captured on a later run once that member leaves
- [ ] #2 Thread members in trash or spam do not defer capture
- [ ] #3 The rule reads the same transient-excluded enumeration TASK-14.3 already builds, adding no second server sweep
- [ ] #4 Plain IMAP resolves thread membership from headers over the transient-excluded folders only, never a full-mailbox walk
- [ ] #5 No role is special-cased: sent is deferred by the same predicate as everything else
- [ ] #6 config.example.yaml documents that a thread parked in the inbox defers its whole thread indefinitely, with no override
<!-- AC:END -->
