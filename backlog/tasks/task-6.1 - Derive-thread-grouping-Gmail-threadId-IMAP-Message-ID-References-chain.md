---
id: TASK-6.1
title: 'Derive thread grouping: Gmail threadId + IMAP Message-ID/References chain'
status: To Do
assignee: []
created_date: '2026-07-24 04:59'
updated_date: '2026-09-26 02:24'
labels: []
milestone: m-3
dependencies: []
parent_task_id: TASK-6
priority: low
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Gmail's API returns a native threadId per message. The opt-in live path already reads it (providers/live_gmail.py) and Gmail-over-IMAP X-GM-THRID is parsed in providers/live_imap.py, but capture discards both: the batch download in providers/gmail.py fetches only id, labelIds and raw, and no sidecar, Active cache entry, or database column records a thread. Generic IMAP has no native thread ID and needs the standard approach (JWZ-style): build a graph from Message-ID/In-Reply-To/References headers (RFC 5322), falling back to normalized-subject matching (strip Re:/Fwd: prefixes) when reference headers are missing or a thread spans providers/accounts differently. Store a thread_id (or equivalent grouping) so the web UI can query 'all messages in this thread' cheaply - avoid recomputing the graph on every page load.

Storage must respect invariant #1. A Gmail threadId is not in the .eml, so it belongs in the per-message sidecar (TASK-1.3), with any database column as a rebuildable cache. A header-derived grouping can be rebuilt from the .eml alone. docs/archive.md explains why References headers cannot prove account-wide thread membership; that limit matters for cleanup, not for UI grouping. A new column or table and a sidecar format change are STOP items that need sign-off.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Gmail-sourced emails capture and store the native threadId
- [ ] #2 IMAP-sourced emails are grouped into threads via References/In-Reply-To chain with a documented subject-based fallback
- [ ] #3 Thread membership is queryable without recomputing the full reference graph on each request
<!-- AC:END -->
