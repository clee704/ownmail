---
id: doc-6
title: Email stack architecture — ownmail's role and the remote drain
type: specification
created_date: '2026-07-24 22:44'
---

> **Superseded product design, 2026-09-14:** [Owning your mail](../../docs/philosophy.md)
> defines the current direction. Ownmail downloads Active mail under server
> authority, archives eligible messages immediately, and separately removes
> verified server copies once their threads are inactive. Download filters alone
> no longer define cleanup safety. The design and alternatives below are retained
> as history; their implementation status and configurable Trash policy are stale.

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

## The drain: two orthogonal knobs

The one net-new capability, expressed as two independent settings that
compose. Neither changes ownmail's current default behaviour.

### Knob 1 — purge (opt-in, default off)

Default is exactly today's behaviour: read, never delete. Enabled, ownmail
removes a message from the server once it has confirmed the local copy.

- **Purge means move to Trash, not hard delete.** This is what makes
  "servers own the grace period" real — Gmail's 30-day Trash retention *is*
  the grace period, and ownmail implements no time logic whatsoever. It
  also closes the loop with knob 2: the default filter excludes trash, so a
  message ownmail just trashed is not re-downloaded next run.
- **Confirmation is a per-message content-hash re-check** of the local
  `.eml` at purge time via the existing `verify`/`sync-check` machinery
  (`cli.py:809,818`) — not "synced recently, probably fine." This is the
  difference between a drain and data loss.
- **Sweep semantics, not download-time-only.** Purge considers every server
  message that passes the current filter and has a verified local copy, not
  just what this run downloaded. Download-time-only cannot meet the goal:
  mail archived before purge was enabled would sit on the server forever.
  Consequence — **the filter is evaluated live against server state at
  purge time**, so a message downloaded a year ago while it sat in the
  inbox becomes purgeable the moment it's archived. This is the generalized
  form of the earlier "read INBOX membership live" rule.

### Knob 2 — download filter (configurable)

Which messages get downloaded at all. **Purge requires download**, so
anything filtered out is automatically never purged. That coupling is what
keeps the inbox safe without a dedicated inbox rule.

- **Not new machinery.** The filter already exists in three inconsistent
  places, none exposed in config: `imap.py:27` `DEFAULT_EXCLUDE_FOLDERS`
  (configurable, but defaulting to Gmail-specific folder names),
  `gmail.py:130` hardcoded `-in:trash -in:spam`, and `gmail.py:224`
  re-checking `TRASH`/`SPAM` on `labelIds`. This unifies and exposes them.
- **Filter terms are canonical system-label names.** Providers spell the
  same concept differently — `TRASH` vs `Trash` vs `[Gmail]/Trash` vs
  `Deleted Items`, plus IMAP SPECIAL-USE flags — so a filter config can't
  be written against raw provider strings. See the dependency note below.
- **Default filter excludes trash, spam, and drafts.** Drafts are live
  working state; purging them would yank an in-progress draft out from
  under a mail client mid-compose. This is the only default behaviour
  change in the whole design.

The intended setup is then just: filter excludes inbox + trash (+ spam,
drafts), purge on. Everything else is downloaded and trashed on the server.

### Why this beats the earlier single-rule design

An earlier draft had purge carry a hardcoded "skip anything in INBOX"
policy plus a verification precondition. The two-knob version is strictly
better: the inbox skip falls out of a general mechanism instead of being a
special case, the filter is independently useful, and purge stays opt-in so
no existing behaviour changes.

Still explicitly rejected as speculative: exempting `\Flagged`/starred
messages (archived means decided, and the star survives in the archive as a
label), a `keep` hold label, and any ownmail-side grace period. Deferred: a
stale-inbox report — that addresses mail lingering on Gmail, a comfort
issue rather than a data-loss one.

### Consequences to handle

- **Editing the filter is destructive.** Under sweep semantics, removing
  `inbox` from the exclude list means the next purge trashes the entire
  inbox. Dry-run-by-default covers most of it; the config docs must say so.
- **OAuth scope.** `gmail.py:16` requests `gmail.readonly`. Trash needs
  `gmail.modify`; hard delete would need full `https://mail.google.com/`,
  another reason to prefer trash. Scope changes are a STOP item and force
  every existing token to re-consent — contained by purge being opt-in, so
  readonly stays the default and only purge users take the wider scope.
- **Retention is provider-specific.** Gmail's 30-day Trash gives a free
  undo window. mailbox.org may not behave the same way — confirm before
  pointing purge at it.
- **This is a STOP item** on two counts (deletes user email, changes OAuth
  scopes): explicit sign-off, and it lands via PR.

### Dependency on TASK-5.2 (corrected)

An earlier version of this doc claimed the drain had no dependency on
TASK-5.2, reasoning that INBOX is the one system folder already
standardized across providers. **That claim is wrong, including for
INBOX.** Recording why, since it's the reasoning that produced the bad
dependency call:

What's actually true is narrow — RFC 3501 mandates an IMAP mailbox literally
named `INBOX`, and Gmail's API happens to use `INBOX` as a system label ID.
That's naming, and naming is not the hard part:

- **The semantics differ.** IMAP `INBOX` is a *folder* — a message is in
  exactly one place. Gmail `INBOX` is a *label* — a message carries it
  alongside others, and "archived" means the label is gone while the message
  still lives in All Mail. "Is this in the inbox" is a different question in
  each model.
- **Even within IMAP, names need normalization.** `INBOX` is case-insensitive
  per spec, so `inbox`/`Inbox`/`INBOX` are the same mailbox and a raw string
  compare is already wrong.
- **Gmail-over-IMAP makes "not in INBOX" ambiguous.** The same message is in
  `INBOX` and `[Gmail]/All Mail` simultaneously. `imap.py:236` downloads from
  All Mail as the sole source precisely because of this, treating other
  folders only as label sources.
- **Folder names are localized.** `imap.py:211-219` hardcodes four language
  variants of All Mail (`[Gmail]/All Mail`, `[Gmail]/Tous les messages`,
  `[Gmail]/Alle Nachrichten`, `[Gmail]/Toda la correspondencia`) and misses
  many others. Direct in-repo evidence that name matching doesn't hold.

So canonical mapping is a **correctness precondition for purge**, not a
presentation nicety: if `inbox` fails to resolve on some provider, inbox
messages pass the filter, get downloaded, and get trashed on the server —
precisely the outcome this design exists to prevent.

This also constrains *how* TASK-5.2 solves it. The mapping has to be
semantic — a **role** per message (JMAP's model, and what IMAP SPECIAL-USE
advertises: `\Trash`, `\Junk`, `\Drafts`) — resolved per provider, not a
lookup table of folder-name strings. TASK-14 depends on TASK-5.2.

## Resolved: client-side deletions and the archive

The two paths are independent, so path B can destroy mail before path A
captures it — `gmail.py:130` hardcodes `-in:trash -in:spam`, so a message
deleted on a phone before ownmail's next sync leaves no archive copy. This
was filed as TASK-15, a code decision about what "delete" should mean.

The two-knob design dissolves it into config: whether `trash` appears in the
download filter. Excluded (the default) means deletions stay deleted;
removed from the filter means Trash is downloaded and deletions are captured
within the provider's retention window. TASK-15 closed, folded into TASK-14.
