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

## Settled 2026-07-26: opt-in, per source

Default OFF. This changes what ownmail downloads, costs bandwidth and local storage, and doc-6's model does not assume it. Per-source, consistent with exclude_folders and with TASK-14.1's filter.

Opting in transfers the cadence obligation to the operator: if you want a live view you keep ownmail running often enough that it is one. That is a fair trade and it removes staleness as a blocker.

**But opt-in does not remove staleness as a REQUIREMENT.** Choosing the feature is not the same as knowing it is currently working. A dead cron, a sleeping laptop or a dropped network all produce a stale view that still looks authoritative, and the user has no way to tell. So the freshness signal is not optional polish — it is what makes opt-in a fair deal rather than a trap. Show the age of the active view wherever active messages appear.

## Cadence, and what it actually costs

Per-minute is plausible but the constraint is not where it first appears. ownmail is a CLI with no daemon, so every run pays process startup, connection and auth.

- Gmail API: history.list since the watermark is one cheap call, usually empty. Per-minute is not a quota concern.
- IMAP: per-minute means ~1440 logins/day per source. Some providers throttle frequent connections. 3-5 minutes is the safer default to document.

TWO CADENCES ARE PROBABLY THE ANSWER, and it falls out of the two purposes being different sizes:

- Refreshing the ACTIVE VIEW needs current membership of the excluded-role folders — effectively SELECT INBOX plus SEARCH. Bounded by inbox size, so it is cheap enough to run every minute.
- CAPTURE eligibility needs TASK-14.3's candidate set, (All Mail) minus (already archived), which enumerates All Mail. On a large mailbox that is tens of thousands of UIDs per run and is not something to do every minute.

So a frequent cheap active refresh plus a normal-frequency capture pass, rather than one loop doing both. Recorded as the likely shape, not a requirement — if the full pass turns out cheap enough at the target cadence, one loop is simpler and wins.

## Surfacing it in the UI

Active messages appear in normal search results by DEFAULT. Keeping them in a separate view would recreate the two-places problem this task exists to remove. They just need to be distinguishable.

Four touch points, following patterns the UI already has:

1. **A search term.** doc-9 established that every sidebar entry is a link to a search, so an Active entry requires one. KNOWN_FILTERS (query.py:88) has no `is` today, so this adds one: `is:active` / `is:archived`. Same shape as `role:` — parser stays pure and emits a marker, database.search resolves it. Unknown values are a parse error listing the valid ones, per TASK-23 and doc-9.
2. **A sidebar entry**, pointing at `is:active`, with a count. Only rendered when the feature is on.
3. **A subtle per-row treatment** in the list — muted text or a left border, NOT a chip. doc-9 kept chips out of the list view on purpose because they crowd a scan-and-pick surface, and that reasoning holds here.
4. **A detail-view banner**, which is where the read-only rule needs explaining, because the detail view is where a user would try to act on the message. This is also the natural place for the freshness line.

OPEN: whether existing counts absorb active messages or split. 'All Mail — 32k' silently changing meaning when the feature is switched on is a small surprise worth deciding deliberately.

## Open questions, in the order they matter

1. ~~Freshness~~ — settled above: opt-in per source, operator owns cadence, freshness signal mandatory. Still open within it: whether ownmail should refuse to render active data past some staleness threshold, or only ever show the age and let the user judge. Prefer showing the age; a hard cutoff invents a policy the operator did not ask for.
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
- [ ] #7 The feature is off by default and enabled per source
- [ ] #8 is:active / is:archived parse, with an unknown value producing a parse error rather than an empty result
- [ ] #9 Active messages appear in ordinary search results, visually distinguishable without a chip in the list view
<!-- AC:END -->
