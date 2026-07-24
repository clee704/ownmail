---
id: TASK-1.3
title: Design per-email sidecar metadata files for labels/tags
status: Done
assignee: []
created_date: '2026-07-23 18:44'
updated_date: '2026-07-23 19:03'
labels:
  - storage
  - design
dependencies: []
parent_task_id: TASK-1
priority: high
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Move label/tag state out of the DB-only email_labels table into a per-email sidecar file, so it survives even if the index is lost. DB/notmuch becomes a derived, rebuildable cache. See doc-1 for full design constraints (atomic writes, sidecar-wins-on-divergence, one file per email).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 One JSON sidecar file per .eml, same basename, containing labels/tags
- [x] #2 Writes are atomic (temp file + rename)
- [x] #3 DB/notmuch index treated as fully rebuildable from .eml + sidecar files
- [x] #4 Design covers both provider-synced labels and future local-only actions (read/star/custom tags)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented (not just designed):

- ownmail/sidecar.py: sidecar_path()/read_labels()/write_labels() - one JSON file per .eml (same basename, .json extension), atomic writes via tempfile.mkstemp + os.rename in the same directory. Dedups labels, preserves order. Schema: {"version": 1, "labels": [...]}.
- archive.py backup(): writes a sidecar for every downloaded email alongside the existing email_labels DB write (dual-write, sidecar is the durable source of truth going forward).
- commands.py cmd_update_labels() (both Gmail-API and IMAP-folder paths): also writes sidecars, not just DB.
- New `ownmail rebuild --only sidecars` (wired via cli.py --sidecars-only): reconciles every email in the archive - if a sidecar already exists its labels overwrite the DB (sidecar wins on divergence per doc-1); if missing, one is backfilled from current DB label state (one-time migration path for archives created before this existed).
- Sidecar files follow their .eml through trash_email/restore_email (renamed alongside) and permanently_delete_emails/empty_trash (deleted alongside), so they never end up orphaned from the message they describe.

Validated against a copy of a real archive without changing the source: backfill wrote sidecars matching Gmail labels; reconcile is idempotent on a clean second run, and a manually-edited sidecar correctly overwrote the DB on the next reconcile (sidecar-wins verified).

Not done (out of scope for this task, left for when/if needed): no local read/star/custom-tag mutation UI yet (design accommodates it - same one-file-per-email JSON, same write path - but no product surface calls it yet); did not run the sidecar backfill against a full archive (only a copied slice) - that is a one-time migration an operator runs themselves via `ownmail rebuild --only sidecars` whenever ready.

18 new tests across tests/test_sidecar.py, tests/test_archive.py, tests/test_commands.py. Full suite: 1340 passed (up from 1322 baseline).
<!-- SECTION:NOTES:END -->
