---
id: TASK-9
title: Email export (ownmail export --format mbox|pdf)
status: In Progress
assignee:
  - '@codex-task9'
created_date: '2026-07-24 20:29'
updated_date: '2026-09-30 16:57'
labels: []
milestone: m-4
dependencies: []
references:
  - backlog/tasks/task-129 - PDF-export-for-archived-messages.md
priority: medium
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Carried over from ROADMAP.md's unscheduled Backlog section. Sketched there as:

    ownmail export --format mbox --output backup.mbox
    ownmail export --format pdf --query "from:important@example.com"

Export archived emails out of ownmail, filtered by the existing search query syntax (query.py already parses from:/subject:/attachment: etc., so --query should reuse it rather than growing a second filter language). mbox is the straightforward case - stdlib mailbox module, and it's the format other clients import. PDF is a much bigger lift (HTML-to-PDF rendering, a new heavyweight dependency) and is worth splitting into its own task or dropping unless there's a concrete need; the Minimal dependencies invariant argues against pulling in a browser engine for it.

Scope is undecided: mbox-only first is the sensible cut. Also decide whether export includes Active messages or only archived ones, and whether sidecar labels are written into the output (for example as X-Keywords).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ownmail export --format mbox --output <file> writes a valid mbox importable by another client
- [ ] #2 --query filters the export using the existing search syntax, not a new one
- [x] #3 PDF export is either implemented, split into its own task, or explicitly dropped with the reason recorded
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 95251cc64f328890362757de49d194fa8ca256fe. Implement only archive-owned mbox export using stdlib mailbox, with an export parser/command and dedicated tests separate from TASK-37. Reuse parse_query and archive DB search (no 50-result cap), retaining existing Trash/date filtering and consulting verified existing Active membership only when ownership filters require it; never select cached-only bodies or fetch mail. Read original archived bytes and preserve headers/MIME/attachments apart from standard mbox framing/From escaping; synthesize no sidecar label headers. Validate queries before output creation. Build a temporary mailbox and publish via exclusive output creation; refuse existing files/symlinks, clean temporary/new incomplete output on interruption or output failure, and allow a clean rerun. Report unreadable/unsafe source paths while exporting readable matches, with a nonzero CLI result for partial export. Cover MIME/header fidelity, From-line framing, all-result selection, filters and ownership, unchanged source data, invalid queries, exclusive-output races, per-message read failures, output failures and Ctrl-C using synthetic fixtures. Record PDF split into linked TASK-129 to satisfy AC3. Run focused tests, mutation checks, full required pre-push gate and parent-coordinated independent review, then clean local-main integration through owner with normal hooks and preserved refs; no public push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise confirmed: no export CLI exists. Exact scope explicitly authorized: mbox-only, ordinary archive search semantics including Trash/date behavior, no synthesized label headers, no Active-only export. PDF is split into TASK-129 using the supported Backlog shared creation lock. Output remains a new user-selected artifact; source mail, credentials, ownership and schema stay unchanged. CLI changes are confined to a new export function/parser/dispatch, with TASK-37 functions excluded.
<!-- SECTION:NOTES:END -->
