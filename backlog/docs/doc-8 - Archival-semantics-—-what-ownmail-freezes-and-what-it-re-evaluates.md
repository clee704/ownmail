---
id: doc-8
title: Archival semantics — what ownmail freezes and what it re-evaluates
type: specification
created_date: '2026-07-25 06:57'
---

## The rule

> **Once a message is captured, its metadata is frozen. Until it is captured,
> its eligibility is re-evaluated every run.**

ownmail is an archive, not a mirror. It records what the server said when it
looked, and does not chase changes afterwards.

This has been derived independently three times now — for read/unread
(TASK-5.3), for IMAP flags (doc-7), and for the download filter (TASK-14.3) —
so it is written here once, as the thing those all follow from.

## Why the two halves are not in conflict

They look opposed: don't follow changes for labels, do follow changes for
trash. They aren't, because they act on opposite sides of one event, and the
failure modes are not comparable.

- **Stale metadata** is a cosmetic defect on a message you have. The `.eml` is
  correct; a label is out of date.
- **A message never captured** is a hole in the archive. After purge
  (TASK-14.2) trashes the server copy, an unrecoverable one.

Invariant #1 says files are the source of truth. Labels are commentary on the
files. So ownmail spends effort on not missing files and accepts drift in the
commentary — never the reverse.

## What follows

**Labels are a snapshot.** Whatever the provider reported at capture is what
the archive keeps. Later additions and removals are not tracked. `update-labels`
exists to re-snapshot on demand and is a manual, whole-archive operation, not
part of sync. (It is also currently broken — TASK-20.)

**Read/unread is not captured at all.** It is the degenerate case: a value that
is not merely stale after capture but actively false, because sync picks mail up
near arrival, when it is usually unread, and nothing corrects it. TASK-5.3.

**IMAP message flags are not captured, except `\Flagged`.** The four-question
test and per-flag verdicts are in doc-7.

**Eligibility is re-evaluated until capture succeeds.** A message skipped for
being in trash is not skipped forever. If it leaves trash it becomes a candidate
again and is downloaded. Not seeing a message must never make it permanently
invisible — a transient state would otherwise cause permanent data loss.
TASK-14.3 owns the mechanism: sync signals produce *candidates*, and each
candidate's current state is re-checked against the filter.

Per provider:

- **Plain IMAP** — correct already. A folder move allocates a new UID above the
  destination's watermark, so every transition is detected for free.
- **Gmail API** — needs `labelAdded`/`labelRemoved` alongside `messageAdded`
  (`gmail.py:214`). Without them, untrashing produces no event ownmail sees.
- **Gmail-over-IMAP** — departure from a folder leaves no trace, so folders the
  filter depends on must be rescanned in full each run.

**Transient state is the user's to declare.** A label used as workflow state —
`Waiting`, `To Read`, or a star used as a to-do marker — has no correct archival
representation. Freeze it and the archive asserts a state you have since left;
track it and it goes to zero, leaving no record it ever existed. It describes
*now*; an archive records *then*. Only the owner knows which of their labels are
classification and which are a to-do list, so the answer is `exclude_labels`
(TASK-19), not a mechanism.

## When capture happens, and why it matters

Capture timing sets label fidelity, because it decides *when* the snapshot is
taken.

**Today capture is arrival-driven**, and that is the worst possible moment: the
message is caught before its owner has filed it, so the snapshot holds `INBOX`,
maybe a `CATEGORY_*`, and none of the user's own organizing.

**TASK-14.3 moves capture to eligibility**, which for a typical filter means
inbox-exit — precisely when the user *has* filed it. That is a second argument
for that task, independent of purge: capture-at-filing is what makes "capture
once" defensible rather than merely cheap.

Corollary for users, once that lands: organize before archiving, because the
labels a message carries when it leaves the inbox are the ones it keeps.

## Accepted costs

Stated plainly so they are not rediscovered as bugs:

- Labels applied after capture never reach the archive without a manual
  `update-labels`.
- A message untrashed during a window when ownmail happens to run gets archived,
  even if the user re-trashes it immediately. Eligibility is evaluated at fetch
  time; there is no notion of "they didn't really mean it."
- Once purge trashes the server copy, nothing can re-derive metadata that was
  never captured. This is what puts a deadline on capture decisions — see doc-7
  on why `\Flagged` is the one flag worth taking.

## What this does not mean

- Not an argument against `update-labels`. Re-snapshotting on demand is fine;
  what is rejected is sync silently chasing server state.
- Not a claim that the archive is immutable. Users may edit labels locally —
  sidecars are the source of truth and are meant to be writable.
- Not applicable to the `.eml` files. Message content never changes; only
  metadata about it does.
