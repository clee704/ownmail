---
id: TASK-33
title: Decide whether purge defers for threads still live in the inbox
status: Done
assignee: []
created_date: '2026-07-31 22:54'
updated_date: '2026-09-14 08:53'
labels: []
milestone: m-5
dependencies:
  - TASK-14.2
  - TASK-6.1
priority: medium
ordinal: 10
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
**Superseded 2026-09-14.** [Ownership philosophy](../../docs/philosophy.md)
now defines capture per message and defers server cleanup while a thread is
active. TASK-38 carries that implementation. The discussion and completed
criteria below record the earlier decision; they no longer prescribe capture
deferral. TASK-28 supplies the consolidated view of Active and Archived mail.

Promoted 2026-07-31 from a LEFT OPEN paragraph inside TASK-14.2, where it was invisible. It is the one part of the drain design that was never settled.

## The problem

Purge trashes the server copy of a captured message, so that message disappears from the thread view of every mail client reading the provider. If the rest of the conversation is still live, the client renders half a thread.

This is a general property of purge, not a sent-mail quirk — archive any received message while its thread is still active and the same gap appears. Sent mail merely hits it more often, having no triage delay. That generality is why the sent-specific exemption was REJECTED on 2026-07-26 (three reasons, in TASK-14.2); this task is the general form the rejection pointed at.

## Two candidate answers, and they are not the same shape

ANSWER A — ACCEPT THE GAP, MOVE THREAD-READING TO OWNMAIL. This is what TASK-14.2 currently records as the resolution: once purge is on, the provider is not where threads are read. Needs TASK-6 (thread view) and is helped by TASK-28 (active messages), which independently fixes the half-a-conversation problem *inside ownmail* by making the un-captured half visible. Zero new mechanism. Cost: the mail client thread view degrades permanently, and that is the surface still used for triage and reply.

ANSWER B — HOLD THE THREAD TOGETHER ON THE SERVER until every message in it is eligible. Needs thread membership over UN-CAPTURED server messages: cheap on the Gmail API (threadId) and Gmail-over-IMAP (X-GM-THRID), a References/In-Reply-To walk on plain IMAP (TASK-6.1). Cost: threads that never fully clear — one message parked in the inbox indefinitely, a long-running list thread — block their whole thread from ever draining.

Note the two answers target DIFFERENT VIEWS. Answer A repairs the view inside ownmail; Answer B repairs the view in the mail client. TASK-28 does not substitute for B.

## If B is chosen: where the rule goes

Defer PURGE, not download. The user framing that produced this task deferred download ("a sent reply should not be downloaded while the message it answers is still in the inbox"), which is the stronger form and the wrong placement:

- WITH PURGE OFF THERE IS NO GAP AT ALL. The server copy stays regardless of what ownmail downloaded, so the client thread view is intact. A download-time rule pays a cost in every configuration to fix a problem that exists in exactly one.
- Purge requires download, so deferring purge is strictly narrower and loses nothing.
- Deferring download leaves the ARCHIVE incomplete for as long as a thread stays live, coupling archive completeness to thread state. Deferring purge leaves only the server copy lingering, which is the thing that is supposed to linger.

The argument on the other side, recorded so it is not re-derived: doc-8 says ownership may only transfer at a point where the user is done with the message, and a live thread means they are not. Principled, and it does make thread-aware CAPTURE the more faithful reading of doc-8. It loses to the practical asymmetry above.

## Do not build this on anticipation

TASK-14.2 is explicit that the annoyance must be observed before it is engineered around, and it stays explicit here. Sequence: enable purge, live with Answer A, and only build B if the client-side thread gap turns out to bite in practice. This task exists so that decision is made deliberately rather than by whoever implements purge, not to pre-commit to B.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The choice between accepting the thread gap and deferring for live threads is recorded with reasoning
- [x] #2 The decision states which side of capture/purge the deferral acts on, and why
- [x] #3 The predicate is defined against transient excluded roles only, so a trashed or spammed thread member cannot stall a thread forever
- [x] #4 Whether a bounded escape hatch exists is decided explicitly, and the accepted cost of the answer is written down
- [x] #5 Implementation is carried by a separate task, so this one closes as a decision record
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Settled 2026-08-06 (user): Answer B, in its general form, on capture — with no escape hatch.

Arrived at from the sent-mail side: the proposal was 'do not download sent messages at all until every message in the thread is downloadable'. Three corrections to that framing, then the decision.

**1. Not sent-specific.** The unit is the thread, and 'defer while any thread member is still live' subsumes sent with no carve-out. The case a sent-only rule misses is a FILED message whose thread gets a new inbox reply — same defect, no sent involved. This is the same generality argument that killed the sent purge exemption on 2026-07-26.

**2. 'All members downloadable' is the wrong predicate.** TASK-14.1 fixes trash and spam as permanently excluded, so a thread with one spammed or deleted member would never become fully downloadable and would stall forever. The predicate is **no member in a TRANSIENT excluded role** — inbox, drafts — ignoring trash and spam members entirely.

**3. Deferral is not loss, which is what defeats this doc's own objection.** The argument above for deferring PURGE rather than DOWNLOAD rests on 'deferring download leaves the ARCHIVE incomplete'. Under the ownership model that overstates it: purge requires download, so a deferred message keeps its server copy until the thread clears. Nothing is at risk; the archive is late, not holed. Set against that, capture-side deferral is the more faithful reading of doc-8 (ownership transfers when the user is done with the message), and it removes the half-a-conversation asymmetry that is currently one of TASK-28's motivations.

**So: defer CAPTURE, not purge.** This reverses the 'if B is chosen: where the rule goes' section above, and on that section's own reasoning — the practical asymmetry it invoked does not survive the observation that a deferred message is still safely on the server.

### No escape hatch (user)

A thread that never clears defers indefinitely. No max age, no override flag. Rationale: a live thread means the exchange is not over, which is the whole premise; a time cap would invent a policy ownmail otherwise refuses to hold (doc-6: 'servers own the grace period', ownmail implements no time logic). Accepted cost, to be documented rather than discovered: one never-triaged list thread pins its own half of the conversation on the server for as long as it stays live. The lever the user already has is triage — clear the inbox message and the thread drains.

### Cheaper than this doc assumed

The 'needs thread membership over UN-CAPTURED server messages' cost was priced against full thread grouping (TASK-6.1). The deferral direction does not need it: the question is only 'does this candidate's thread intersect the live set', and the live set is the inbox, which TASK-14.3 now enumerates every run anyway. Gmail gives it free (threadId / X-GM-THRID); plain IMAP needs a Message-ID/References header fetch over the inbox only, not a thread walk.

### Not built here

Filed as its own task, after TASK-14.1. Run the plain filter first — this doc's evidence gate ('do not build this on anticipation') still applies to whether the gap bites, even though the SHAPE is now settled.
<!-- SECTION:NOTES:END -->
