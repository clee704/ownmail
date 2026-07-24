---
id: doc-5
title: ROADMAP.md retirement — content disposition map
type: other
created_date: '2026-07-24 20:29'
---

## Goal

TASK-2.3 deleted `ROADMAP.md`. It was a second, parallel planning surface next
to `backlog/` — the two drifted (ROADMAP still listed Import & Scan as
"not yet scheduled" after TASK-7 shipped it), and a roadmap nobody updates is
worse than none.

This doc records where every line of it went, so "was that dropped, or is it
tracked somewhere?" has an answer without digging through git history.

## Disposition

| ROADMAP section | Where it went |
|---|---|
| **Vision** — file-first, DB is just an index | Already stated in README.md § Philosophy and AGENTS.md § Project invariants. Not duplicated a third time. |
| **Web UI Polish** → Label sidebar with counts + sort order | **TASK-5.1** (label-based navigation). Already written to absorb this, including ROADMAP's note about configurable sort order. |
| **Web UI Polish** → Simple password-based auth for LAN/tunnel access | **Won't do** — superseded by `decision-1`, which puts the web UI behind Cloudflare Access instead of hand-rolling login in Flask. No task filed. |
| **Web UI Polish** → Verify CJK attachment filename encoding (RFC 5987) | **TASK-8** |
| **Backlog** → Import & Scan | **Done** — shipped as TASK-7 (`ownmail import` / `ownmail scan`). ROADMAP's design sketch was the spec, and it was followed. |
| **Backlog** → Email Export (mbox / PDF) | **TASK-9** |
| **Backlog** → Deduplication | **Resolved, no task.** ROADMAP itself had already struck this through: IMAP cross-folder dedup lives in the IMAP provider, content-hash dedup happens during download, and `verify --fix` cleans up duplicates in the archive. A standalone `ownmail dedup` command would be new work, not carried-over work — file it fresh if a real need appears. |
| **Backlog** → Headless Server Support | **TASK-10** |
| **Backlog** → Encryption at Rest | **TASK-11** |
| **Contributing** — pointer to CONTRIBUTING.md | Dropped; README.md and AGENTS.md both link CONTRIBUTING.md already. |

## Going forward

`backlog/` is the only planning surface. Roadmap-shaped questions ("what's
next?") are answered by `backlog board` and the milestone/ordinal sequencing in
`doc-4`, not by a hand-maintained list. Don't reintroduce a ROADMAP.md.
