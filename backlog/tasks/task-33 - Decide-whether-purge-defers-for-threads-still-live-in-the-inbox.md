---
id: TASK-33
title: Decide whether purge defers for threads still live in the inbox
status: To Do
assignee: []
created_date: '2026-07-31 22:54'
labels: []
milestone: m-5
dependencies:
  - TASK-14.2
  - TASK-6.1
priority: medium
ordinal: 7
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
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
- [ ] #1 The choice between Answer A (accept the gap) and Answer B (defer purge for live threads) is recorded with reasoning, in TASK-14.2 or its own doc
- [ ] #2 The decision is made against observed behaviour after purge has run, not in anticipation of it
- [ ] #3 If B is adopted: the deferral acts on purge and not on download, and config.example.yaml documents that a thread parked in the inbox blocks its whole thread from draining
- [ ] #4 If A is adopted: the permanent degradation of provider-side thread views is documented as a known cost of enabling purge
<!-- AC:END -->
