---
id: TASK-35
title: Re-derive IMAP folder labels for already-archived messages
status: Done
assignee: []
created_date: '2026-08-06 04:08'
updated_date: '2026-08-06 18:44'
labels: []
dependencies:
  - TASK-34
priority: high
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
There is no path that repairs label state on mail already in the archive. Found while fixing TASK-34, which had been flattening cross-folder membership on every non-Gmail IMAP source.

## Why nothing today covers it

- `update-labels` selects only emails with zero rows in `email_labels`. A message with one wrong label has a label, so it is never visited — and since TASK-20 it restores from the sidecar rather than re-deriving anyway.
- `download`, even after `reset-sync`, short-circuits on content hash (`archive.py:373`) before the label write. An email already on disk is skipped whole; its labels are never reconsidered.
- `rebuild --only sidecars` treats the sidecar as authoritative, so it propagates whatever is on disk. Deleting the sidecars first does not help: the emails then have no labels, `update-labels` picks them up, and derives the same single folder name from `provider_id`.

So the flattened state is currently permanent, even though the information is still on the server.

## Shape

`_scan_standard` already builds exactly what is needed — `_folder_lookup`, mapping composite id to every folder the message was found in — and throws it away for messages that are already downloaded. A relabel path would run the ordinary scan and write that map onto existing rows and sidecars. No new server capability, no new parsing; a full scan of a mid-size account is a couple of minutes.

## The doc-8 question, which needs deciding first

doc-8 says ownmail never reads label state from the server after capture, because that lets a non-authoritative source overwrite the authoritative one. This command does exactly that, so it needs an argument for why it is different — the honest one being that it repairs membership ownmail *intended* to capture and got wrong, rather than following changes the user made later. That distinction is not machine-checkable after the fact: a folder the user moved a message into post-capture is indistinguishable from one the buggy scan missed.

Consequences worth weighing: it should probably be explicitly invoked and scoped to a source, never part of sync; and it will silently adopt post-capture reorganisation as a side effect. If that is unacceptable, the alternative is to accept the flattening on pre-fix archives and close this.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A message archived from one IMAP folder but present in several gets all of them, in the DB and the sidecar
- [x] #2 Only messages already in the archive are touched — no re-download
- [x] #3 Explicitly invoked and source-scoped; never runs as part of download
- [x] #4 doc-8 records the decision on why post-capture re-reading is admissible here, or the task is closed unbuilt
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built as `ownmail relabel --source <name> [--strategy union|server] [--apply]`.

## The doc-8 decision

Resolved in favour of building it, with the argument recorded in doc-8 under
*Repair, and why it is not mirroring*. The short version: the rule's purpose is
that a non-authoritative source must never *overwrite* the authoritative one,
which is a statement about overwriting. `union` — the default — only ever adds,
so nothing the archive holds can be lost and the invariant that matters is
intact. The enforceable rule is restated as *ownmail never lets server state
replace local label state*.

The strategy is a per-run flag rather than a baked-in choice, because the doc-8
anxiety is about whose authority wins and only the operator knows whether they
have reorganised since capture:

- `union` (default) adds folders the archive is missing, never removes. Cannot
  repair a label that is *wrong*, only one that is *missing*. Adopts
  post-capture moves into a folder as extra labels — the accepted cost.
- `server` is a true re-snapshot and does drop labels the server no longer
  reports. This genuinely departs from doc-8 and is opt-in for that reason.

`--strategy` becomes unnecessary for the local-edit half once label provenance
lands — filed as TASK-36, targeted at TASK-5.4 where local labels first exist.
The removal question survives provenance and stays doc-8's.

## Implementation

`_scan_standard` already built composite_id -> folders and threw it away for
messages already downloaded. Two changes made it usable:

- The map now covers *every* composite id a message was seen under, not just
  the elected primary. Only primaries are downloaded, so the extra entries are
  inert during a normal run — but an archived row carries whichever folder won
  the election on the earlier run, which need not be this run's primary.
- `_scan_standard` now clears `_message_id_to_folders`, so a standard scan
  cannot fall through to a stale Gmail-path lookup.

`scan_folder_membership()` exposes the map and returns None for the Gmail
All-Mail path, which keys membership by Message-ID rather than by the
composite id archived rows carry; `relabel` refuses that source with a
message rather than silently matching nothing.

Rows are matched on `account` + `provider_id`. Account scoping is not
cosmetic: `INBOX:1` collides trivially across sources. Legacy NULL-account rows
are deliberately excluded — they come from `import`/`scan`, so their
provider_id is not `folder:uid` anyway.

Labels are read sidecar-first (invariant #1), falling back to the DB only for
emails predating sidecars. Writes go sidecar first, then DB, so an interrupt
between the two leaves the repair on disk and only the rebuildable index
behind.

## Caveats

- A message whose folder's UIDVALIDITY has rolled will not match and is
  counted as "not found on the server", left untouched. Same for anything
  deleted from the server since capture.
- Nothing is written without `--apply`; the default run prints the per-message
  diff. This is opposite to `import`/`scan`, whose flag is `--dry-run` — the
  asymmetry is deliberate, since `--strategy server` can remove labels.
- `--source` is optional and defaults to every IMAP source, matching every
  other `--source` in the CLI. It was briefly required, on the reasoning that a
  command able to delete labels should make the operator name its target; that
  was dropped as inconsistent, since `--apply` is already the gate that stops
  an accidental run from writing anything. AC #3's "source-scoped" is still met
  — a run can be scoped to one source, and nothing but a person invokes it.
- Not supported for Gmail-over-IMAP or the Gmail API source type.
<!-- SECTION:NOTES:END -->
