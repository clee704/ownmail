---
id: TASK-7
title: Import external .eml files (ownmail import command)
status: Done
assignee: []
created_date: '2026-07-24 05:04'
updated_date: '2026-09-13 09:44'
labels: []
milestone: m-0
dependencies: []
priority: high
ordinal: 2
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ownmail currently only recognizes emails downloaded via its own download command (Gmail API/IMAP) - there's no way to bring in externally-sourced .eml files. External providers such as Tuta Mail can supply .eml exports for import. This is already spec'd in ROADMAP.md's 'Next Up — Import & Scan' section (not yet implemented) - reuse that design rather than re-deriving it: 'ownmail import <path> [--account EMAIL] [--move] [--dry-run]' recursively scans for .eml files, derives provider_id as 'local:{Message-ID}' (fallback 'local:sha256:{content_hash}' when Message-ID is missing) so the local: prefix can't collide with gmail/imap provider ids, derives email_id the normal way, checks duplicates, copies/moves into the standard archive layout, registers + indexes in the DB, batch-commits every 10 emails with Ctrl-C-safe resume. A companion 'ownmail scan [--account EMAIL] [--dry-run]' detects .eml files already sitting in the archive dir untracked by the DB and registers them in place. Code changes per ROADMAP: database.py (get_tracked_filenames), archive.py (extract reusable file-saving helper; add import_email()/scan_archive()), cli.py (import/scan subcommands), commands.py (cmd_import()/cmd_scan() with progress + Ctrl-C handling). This should become the canonical import task when TASK-2.3 retires ROADMAP.md - don't file a duplicate there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 ownmail import <path> ingests a directory of external .eml files into the archive with dedup, following the local: provider_id scheme
- [x] #2 ownmail scan registers untracked .eml files already present in the archive dir
- [x] #3 Both commands are resumable (Ctrl-C safe, batch-committed)
- [x] #4 Verified end-to-end against a real email export
<!-- AC:END -->
