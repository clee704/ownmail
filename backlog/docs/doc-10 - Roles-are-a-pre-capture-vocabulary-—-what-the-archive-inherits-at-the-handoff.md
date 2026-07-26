---
id: doc-10
title: Roles are a pre-capture vocabulary — what the archive inherits at the handoff
type: specification
created_date: '2026-07-26 05:24'
---

## Goal

Settle what the role vocabulary (doc-7) is *for*, and resolve two symptoms
that turn out to be the same problem:

- Archives hold messages and labels with `inbox` and `trash` roles. The
  intended picture says neither should exist.
- The sidebar renders both **"Trash (server)"** (role `trash`) and
  **"Trash"** (ownmail's own bin) — two unrelated things competing for one
  word (doc-9).

The second reads as a naming problem. It isn't. It is the first problem
surfacing in the UI, and renaming the entry would hide the cause.

## The split doc-7 didn't make

doc-7 defined one flat role set: `inbox sent drafts trash spam archive all`.
doc-8 then established that **capture is a transfer of ownership** — before
capture the server is authoritative and eligibility is re-evaluated every
run; after capture ownmail is authoritative and never reads server label
state again.

Cross the two and the role set splits along the capture event:

| Role | Read by | Says |
|------|---------|------|
| `inbox` `trash` `spam` `drafts` | the download filter, live, **pre**-capture | where the message sat in the provider's workflow |
| `archive` `all` | folder discovery, **pre**-capture | which folder to download from |
| `sent` | the archive, **post**-capture | who wrote it |

The first two groups are **eligibility** roles: their entire consumer is the
decision of whether, and from where, to capture. The third is **provenance**
— durably true of the message itself.

## The rule

> **Eligibility roles are never archive metadata.**

Not because they are excluded from download. The filter is configurable by
design and doc-6 depends on that — removing `trash` from the exclusions is
how a user captures client-side deletions inside the provider's retention
window. The reason is what doc-8 already says: **ownmail never re-reads
server label state after capture.** A stored eligibility role is therefore a
frozen snapshot of a state whose entire nature is to change, with nothing
that can ever correct it.

This is the argument TASK-5.3 made for read/unread, reaching one role
further. `INBOX` is `UNREAD`'s sibling, not a classification: mail is
captured near arrival, while it is still in the inbox, and its owner files
it minutes later. The label is wrong within the hour and wrong forever
after.

So the answer to "what if someone widens their filter and downloads inbox or
trash?" is not to make the filter stricter. It is that **the filter and the
inheritance rule are two separate decisions**, currently conflated. The
filter decides *whether to capture*; the snapshot decides *what to inherit*.
A message captured out of trash is a message the user chose to keep — it
should land as ordinary archived mail, because that is what keeping it
means.

### Per-role verdicts

doc-7's four-question test for IMAP flags, applied to roles-as-stored-labels:

| Role | Stays true after capture? | Derivable? | Post-capture consumer? | Verdict |
|------|---------------------------|------------|------------------------|---------|
| `inbox` | no — filed minutes later | — | none | **don't inherit** |
| `trash` | no — untrashed, or reaped by retention | — | none | **don't inherit** |
| `drafts` | no — a draft becomes a sent message | — | none | **don't inherit** |
| `archive` | trivially true of everything captured | yes | nav, where it duplicates "All Mail" | **don't inherit** |
| `all` | trivially true | yes | none — already hidden (doc-9) | **don't inherit** |
| `spam` | arguable — see below | — | nav | **defer to TASK-19** |
| `sent` | **yes** | partly (`From:`) | nav, and a real query | **inherit** |

## What this dissolves

**"Trash (server)" stops existing.** With no `trash`-role label in the
archive, `role:trash` matches nothing, the sidebar entry never renders, and
"Trash" in the UI means ownmail's bin — unambiguously, with no
parenthetical. doc-9 introduced the disambiguation as the best available
answer given a flat role set; removing the collision beats naming around it.

**The system section collapses to Sent.** Of doc-9's six entries, four can
no longer occur, `all` was already hidden, and `spam` is opt-in-only pending
TASK-19. That is not a loss: an entry that duplicates "All Mail", and four
that assert a location the message left long ago, were never navigation.

**`role:` keeps its job.** It stays the search term doc-9 built and the
config vocabulary TASK-14.1 will expose. What narrows is only which roles
can *appear in an archive* — a `role:trash` search is still valid, still
resolves, and correctly returns nothing.

## `spam` is the one open case

Unlike the others, `spam` is a **classification** — the provider's judgement
about content — rather than a location. It does not decay the way `inbox`
does. That is exactly the category TASK-19 already owns (`IMPORTANT`,
`CATEGORY_*`, `STARRED`), so it disposes of it there rather than needing a
second ruling here. Low stakes either way: the default filter excludes spam,
so the question only arises for someone who deliberately opted in.

## Mechanism, and why the two halves differ

Two halves. They cannot use the same test, and that is the load-bearing
detail.

**Going forward — drop at the handoff, from live provider state.** The
existing precedent is `EPHEMERAL_LABELS` dropping `UNREAD` in
`_resolve_label_names` (`gmail.py:392`). The set cannot be a literal
label-name list, because IMAP spellings vary; the test is the role. At
capture time that is safe, because the good signal is still available —
Gmail API label IDs are exact, and the IMAP folder scan still has
SPECIAL-USE flags and the server's delimiter.

**Existing archives — hide at read, and only where the string is
unambiguous.** All the archive kept is the raw label, so `role_for_label` is
heuristic by construction (doc-7's accepted cost). Applying it as a hide
rule would swallow a user label legitimately named `Archive`, `Trash` or
`Bin` — confirmed in a real archive. Synthetic example: a user label `Archive` with a
child `Archive/Example`, and today's `_build_label_nav` already folds it into
the system Archive entry (TASK-26).

So the read-time rule is narrow: exact-match Gmail system label IDs
(`INBOX`, `TRASH`, `SPAM`, `DRAFT`), never case-folded. This is the same
reasoning `EPHEMERAL_LABELS` already documents for `UNREAD` — those IDs are
always upper-case and cannot collide with a Gmail user label. IMAP-derived
spellings stay visible and go to the cleanup path instead, where a human
looks at them.

Neither half rewrites a sidecar. Improving the name table keeps fixing
archives retroactively, per doc-7.

## What this does not fix

Dropping a label does not remove a **message**. An archive synced before
role-based exclusion holds mail downloaded *from* a trash folder that the
old Gmail-only name list missed (doc-7) — mail its owner deleted in a
client, captured by mistake, and carrying no other label because the trash
folder was its only source. `verify` reports it today (doc-7 AC #6,
`commands.py:1044`) and offers no way to act on the report, because moving
user email is a STOP item.

TASK-25 resolves that by pointing the report at a destination that is
reversible — ownmail's own bin — so the cleanup is not a delete.

**Ordering constraint:** `verify`'s report reads *stored* labels. Hiding
eligibility roles at read time must not blind it, or the cleanup path loses
its input. Whichever lands first, the other must not regress it.

## Revises

- **doc-7** — the role set is not flat. It stands unchanged as the
  *resolution* vocabulary; what changes is that resolution is a pre-capture
  activity, and only `sent` (plus `spam`, pending TASK-19) is archive
  metadata.
- **doc-9** — the six-entry system-roles section and the "Trash (server)"
  disambiguation in `_ROLE_NAMES`. Both were correct given a flat role set.
  doc-9's decision to hide `all` was the first instance of this rule; this
  doc generalizes it rather than contradicting it.
