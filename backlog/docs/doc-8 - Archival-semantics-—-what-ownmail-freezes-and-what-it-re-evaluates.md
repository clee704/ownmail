---
id: doc-8
title: Archival semantics — what ownmail freezes and what it re-evaluates
type: specification
created_date: '2026-07-25 06:57'
---

## The rule

> **Capture is a transfer of ownership.** Until a message is captured, the
> server is authoritative and the message's eligibility is re-evaluated every
> run. After capture, ownmail is authoritative — its labels are the real ones,
> and it never reads label state from the server again.

ownmail is an archive and a manager, not a mirror. It records what the server
said at the moment it took ownership, and everything after that is ownmail's.

This has been derived independently three times — for read/unread (TASK-5.3),
for IMAP flags (doc-7), and for the download filter (TASK-14.3) — so it is
written here once, as the thing those all follow from.

## Ownership transfer

Local label editing is a headline feature, not an afterthought: the "manage"
half of the product. That is what makes the handoff real rather than a
bookkeeping convention.

- **Before capture** — the server owns the message. ownmail observes it and
  re-checks its eligibility on every run.
- **At capture** — ownership moves. Whatever labels the message carries at that
  instant are what the archive inherits.
- **After capture** — ownmail owns it. Labels are edited locally, sidecars are
  the durable store, and the server's copy of that metadata is no longer
  consulted.

Purge (TASK-14.2) completes the handoff: the server copy is trashed and reaped
under the provider's own retention policy, so no second authority survives.

**But purge is optional**, so the enforceable invariant is the narrower one:
*ownmail never reads label state from the server after capture.* It is not that
the server copy must not be modified — ownmail cannot enforce that, and a user
running without purge will reasonably keep using their provider's client. The
point is that such changes become irrelevant rather than forbidden. With purge
on, the question disappears entirely.

### Consequences

- **Following server changes post-capture would be a bug, not a feature.** It
  would let a non-authoritative source overwrite the authoritative one. This is
  why capture-once is a correctness requirement and not merely cheap.
- **`update-labels` is at odds with the model.** Re-snapshotting from the server
  overwrites ownmail's own labels. Its defensible scope is a one-time backfill
  for archives captured before local editing existed. See TASK-20, which also
  documents that it currently destroys data.
- **Capture timing must match the handoff.** Ownership may only transfer at a
  point where the user is done with the message in their mail client. Eager
  inbox capture — what ownmail does today — hands over mail the user is still
  actively working in, which is wrong under this model. TASK-14.3 is therefore
  a precondition for the manage story, not only for purge safety.
- **`exclude_labels` is an inheritance rule, not censorship.** It says what
  ownmail adopts at the handoff. With local editing available, a user could
  instead delete an unwanted label by hand; the knob earns its keep for
  recurring platform labels across thousands of messages, not for one-offs.

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

- **Not a claim that the archive is immutable.** The opposite: after capture the
  archive is the *only* thing that should change. Sidecars are the source of
  truth and are meant to be written to.
- **Not applicable to the `.eml` files.** Message content never changes; only
  metadata about it does. Local editing covers labels, not messages.
- **Not a restriction on the user's provider account.** They may keep labelling
  in Gmail. ownmail simply stops looking.

## Status

The ownership model is not fully realised yet. What exists and what does not:

- **Exists** — local trash / restore / delete-forever (`web.py:1912-1958`,
  backed by the archive's own trash dir). ownmail already owns *deletion* of
  archived mail.
- **Missing** — local label editing. There is no route, no helper, no UI.
  TASK-5.4.
- **Missing** — capture at the handoff point rather than at arrival. TASK-14.3.
- **Missing** — purge, which completes the transfer. TASK-14.2.

Until TASK-14.3 lands, the corollary users would otherwise be given — organise
before archiving, because the labels a message carries when it leaves the inbox
are the ones it keeps — is not yet true, and should not be documented as if it
were.
