---
id: TASK-35
title: Re-derive IMAP folder labels for already-archived messages
status: To Do
assignee: []
created_date: '2026-08-06 04:08'
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
- [ ] #1 A message archived from one IMAP folder but present in several gets all of them, in the DB and the sidecar
- [ ] #2 Only messages already in the archive are touched — no re-download
- [ ] #3 Explicitly invoked and source-scoped; never runs as part of download
- [ ] #4 doc-8 records the decision on why post-capture re-reading is admissible here, or the task is closed unbuilt
<!-- AC:END -->
