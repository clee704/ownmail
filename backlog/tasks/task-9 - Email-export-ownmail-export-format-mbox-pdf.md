---
id: TASK-9
title: Email export (ownmail export --format mbox|pdf)
status: In Progress
assignee:
  - '@codex-task9'
created_date: '2026-07-24 20:29'
updated_date: '2026-09-30 17:24'
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
- [x] #1 ownmail export --format mbox --output <file> writes a valid mbox importable by another client
- [x] #2 --query filters the export using the existing search syntax, not a new one
- [x] #3 PDF export is either implemented, split into its own task, or explicitly dropped with the reason recorded
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 95251cc64f328890362757de49d194fa8ca256fe. Implement only archive-owned mbox export using stdlib mailbox, with an export parser/command and dedicated tests separate from TASK-37. Reuse parse_query and archive DB search (no 50-result cap), retaining existing Trash/date filtering and consulting verified existing Active membership only when ownership filters require it; never select cached-only bodies or fetch mail. Read original archived bytes and preserve headers/MIME/attachments apart from standard mbox framing/From escaping; synthesize no sidecar label headers. Validate queries before output creation. Build a temporary mailbox and publish via exclusive output creation; refuse existing files/symlinks, clean temporary/new incomplete output on interruption or output failure, and allow a clean rerun. Report unreadable/unsafe source paths while exporting readable matches, with a nonzero CLI result for partial export. Cover MIME/header fidelity, From-line framing, all-result selection, filters and ownership, unchanged source data, invalid queries, exclusive-output races, per-message read failures, output failures and Ctrl-C using synthetic fixtures. Record PDF split into linked TASK-129 to satisfy AC3. Run focused tests, mutation checks, full required pre-push gate and parent-coordinated independent review, then clean local-main integration through owner with normal hooks and preserved refs; no public push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise confirmed: no export CLI exists. Exact scope explicitly authorized: mbox-only, ordinary archive search semantics including Trash/date behavior, no synthesized label headers, no Active-only export. PDF is split into TASK-129 using the supported Backlog shared creation lock. Output remains a new user-selected artifact; source mail, credentials, ownership and schema stay unchanged. CLI changes are confined to a new export function/parser/dispatch, with TASK-37 functions excluded.

Implemented archive-only mbox export with exclusive output creation, original byte-based MIME/header preservation, search filters and verified membership, partial-read reporting and restart-safe failure cleanup. Added an opt-in FTS error path to the existing database search helper, preserving default callers: the synthetic leading text-negation probe previously printed an FTS syntax error and falsely succeeded with an empty export; it now fails before output creation. Valid combined negation and valid empty results are covered. AC1 and AC2 verified by 34 focused synthetic cases including the standalone module CLI, plus 489 retained CLI/database/query/ownership tests. Exporter focused statement and branch coverage is 100%. Four deliberate mutations (50-result cap, nonexclusive destination, swallowed FTS error, omitted Active membership) each failed the intended regression and were restored. Earlier MIME fixture comparison normalized CRLF only on its read side; corrected both comparisons to parsebytes. Leading negative CLI values use standard argparse --query=-term spelling. Required full pre-push gate and independent review remain pending; status stays In Progress.

Independent review of f51d4d2 found one P2: a label parameter equal to active combined with is:archived unnecessarily acquired Active membership. Added a parameter-aware ownership check and five unavailable-cache regression cases (three failed before the correction, two controls passed), plus genuine Active filters after parameter-free attachment clauses. All 41 focused cases now pass with exporter statement/branch coverage at 100%. Clarified that exclusive publication cleans up handled errors/Ctrl-C but abrupt termination can leave a partial output; no atomic-publication claim is made. Awaiting mutation check, normal-hook fix checkpoint, same-reviewer recheck and full required gate. Testing/hooks temporarily paused for the coordinator-requested bounded memory measurement; source edits remain local until release.

Resource pause released. The deliberate plain-clause zip mutation fails the two attachment-plus-ownership regressions; restored code passes all 41 export cases. Review correction is ready for same-reviewer recheck.
<!-- SECTION:NOTES:END -->
