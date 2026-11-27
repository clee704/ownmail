---
id: TASK-6.1
title: Derive thread grouping from Message-ID/References headers
status: Done
assignee:
  - codex
created_date: '2026-07-24 04:59'
updated_date: '2026-11-27 17:44'
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
- [x] #1 IMAP-sourced emails are grouped into threads via References/In-Reply-To chain with a documented subject-based fallback
- [x] #2 Thread membership is queryable without recomputing the full reference graph on each request
- [x] #3 Gmail and IMAP messages group by the same header rules, and rebuilding from .eml files reproduces membership without contacting a provider
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 0c6bd26 (proposal); implementation branch feat/thread-membership from f2ed215.
1. Done: proposal and maintainer sign-off on 2026-11-26 for header-only grouping (doc-11).
2. Done: grouping module, thread_inputs and thread_members schema, input writes on every index path.
3. Done: refresh at command batch boundaries, rebuild --threads-only backfill, membership lookup.
4. Done: rules and command documented, full diff reviewed from 0c6bd26, pre-push gate, PR.
Scope: storage and membership lookup for owned and Active messages. Out of scope: native provider thread IDs, list rendering, visibility rules, thread-level actions and cleanup policy.
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

2026-11-26: maintainer approved header-only grouping. Replaced AC #1 (native threadId capture) with a header-rules and rebuild criterion; doc-11 now records the approved design and why native IDs were dropped.

Implementation on feat/thread-membership. Phases: thread_inputs and grouping (e86ef97, 8e2d471); refresh, rebuild --threads-only backfill, lookup, docs (a4cd087, f8ebdc8, d60a18e). The CLI has per-mode rebuild flags, so the backfill is --threads-only; the pre-existing docs naming a nonexistent --only option are TASK-157.

Independent review (Opus 5.5 and gpt-6.2-sol) of the full diff. Fixed: 8-bit bytes in identifiers failed index writes and could stop the Active cache from opening (identifiers are printable ASCII now); refresh opened the Active cache, re-parsing every Active message and failing for a moved archive (it reads stored Active inputs now); Active copies counted twice when choosing a fallback target; fallback could merge two originals (fallback now applies only to a reply whose reference component holds no other message); two quadratic loops; forced backfill resume message; a later source's failure skipped the download refresh; a backfill test that could not fail; parser exceptions aborted the backfill.
Dismissed: concurrent refreshes from overlapping commands can publish older membership (doc-11 accepts lag and the next refresh corrects it); tokens extracted from malformed text such as <<a@x>> (the extracted token is well-formed and in practice names the same message); --threads-only ignoring --file and --pattern (the backfill only reads files and is idempotent).

Convergence review of the fix commits (both models). Fixed: a relative active_cache_dir broke the read-only URI (469cab7); copies of one unlinked reply in two accounts bridged two originals, and a damaged Active index raised ValueError out of refresh (686b216).
Dismissed: refresh reading an Active index whose marker names another archive (the only triggers are a misconfigured shared cache dir, which ActiveCache already refuses on every download, or a moved archive whose cache still holds its own messages); a refresh failure in the download finally replacing an earlier source error (needs two coincident failures, the refresh error is real and reported, and the original stays chained).

Focused check of 686b216 (gpt-6.2-sol). Dismissed: two messages sharing a Message-ID where only one carries References can skip an ambiguous candidate (they are not copies of one message, no originals are bridged, and the result predates the fix); an Active row whose references_json holds JSON null raises TypeError in grouping (the only writer stores a JSON list, and the Active index rebuilds from files when a download next opens it). Review converged.
AC evidence: #1 reference-chain and subject-fallback tests in tests/test_threads.py, rules documented in doc-11 and docs/archive.md; #2 thread_members is stored and indexed, and test_lookup_reads_the_index_without_parsing reads it with parsing disabled; #3 every provider indexes through the same parse_file inputs, and test_backfill_from_files_reproduces_indexed_membership regroups from .eml files alone.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Thread grouping now derives from Message-ID, References and In-Reply-To headers for every provider, with a subject fallback limited to unlinked replies that find exactly one candidate thread. Each index database stores per-message inputs in thread_inputs; the archive database holds thread_members for owned and Active messages, refreshed once per download, import, scan and rebuild. rebuild --threads-only backfills inputs for older archives (Ctrl-C safe, resumable, --force re-derives all). ArchiveDatabase.get_thread_member_ids returns a message's thread from the index alone, and a database without the new tables yields the message alone. Native provider thread IDs are not stored (doc-11). Delivered through a PR because it adds tables.
<!-- SECTION:FINAL_SUMMARY:END -->
