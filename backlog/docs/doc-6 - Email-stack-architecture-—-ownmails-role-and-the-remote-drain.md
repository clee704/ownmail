---
id: doc-6
title: Email stack architecture — ownmail's role and the remote drain
type: specification
created_date: '2026-07-24 22:44'
---

## Goal

Fix where ownmail sits in the overall email stack, and record what was
considered and rejected getting there. Supersedes doc-1's framing of the
sync question (doc-1's search and sidecar conclusions still stand).

Driving requirements:

- Combine multiple providers/accounts into one place.
- One file per message on own drive, inspectable with any tool.
- Single source of truth. No mail left on third-party servers long-term.

## The stack

Two independent paths, deliberately **not** integrated:

```
providers ──→ ownmail ──────────────→ archive / search / manage
providers ──→ per-device mail clients → send / receive / delete / archive
```

Mail clients talk directly to their providers over IMAP; multi-account
setup per device is a one-time cost.
ownmail keeps doing what it already does: pull, archive, index, serve the
web UI.

Consequence: **ownmail's current architecture is already correct.** The
`YYYY/MM` archive layout, `providers/imap.py`, `GmailProvider`, and the
label sidecars from TASK-1.3 all stay as they are. The only net-new
capability is the drain (below).

## Considered and rejected: local store as a Dovecot backend

The alternative was making the local archive authoritative and serving it
over IMAP via Dovecot, so devices configure one account instead of N.
Rejected — the cost is enormous and the benefit is a one-time setup task:

- **Archive layout would have to become Maildir.** Dovecot has no
  flat-`.eml` driver, so `archive.py`'s date-organized layout goes away.
- **The sidecars break.** They key on `.eml` basename (`sidecar.py:25`),
  but Maildir encodes flags *in the filename* and renames on every flag
  change and folder move.
- **Concurrency discipline.** Maildir delivery (`tmp/` → fsync → rename
  into `new/`) is genuinely lock-free and safe, but delivery isn't
  everything. Keywords require writing Dovecot's private per-mailbox
  `dovecot-keywords` file — a read-modify-write race against Dovecot. The
  safe shape would be ownmail as an IMAP client to its own Dovecot
  (`APPEND`/`doveadm import`), never touching files for writes, with
  direct file reads only for indexing.
- **It makes ownmail a daemon.** Near-real-time delivery needs IMAP IDLE
  for IMAP sources plus `history.list` polling for Gmail. There is no
  loop, scheduler, or long-running mode anywhere in `cli.py`/`commands.py`
  today. This was the single biggest addition, bigger than the layout
  change.
- **Unresolved:** Dovecot's Maildir backend is believed to cap keywords at
  26 per mailbox (`a`–`z` encoding), likely well under a real Gmail label
  count. Never verified. Moot now, but it would
  have needed answering first.

Also worth recording: `imaplib.IMAP4.idle()` (needed for the IDLE half of
this) exists only on Python 3.13+, while `pyproject.toml:11` pins `>=3.10`.

## mbsync: NO-GO re-affirmed, on different grounds

TASK-1.2 closed NO-GO because mbsync's Maildir++ staging tree meant two
on-disk layouts and two copies. Under the Dovecot proposal that objection
*did* evaporate — Maildir would have been the one true layout. But
removing a cost is not the same as establishing a benefit, and mbsync's
benefits don't survive contact with this stack:

- **It's IMAP-only.** Verified against an `isync` binary:
  standard IMAP vocabulary present (`IMAP4rev1`, `UIDPLUS`, `APPENDUID`),
  zero Gmail tokens — no `X-GM-LABELS`, `X-GM-THRID`, or `googleapis`. So
  Gmail routes through `GmailProvider` regardless, and mbsync would cover
  the generic IMAP path.
- **OAuth2 is not Gmail API support.** mbsync delegates auth to SASL
  (`AUTHENTICATE %s`), which is separate from Gmail API support.
- **Two IMAP clients, two state models.** The drain must verify local
  integrity before expunging. Splitting fetch (mbsync's `.mbsyncstate`)
  from expunge (ownmail's hash index) means neither holds the full picture
  of "is this message safely on disk." That is a data-loss shape.
- **`ExpireSide Far` doesn't fit.** mbsync's only drain-like mode is
  `MaxMessages` + `ExpireSide Far`, which is count-based arrival-order
  FIFO, not conditioned on triage state.
- **A Maildir writer is needed anyway** for the Gmail path, so mbsync
  eliminates no component.

Original NO-GO trigger still stands: revisit only if `providers/imap.py`
hits a real, specific problem cheaper to fix via mbsync than directly.

## The drain

The one net-new capability: delete mail from remote servers once it is
safely archived locally.

**One policy rule, one precondition.** These are different kinds of thing
and shouldn't be presented as a single list of knobs:

- **Policy — skip anything in INBOX.** Age is the wrong predicate. The
  inbox is a decision queue kept near-empty, so a message still sitting in
  it is undecided *at any age*, and a message that's been archived is
  decided. Triage is already the signal; no heuristic needed. This is the
  only user-facing rule.
- **Precondition — content verifies locally.** Hash the local `.eml` and
  confirm it matches before expunging. No knob, no config, never surfaced.
  It is the difference between a drain and data loss, and must be a
  per-message check at drain time using the existing `verify`/`sync-check`
  machinery (`cli.py:809,818`) — not "synced recently, probably fine."

**Read INBOX membership live from the server**, in the same session that
does the delete. This is what makes an age/grace-period buffer
unnecessary: the only thing a delay would protect against is a stale local
view of where a message lives, and there's nothing stale about state read
immediately before expunging. It also removes any "days since it left the
inbox" bookkeeping.

Explicitly rejected as speculative: exempting `\Flagged`/starred messages
(archived means decided; the star survives in the archive as a label), a
`keep` hold label, and any grace period.

Deferred, not needed for v1: a stale-inbox report ("14 messages older than
30 days"). Addresses mail lingering on Gmail, which is a comfort issue,
not a data-loss one.

### Notes for implementation

- **Gmail gives a free undo window.** Its IMAP delete semantics route
  through `[Gmail]/Trash` with 30-day retention, so a drain mistake is
  recoverable for a month. mailbox.org may not behave the same way — check
  before pointing the drain at it.
- **This is a STOP item.** It deletes user email, so it needs explicit
  human sign-off and lands via PR, not straight to `master`.

## Known gap in the two-path split

The two paths are independent, so path B can destroy mail before path A
captures it: `gmail.py:130` hardcodes `-in:trash -in:spam`, so a message
deleted on a phone before ownmail's next sync is gone permanently, with no
archive copy. Nothing to do with the drain. Whether that's correct depends
on whether "delete" means "I don't want this" or "get it out of my inbox"
— filed separately rather than assumed.
