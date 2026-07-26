---
id: doc-9
title: 'Label navigation — sidebar structure and the role: search term'
type: specification
created_date: '2026-07-26 03:19'
---

## Goal

Replace the hardcoded All Mail / Trash sidebar with real label browsing.
Resolves TASK-5.1.

The interesting part is not the sidebar markup — it is that AC #3 ("system
labels display under one canonical name per role regardless of which
provider they came from") cannot be expressed in the search language as it
stands. That forces one new query term.

## Why `label:` alone can't satisfy AC #3

A role can be spelled several ways in one archive. Two accounts — a Gmail
API source and an IMAP source — contribute `SENT` and `[Gmail]/Sent Mail`
for the same concept. One sidebar entry named "Sent" therefore has to mean
"any label whose role is `sent`", i.e. a set union.

`label:` cannot express a union, and both plausible workarounds are worse
than they look:

- `label:A OR label:B` **silently ANDs**. `OR` is emitted into the FTS5
  string, but label filters become SQL `WHERE` clauses joined with `AND`.
- `label:A label:B` **silently drops A**. `database.search` keeps a single
  `label_filter` variable, so the second `__LABEL__` marker overwrites the
  first.

Both return a confidently wrong result set rather than an error. Filed as
TASK-21 — independent of this task, and not fixed here.

## Decision: a `role:` search term

`role:<slug>` over the closed role set in `roles.py`
(`inbox sent drafts trash spam archive all`). It resolves, at search time,
to every distinct label in *this* archive whose `role_for_label` matches,
then filters `email_labels.label IN (…)`.

Same shape as the existing `__LABEL__` / `__NOT_LABEL__` markers: the
parser stays a pure function and emits a marker, `database.search` does
the resolution because only it has a connection.

Why this and not the alternatives:

| | Union across spellings | New syntax | AC #3 |
|---|---|---|---|
| `role:sent` | yes | one term | met |
| one sidebar entry per raw label | n/a | none | fails — two entries both named "Sent" |
| `label:A,B` multi-value | yes | one term | met, but less expressive and provider-specific |

`role:` also puts doc-7's vocabulary — already the internal answer to "is
this trash?" — into the surface the user types in, and TASK-14.1 will
expose the same slugs in config.

Notes on scope:

- **Negation is implemented** (`-role:spam`), not because the sidebar needs
  it but because adding `role` to the tokenizer's `known_filters` makes
  `-role:spam` parse whether or not it is handled. Handling it costs about
  as much as rejecting it and is strictly more useful; leaving it unhandled
  would silently match everything.
- **Unknown slugs are a parse error** listing the valid ones, not an empty
  result set. Same reasoning as `label:UNREAD` in TASK-5.3.
- **Not stored.** Resolution is `SELECT DISTINCT label` filtered through
  `roles.role_for_label`, paid only when `role:` is used. doc-7's
  derive-don't-persist rule holds, and improving the name table keeps
  retroactively fixing existing archives.
- Accepted cost: a free-text search for `role:something` used to reach FTS
  as a quoted literal and is now a parse error. Every existing filter made
  the same trade.

## Sidebar structure

Three sections, top to bottom:

1. **All Mail** → `/search` — unchanged. Means "everything in the archive".
2. **System roles**, fixed order: Inbox, Sent, Drafts, Archive, Spam,
   Trash (server). Each links to `role:<slug>`.
3. **Labels** — every remaining label, `label:"<raw>"`, lexicographic.
4. **Trash** → `/trash` — unchanged. ownmail's own bin, not a label.

### Two decisions inside that

**Role `all` is not shown.** `[Gmail]/All Mail` sits on nearly every
message of a Gmail-over-IMAP archive, so the entry would duplicate the
"All Mail" nav item with a near-identical count.

In practice it wouldn't render today anyway: `_FOLDER_NAMES` in `roles.py`
has no `all` entry, so the role only resolves from a live `\All`
SPECIAL-USE flag and never from a stored label. That is doc-7's accepted
cost, deliberately not fixed here — adding `all` to the name table would
also widen `_get_all_mail_folder`, changing *which messages get
downloaded* on untested servers, which doc-7 explicitly declined.

The consequence is that `[Gmail]/All Mail` shows up under Labels as a raw
user label. That is the same treatment `IMPORTANT`, `STARRED` and
`CATEGORY_*` get — provider pseudo-labels stay visible until TASK-19
rules on them — so it is at least consistent. Keeping `all` out of the
nav table stands as the decision for if and when it does resolve.

**Role `trash` renders as "Trash (server)".** ownmail already has a
"Trash" — the local bin at `/trash`, where web-UI deletions go — and the
two are unrelated. The parenthetical only ever appears in an archive that
actually has server trash, which is exactly when the distinction matters:
either the user opted into downloading it (doc-7's `exclude_folders`
override) or the archive predates role-based exclusion and `verify`
reports it as pollution.

**Empty roles don't render at all.** A healthy archive excludes trash and
spam at sync time, so those entries are normally absent.

### Sort order

System roles in fixed reading order; user labels case-insensitively
lexicographic. Not by frequency: the sidebar would reshuffle on every
sync and destroy muscle memory. No config knob — ROADMAP's original
"configurable" note had no consumer, and this repo doesn't add knobs on
spec.

Long label lists scroll inside the section rather than growing the page. A
Gmail archive with 200 labels is normal, and reducing that noise
(`CATEGORY_*`, `IMPORTANT`) is TASK-19's call, not this one's.

## Counts

`get_label_counts()` promises exactly one thing: **the number of results
clicking the entry will produce.** So it mirrors `database.search`'s
implicit filters — `trashed_at IS NULL` and `email_date IS NOT NULL`.

The obvious query for that is 20× too slow to run on every page render,
because the sidebar lives in `base.html`:

| | 15k emails | 100k emails |
|---|---|---|
| `email_labels JOIN emails` (one statement) | 14 ms | **330 ms** |
| covering-index scan, minus trashed rowids | 3 ms | 23 ms |

So it is two statements: a `GROUP BY label` over
`idx_email_labels_label_date` (which covers the `email_date` filter,
because that column is denormalized into `email_labels`), minus a
correction driven by `email_rowid IN (SELECT rowid FROM emails WHERE
trashed_at IS NOT NULL)`. Trash is small and the subquery probes the
`email_labels` primary key, so the correction costs ~5 ms at 100k. Results
are identical to the single-statement form.

No new index — that would be a schema change, and the existing covering
index already does the work.

Measured with `scripts/` absent from the repo on purpose; the benchmark was
a throwaway over a synthetic archive (215 distinct labels, ~4 labels per
message).

## What is deliberately not in scope

- **No labels in the list view.** The list is a scan-and-pick surface;
  per-row chips crowd it and cost a join per page. The detail view is
  where a message's labels belong.
- **No label hierarchy.** Gmail's `Parent/Child` renders flat. Nesting is
  presentation polish with no correctness content.
- **No label editing.** That is TASK-5.4.
- **`EPHEMERAL_LABELS` (`UNREAD`) is filtered out** of both the sidebar and
  the detail-view chips. It only exists in archives synced before TASK-5.3,
  searching it is a deliberate parse error, and offering it as a
  destination would advertise state ownmail does not archive.

## Detail view

The chips in `email.html` get the same canonical naming as the sidebar: a
system label displays its role name and links to `role:<slug>`, so clicking
a chip and clicking the sidebar entry land in the same place. The raw
provider string stays visible in the `title` attribute, and user labels are
unchanged.
