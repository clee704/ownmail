---
id: TASK-6.1
title: 'Derive thread grouping: Gmail threadId + IMAP Message-ID/References chain'
status: In Progress
assignee:
  - codex
created_date: '2026-07-24 04:59'
updated_date: '2026-11-26 21:49'
labels: []
milestone: m-3
dependencies: []
documentation:
  - doc-11
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 0c6bd26.
1. Verify current capture, sidecar, Active cache and rebuild paths; prepare a concrete storage/grouping proposal.
2. Obtain maintainer sign-off for the schema and sidecar changes before implementing behavior.
3. After approval, implement durable thread metadata and rebuildable indexed membership, with reference-chain and subject-fallback tests.
4. Self-review the full diff from the review base, run the required pre-push gate, and deliver through a PR.
Scope: storage and membership lookup for archived and Active mail. Threaded list rendering, thread-level bulk actions and server cleanup policy are out of scope.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Selected as the first eligible unfinished task in doc-4; the working tree was clean and no task was In Progress. Preparing the schema/sidecar proposal only until explicit sign-off. All acceptance criteria remain unverified.

Proposal: backlog/docs/doc-11 - Thread-grouping-storage-proposal.md. It specifies optional top-level native thread metadata, one derived thread_members table spanning owned and Active IDs, an offline resumable backfill, exact reference links and conservative subject fallback.
Read-only survey confirmed the premise. Live providers already expose native IDs; capture and Active storage discard them. Existing owned messages are skipped during refresh, so historical native-ID enrichment is explicitly excluded. Existing label-only writers replace whole sidecars; retaining other metadata is required within this implementation.
Approval remains required before schema, sidecar or behavior edits. Next action: obtain maintainer approval of doc-11, then implement on a branch and open a PR. No acceptance criterion has been met.

Proposal self-review completed against 0c6bd26, including provider ID normalization, sidecar retention, offline backfill, Active transitions and read-only compatibility. The required pre-commit run -a --hook-stage pre-push passed with the unchanged production code. This checkpoint changes documentation only; implementation and all acceptance criteria remain pending approval.

2026-11-26 resume. Re-verified doc-11 against ddfa91b. Code changed since 0c6bd26 does not touch thread storage: ActiveCache.put, live_sync capture and legacy downloads still discard thread_id, and write_labels still replaces the whole sidecar. Its callers (relabel, update-labels, sidecar reconcile) do not select live-captured files under current queries, so the provenance loss doc-11 flags is untriggerable today and needs no separate task.

Pending decision, blocking implementation:
1. Recommended: header-only grouping. A derived thread_members table built from .eml Message-ID/References/In-Reply-To plus doc-11's subject fallback. Drops native thread ID capture (AC #1 would be rewritten). Existing mail has no stored native IDs and cannot get them offline, so headers are the only signal for the archive as captured. This avoids the sidecar, Active JSON and capture-path changes. It still adds a table, which needs sign-off.
2. doc-11 as written: native Gmail IDs in sidecars and Active JSON plus header grouping. Groups new Gmail mail closer to Gmail's own threads, such as same-subject notifications without References. Only new captures benefit, and it touches both capture paths, the sidecar format and the Active cache.
3. Close the TASK-6 tree and keep flat lists.
Next action: record the maintainer's choice here, then implement on a branch and open a PR.
<!-- SECTION:NOTES:END -->
