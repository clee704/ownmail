---
id: TASK-28
title: Active messages — surface the pre-capture set so ownmail is a complete view
status: To Do
assignee: []
created_date: '2026-07-26 07:01'
updated_date: '2026-07-26 07:02'
labels: []
dependencies:
  - TASK-14.3
priority: medium
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
USER PROPOSAL, 2026-07-26. Two classes of message in ownmail: ARCHIVED (today's model — captured once, ownmail owns it, server never re-read) and ACTIVE (still live on the server; ownmail follows its changes each run and nothing is final).

The problem it solves is a real UX gap, not a hypothetical. Today a full picture of your mail requires two places: the mail client for anything still active, ownmail for anything archived. Search is the sharpest case — 'did that invoice arrive?' spans both, and you have to ask twice. It also fixes an asymmetry found while settling sent mail: a sent reply is archived immediately while the message it replies to is still in the inbox and therefore invisible, so ownmail shows half a conversation.

## Why this is cheaper than it sounds

**It is not a new ownership model.** doc-8 already defines this exact state: 'Before capture — the server owns the message. ownmail observes it and re-checks its eligibility on every run.' Active is that phase made visible. Authority is unchanged — server owns active, ownmail owns archived, capture is still the one-way door. What changes is that ownmail stops hiding the pre-capture set.

**The set already has to be computed.** TASK-14.3 defines the candidate set as (All Mail) minus (already archived), enumerated every run. That IS the active set. So most of the machinery is a prerequisite that is already filed, and this task is largely a surface over it.

**It makes the model legible.** Users would watch messages move from Active to Archived, which is the capture moment made concrete. Today capture is invisible and has to be explained.

## The failure mode that would undo everything

ACTIVE FETCH MUST NOT BE CAPTURE. If 'download it to show it' is implemented as capture, eager inbox capture is back and the entire filter design (TASK-14.1, TASK-14.3, doc-8) is undone through a side door. Active means OBSERVED, NOT OWNED. Keep the two paths separate in code, not just in intent.

## Rules that fall out, not chosen

- **Active messages are read-only in ownmail.** The server owns them, so a local label edit (TASK-5.4) would be silently overwritten on the next run. No editing until capture.
- **Active storage lives outside the archive.** Following server changes means deleting local copies when the server does. Inside the archive that collides with invariant #1 and with the STOP rule on deleting mail files. Outside it, it is a disposable cache, rebuildable from the server, and nothing about the archive's guarantees changes.
- **Active messages are never purged.** They are not captured, and purge acts only on captured mail.
- **The active-to-archived transition IS capture**, with labels freezing at that instant. No new concept needed.

## Open questions, in the order they matter

1. **Freshness, and the trap.** The value proposition requires the active view to be current. A stale one is WORSE than none: today a user knows ownmail is archive-only, but a six-hour-old inbox looks authoritative and is not. ownmail has no scheduler (doc-6 rejected the daemon), so this needs an answer — frequent cron, prominent sync age, or refusing to render active data past some staleness. Decide before building, not after.
2. **Bodies or headers?** Index-only (headers plus snippet) avoids downloading and then deleting mail the user discards, and is the cheap first cut. Full bodies give offline reading of active mail, at the cost of churn on a busy inbox. Recommend index-only first.
3. **Read-only means triage still happens in the client**, so the goal is 'one place to READ and SEARCH', not 'one place to work'. Acting on active mail from ownmail would need write scopes and would make ownmail a mail client — out of scope, and a STOP item.
4. **Schema.** A message class is new state. STOP item; needs sign-off before implementation.

## Relationship to doc-6

If adopted this amends doc-6's two-path model, which assigns live mail to the client and the archive to ownmail. The amendment is narrow — ownmail gains a read-only window onto path B, it does not take over path B — but doc-6 should say so rather than being quietly contradicted.

DEPENDS ON TASK-14.3, which produces the candidate set this renders. Building it first would mean inventing that enumeration twice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Active messages are visibly distinct from archived ones in the UI, and searchable alongside them
- [ ] #2 An active message that changes on the server reflects that change on the next run; one that disappears from the server disappears from ownmail
- [ ] #3 Active fetch shares no code path with capture, and no active message is ever written into the archive without passing the filter
- [ ] #4 Active messages cannot be label-edited in ownmail
- [ ] #5 Active data lives outside the archive directory and its removal never touches archive content
- [ ] #6 The age of the active view is visible wherever active messages are shown
<!-- AC:END -->
