---
id: doc-7
title: Canonical system-label roles — provider-agnostic mapping
type: specification
created_date: '2026-07-25 05:14'
---

## Goal

Give ownmail one vocabulary for "this message is trash / spam / a draft /
in the inbox" that holds across Gmail API, Gmail-over-IMAP, and arbitrary
IMAP servers. Resolves TASK-5.2.

Two things force this:

- **A confirmed bug.** `imap.py` excluded folders by literal name against
  a Gmail-only list (`["[Gmail]/Trash", "[Gmail]/Spam"]`). Any server that
  names its trash anything else — plain `Trash`, `Deleted Items`,
  `INBOX.Trash` — archived deleted mail as normal mail. Found in a real
  archive.
- **TASK-14 (purge) depends on it.** Its download filter is configured in
  terms of system labels, and a term that fails to resolve means messages
  get trashed on the server that shouldn't be. doc-6 records why.

## Decision: roles, derived on demand

A closed set of **roles** — semantic, per-message, provider-independent:

```
inbox  sent  drafts  trash  spam  archive  all
```

Each has a consumer today. `all` replaces the hardcoded All Mail name
list; `archive` falls out of the same SPECIAL-USE enumeration for free.
Deliberately **not** included: `flagged`, `important`, `starred`,
`unread`. RFC 6154 defines `\Flagged` and Gmail advertises `\Important`,
but nothing consumes them yet.

`unread` stays out permanently: TASK-5.3 resolved read/unread by *not*
archiving it, since nothing refreshes a captured value and it therefore
only decays. That task added `EPHEMERAL_LABELS` to this module — a
separate, smaller idea than a role, for provider labels that record
client state rather than archive content. TASK-19 decides whether
`STARRED`, `IMPORTANT` and `CATEGORY_*` belong there too.

## IMAP message flags: ignore all but one

The general rule these verdicts follow — metadata is frozen at capture,
eligibility is re-evaluated until capture — is in doc-8.

RFC 3501 defines six message flags. ownmail archives none of them today,
and should keep it that way except for `\Flagged`. A flag earns capture
only by surviving all four:

| Flag | Stays true? | Derivable? | Consumer? | Verdict |
|------|-------------|------------|-----------|---------|
| `\Seen` | no | — | — | ignore (TASK-5.3) |
| `\Recent` | no | — | — | ignore |
| `\Answered` | yes | yes | no | ignore |
| `\Draft` | yes | yes | no | ignore |
| `\Deleted` | no | — | no | ignore |
| keywords | yes | partly | no | ignore |
| `\Flagged` | yes | **no** | yes | **capture** |

- **Stays true** — `\Seen` decays (nothing re-fetches a downloaded
  message). `\Recent` is session-scoped: it says who connected first, not
  anything about the message, and IMAP4rev2 (RFC 9051) removed it.
- **Derivable** — `\Answered` is recoverable from the archive itself: the
  reply sits in Sent with `In-Reply-To` pointing at the original. `\Draft`
  the message flag is redundant with the `drafts` role, which resolves at
  folder level. Same derive-don't-store rule as the roles above.
- **Consumer** — registry keywords (`$Forwarded`, `$MDNSent`, `$Junk`) are
  server-dependent and sparsely set, and `$Junk` duplicates the `spam`
  role.
- `\Deleted` is listed for completeness. Nothing should *read* it, but
  whether purge *writes* it — and whether it follows with EXPUNGE — is a
  live question for TASK-14.2, and a different one.

### Why `\Flagged` is the exception

It is the only flag that is user-curated, leaves no trace anywhere else in
the message, and is destroyed by purge if not captured. It is also already
half-implemented: Gmail's `STARRED` label flows through
`_resolve_label_names` into sidecars today, so "ignore all flags" would
mean deleting working data rather than declining to add any. Level up
(read `\Flagged` for IMAP) rather than down.

Note the name collides across two RFCs, at two different levels:

- **RFC 3501** `\Flagged` — a *message* flag. The per-message bit.
- **RFC 6154** `\Flagged` — a *mailbox* SPECIAL-USE attribute, for a folder
  presenting all such messages. Gmail's `[Gmail]/Starred` advertises it.

The mailbox attribute is the cheaper path where it exists: the folder scan
already enumerates SPECIAL-USE, so Gmail-over-IMAP yields star-ness with no
`FETCH FLAGS` at all. Generic servers with no such folder need the message
flag. `_SPECIAL_USE` in `roles.py` deliberately omits `\flagged` until
TASK-19 adds the consumer.

Roles are **derived on demand**, never stored. `roles.py` is a pure
function over provider state; the sidecar format is unchanged
(`SIDECAR_VERSION` stays 1) and no DB column is added.

Why derive rather than persist:

- Improving the name table retroactively fixes every existing archive on
  the next read, with no re-sync and no sidecar rewrite.
