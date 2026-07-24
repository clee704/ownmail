---
id: TASK-6.1
title: 'Derive thread grouping: Gmail threadId + IMAP Message-ID/References chain'
status: To Do
assignee: []
created_date: '2026-07-24 04:59'
updated_date: '2026-07-24 05:10'
labels: []
milestone: m-3
dependencies: []
parent_task_id: TASK-6
priority: medium
ordinal: 12
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Gmail's API returns a native threadId per message for free, but gmail.py currently only pulls format=raw RFC822 bytes and never captures it - straightforward win there. IMAP has no native thread concept and needs the standard approach (JWZ-style): build a graph from Message-ID/In-Reply-To/References headers (RFC 5322), falling back to normalized-subject matching (strip Re:/Fwd: prefixes) when reference headers are missing or a thread spans providers/accounts differently. Store a thread_id (or equivalent grouping) so the web UI can query 'all messages in this thread' cheaply - avoid recomputing the graph on every page load.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Gmail-sourced emails capture and store the native threadId
- [ ] #2 IMAP-sourced emails are grouped into threads via References/In-Reply-To chain with a documented subject-based fallback
- [ ] #3 Thread membership is queryable without recomputing the full reference graph on each request
<!-- AC:END -->
