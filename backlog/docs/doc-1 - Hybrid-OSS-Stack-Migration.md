---
id: doc-1
title: Hybrid OSS Stack Migration
type: specification
created_date: '2026-07-23 18:43'
---

## Goal

Keep the custom Flask web UI (that's the part worth owning), but stop
reinventing sync and search where mature tools already solve it well.
Not a rewrite — a hybrid.

## What moves to existing OSS

- **Search** → `notmuch`. Indexes any directory of RFC822 files directly
  (doesn't require Maildir layout). Replaces most of `query.py` and the
  FTS5 half of `database.py`. Query syntax (`from:`, `subject:`, `date:`)
  maps ~1:1. `attachment:` has no notmuch equivalent — tag on ingest
  instead.
- **Generic IMAP sync** → `mbsync` (isync). Mature, handles real
  multi-folder IMAP accounts (Fastmail, work IMAP, old dead providers
  where only IMAP access remains) cleanly via Maildir++ folder mapping.
  Replaces most of `providers/imap.py` for non-Gmail sources.

## What stays custom (no OSS equivalent)

- `providers/gmail.py` — OAuth2, Gmail History API incremental sync,
  batched `messages.get` with rate-limit tuning, native label fetch.
  mbsync is IMAP-only and can't do any of this.
- Keychain-backed credential storage, content-hash dedup,
  `verify`/`sync-check` integrity checking, resumable Ctrl-C downloads,
  local `.eml` import/scan (see roadmap). None of these exist in
  mbsync/notmuch.
- All of `web.py` — the whole point is to keep building this ourselves.

## Gmail labels vs. Maildir folders (the trap to avoid)

Maildir is one-message-one-location. Gmail labels are many-to-many.
If Gmail is ever synced via IMAP folders (rather than the API), syncing
per-label folders duplicates message content on disk once per label.

Rule: any IMAP-based sync of a Gmail account must only pull
`[Gmail]/All Mail` (one copy per message) and get label data from a
separate source — either the Gmail API (what `GmailProvider` already
does) or the `X-GM-LABELS` IMAP extension. Reinforces keeping
`GmailProvider` as-is rather than routing Gmail through mbsync.

## Labels/tags as file-based sidecars

Current `email_labels` table is many-to-many, matching Gmail's model —
but it's the only copy of that data. If lost, labels for
no-longer-accessible accounts (the whole reason this project exists)
can't be recovered from the `.eml` files alone.

Fix: one sidecar metadata file per email (JSON, same basename as the
`.eml`), treated as source of truth for labels/tags. Database (or
notmuch's tag index) becomes a derived, rebuildable cache — same
relationship the DB already has with `.eml` content today. Same pattern
as XMP sidecars in photo archiving tools (digiKam, PhotoPrism).

Implementation constraints:
- Atomic writes only (temp file + rename), never in-place edit.
- Sidecar → index, never index-only. On divergence, sidecar wins;
  `rebuild` reconciles.
- One file per email, not one big labels file — avoids lock
  contention between concurrent `download` and `serve` processes.
- Today there's no local label mutation (`update-labels` only re-pulls
  from provider), but this design is meant to also cover future
  local-only actions (mark read/star, custom personal tags) once those
  exist — Gmail itself treats read/starred as labels, so one mutation
  path covers both.

## Open risk

notmuch is a subprocess/CLI or FFI dependency, not in-process like
SQLite FTS5. Benchmark query latency (especially search-as-you-type)
before committing to it — see task for search backend evaluation.