- One representation of the fact, so nothing can go stale or disagree.
- TASK-14 doesn't need persistence: doc-6 specifies the filter is
  evaluated *live against server state* at purge time, so the provider is
  connected and SPECIAL-USE is available anyway.

Accepted cost: a folder identifiable *only* by its SPECIAL-USE flag —
say a Dutch `Prullenbak` the name table misses — cannot be re-resolved
offline later, because all the archive kept is the raw string. This is
narrower than it sounds. It does not affect already-polluted archives
(nothing was persisted then either), and going forward those folders are
excluded at sync time, so the message never lands. If an offline consumer
ever needs it, the resolved folder→role map can be cached as a
`sync_state` row — that table is plain key/value, so it needs no schema
change.

## Resolution order

**IMAP**, highest confidence first:

1. **SPECIAL-USE attributes** (RFC 6154) from the `LIST` response —
   `\All`, `\Archive`, `\Drafts`, `\Junk`, `\Sent`, `\Trash`. This is the
   provider-agnostic primitive and it costs nothing to read: the LIST
   parser already captured the flags and discarded them.
2. **`INBOX`**, compared case-insensitively. RFC 3501 mandates the name
   and mandates that it is case-insensitive, so a raw `==` is wrong.
3. **Leaf-name table**, case-insensitive, matched against the last path
   component after splitting on the delimiter the server reported — so
   `INBOX.Trash` and `[Gmail]/Trash` both reduce to `Trash`.

The name table is **deliberately bounded**: common English and provider
spellings plus the most widely seen German, French, Spanish, Dutch,
Italian, Japanese and Korean forms. It is a fallback for servers too old
to advertise SPECIAL-USE, not an attempt at exhaustive i18n — there is no
way to verify an exhaustive list, and an unverified one is a maintenance
liability. `exclude_folders` is the documented escape hatch when the
table misses.

**Gmail API**: system label IDs (`INBOX`, `SENT`, `DRAFT`, `TRASH`,
`SPAM`) are stable and never localized, so it is a direct map. Note the
singular `DRAFT`.

## What this changes

- `_get_all_mail_folder`'s four hardcoded localized names
  (`[Gmail]/All Mail`, `[Gmail]/Tous les messages`, …) are deleted in
  favour of role `all`. This fixes Gmail accounts in any of the ~70
  locales the old list missed.
- The All-Mail-as-sole-download-source optimization stays gated on the
  host being Gmail, even though other servers can advertise `\All`.
  Widening it changes *which messages get downloaded* on servers we've
  never tested, and a server whose `\All` isn't truly exhaustive would
  silently lose mail. Out of scope for a correctness fix.
- Default exclusion becomes role-based: trash and spam, whatever they're
  named.

## `exclude_folders` semantics

**Replace, not merge** — the pre-existing behaviour, kept deliberately:

- **Unset** (the state of every config today, since the option was never
  documented) → exclude by role: trash and spam.
- **Set** → that literal list is the exclusion, and the role defaults do
  not apply.

Replace keeps doc-6's TASK-15 resolution intact: whether trash is
downloaded has to remain a config choice, because removing `trash` from
the exclusion is how a user opts into capturing client-side deletions
before the provider's retention window closes. A hard role exclusion with
no override would contradict that.

Corollary — the role default is what repairs existing installs. They have
no `exclude_folders` key, so they pick up correct exclusion on the next
sync with no config edit.

`ownmail setup` additionally writes a **commented-out** `exclude_folders:`
block listing the folder names it actually resolved to trash/spam on that
specific server, discovered by a `LIST` over the connection setup already
opens to test credentials. Commented, because uncommenting it is an opt-in
downgrade from role matching to name matching — the block exists to make
the behaviour visible and editable, not to become the default path.

Note: `exclude_folders: []` falls back to the defaults rather than
disabling exclusion, because the check is `exclude_folders or DEFAULT`.
Pre-existing, kept — an empty list meaning "sync my trash" is a footgun,
and the explicit way to say it is to list the folders you do want.

## Already-polluted archives (AC #6)

**Report only.** `ownmail verify` gains a read-only phase that resolves
stored raw labels through the same name table and reports emails carrying
a trash- or spam-role label, grouped by label and account, with the search
command to inspect them.

No `--fix`. Moving user email files is a STOP item, and the mapping is
heuristic by construction — a false positive would silently trash
correctly-archived mail. The report is the part that is safe and the part
the AC actually asks for. Cleanup stays a manual, deliberate act.

## Scope boundary against TASK-14

This task delivers the **vocabulary and correct defaults**. TASK-14 owns
the **configurable filter** — exposing role terms in config, unifying
`gmail.py`'s hardcoded `-in:trash -in:spam` and its `labelIds` re-check
into one configured path, and the purge itself. Building the config
surface here would front-run a task that is a STOP item on two counts.
