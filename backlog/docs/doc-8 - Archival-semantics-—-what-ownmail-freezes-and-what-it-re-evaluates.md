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
- **`update-labels` is a backfill, and only that.** Re-snapshotting from the
  server would overwrite ownmail's own labels, so it doesn't: it visits only
  emails carrying no labels at all, and where a sidecar exists it restores the
  DB from the file rather than the other way round. That is its whole
  defensible scope — archives captured before sidecars existed. TASK-20.
- **Capture timing must match the handoff.** Ownership may only transfer at a
  point where the user is done with the message in their mail client. Eager
  inbox capture — what ownmail does today — hands over mail the user is still
  actively working in, which is wrong under this model. TASK-14.3 is therefore
  a precondition for the manage story, not only for purge safety.

  **The message is not the whole unit** (2026-08-06). Read strictly, "done with
  the message" is done with the *exchange*, and a reply sent into a live thread
  is the counterexample: it is eligible the instant it exists, while its
  conversation is still open in the inbox. So capture also defers while any
  member of a candidate's thread sits in a transient excluded role — TASK-33
  for the reasoning, TASK-38 for the build. This is a strengthening of the rule
  above rather than an exception to it, and it takes no notice of the `sent`
  role: a filed message whose thread gets a new inbox reply defers identically.
- **`exclude_labels` is an inheritance rule, not censorship.** It says what
  ownmail adopts at the handoff. With local editing available, a user could
  instead delete an unwanted label by hand; the knob earns its keep for
  recurring platform labels across thousands of messages, not for one-offs.

## Repair, and why it is not mirroring

`relabel` (TASK-35) rescans an IMAP source's folders and rewrites the labels on
messages already captured. Read literally that is the thing this document
forbids, so it needs an argument — and the argument is narrower than "repair is
a special case".

The rule's purpose is that a non-authoritative source must never *overwrite* the
authoritative one. `relabel --strategy union`, the default, only ever adds: no
label the archive holds is removed, so nothing of ownmail's can be lost. The
enforceable invariant is therefore the one this document should have stated all
along — **ownmail never lets server state replace local label state** — and an
additive repair leaves it intact.

What union does not preserve is the weaker claim that ownmail stops *looking*.
It looks. The cost is that a folder the user moved a message into after capture
is indistinguishable from one a buggy scan missed, and is adopted as a label.
That is drift in the commentary rather than in the files, which is the trade
this document already makes everywhere else.

`--strategy server` is the true re-snapshot and does break the rule: it drops
labels the server no longer reports, which is following post-capture change. It
exists because union can only fix a label that is *missing*, never one that is
*wrong*, and the operator is the only party who knows whether their archive has
been reorganised since capture. It is opt-in, prints its diff first, and writes
nothing without `--apply`.

Both are hand-run, report before they write, and never run as part of
`download`. A run can be scoped to one source, though it defaults to sweeping
every IMAP source — the containment that matters is that nothing invokes this
except a person, not how many sources one invocation covers.

Label provenance (TASK-36) would settle half of this permanently: with
server-provided and locally-added labels held apart, a re-scan replaces the
server partition and cannot reach the local one, so `--strategy` collapses to a
single behaviour. The removal question survives it — replacing the server
partition still follows post-capture removals — and stays as stated here.

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
the archive keeps. Later additions and removals are not tracked, and no routine
operation re-reads them: `update-labels` fills in emails that have no labels at
all and leaves every other message untouched (TASK-20). The one command that
does re-read is `relabel`, which is a hand-run repair rather than part of sync
— see *Repair, and why it is not mirroring* above.

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

**How the candidate set is built** (settled 2026-08-06; this replaces the
three per-provider prescriptions that stood here, which were a different
mechanism each). Enumerate what is *excluded* and diff it across runs:

    candidates = new arrivals ∪ (last run's excluded set − this run's)

Departure becomes a set difference, which is the one transition a watermark
cannot express. The cost is bounded by the size of the excluded set rather
than the archive — which is why only the *transient* roles are diffed, since
they are the self-bounding ones. The obvious alternative, enumerating the
*eligible* set and subtracting what is archived, was rejected on cost: the
eligible set is essentially the whole archive, so it is O(mailbox) per run
and grows forever. TASK-14.3 has the measurements.

Per provider, what that costs:

- **Plain IMAP** — nothing new. A folder move allocates a new UID above the
  destination's watermark, so every transition is detected for free.
- **Gmail API** — a handful of `messages.list` calls per run, flat in mailbox
  size. Replaces the `labelAdded`/`labelRemoved` subscription this document
  used to require.
- **Gmail-over-IMAP** — one `SEARCH` of each transient-excluded folder. This is
  what fixes that path's blindness to departures; the full rescan previously
  prescribed here is not needed.

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

- Labels applied after capture never reach the archive on their own.
  `update-labels` does not bring them in — it only fills gaps where there are no
  labels. `relabel` will, for IMAP folder membership, but only when run by hand
  and only for the source named.
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
