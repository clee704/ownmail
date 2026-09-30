---
id: TASK-116
title: Make OR precedence match the search help
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-27 08:16'
updated_date: '2026-09-30 05:59'
labels:
  - search
  - bug
dependencies: []
priority: medium
ordinal: 10500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
FTS5 binds implicit AND tighter than OR, so `attachment:pdf report OR invoice` means (PDF attachment AND report) OR invoice. The help page's Examples table says it finds PDFs with report or invoice, but the actual search can also return invoice mail without a PDF attachment.

Use the documentation-only solution and preserve current search semantics. Preflight through ArchiveDatabase.search verified `attachment:pdf report OR attachment:pdf invoice` as the working PDF example. The earlier proposed `attachment:pdf (report OR invoice)` conjunction fails through the actual search path and must not be advertised. Correct the Boolean and Example rows together: show text negation with positive search context, use a verified standalone grouping example, and describe the fixed 2024 date literally rather than as "this year".

Text terms and attachment-name terms use the existing FTS behavior. Since TASK-21, SQL-applied filters apply to the whole search and cannot be OR alternatives. Keep production query/database behavior unchanged; confirm every edited example through real ArchiveDatabase.search over synthetic fixtures.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The help page describes OR precedence as search applies it, and every Boolean and Example row returns what its description says
- [ ] #2 A test runs the documented OR example through search() and asserts its result
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve the documentation-only premise already verified through ArchiveDatabase.search: repeat attachment:pdf on each OR branch; keep production query/search behavior unchanged. Reconfirm the exact selected example results on this common claim base using synthetic fixtures before editing the template.
2. Correct only the assigned help template: explain that implicit AND binds more tightly than OR, give text negation positive context, use a standalone grouping example, and describe the fixed 2024 cutoff literally.
3. Cover every Boolean and Examples row plus the edited grouping row through actual ArchiveDatabase.search with exact synthetic result sets, including PDF/no-PDF and unrelated-PDF decoys. Extend the existing help-route test to confirm the served examples and precedence wording. Mutation-check the original misleading OR example and restore source.
4. Use an isolated environment for this source and private caches. After the quiet-window release, commit this task-only plan checkpoint with normal hooks before implementation. Run focused checks, request the coordinated full-suite/pre-push slot only when ready, then complete required coverage/browser/lint/format/dependency gates.
5. Self-review the whole task diff against the recorded review base, update verified acceptance/notes, and finish with clean local commits. Wait for parent remote/branch push coordination before publishing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner: Ownmail IC1. Reserved for TASK-116. Review base: da018d5d1dd309ee5767ac8483fc746d7ff3155f. Planned branch: fix/search-help-boolean-examples.
Intended write scope: ownmail/templates/help.html; tests/test_database.py for actual ArchiveDatabase.search regressions; help-route-only assertions in tests/test_web.py; this task file. Production query/database/search code is read-only. IC2 owns TASK-16's archive IMAP LIST parser and tests/test_imap_provider.py. README and the integration checkout are reserved for integration coordination.
Start from the common committed claim base after both task claims. Use an isolated local worktree in the IC's own writable workspace. Integrate TASK-116 before TASK-16; serialize full suites, browser validation and commit hooks through the coordinator. Preserve every other task and implementation scope.
The selected solution is truthful documentation plus regression coverage. The failing parenthesized PDF conjunction is explicitly excluded; do not change parser precedence to make it work. Scope excludes schema, credentials/OAuth, runtime dependencies, real mail operations and publishing.
Next action: IC1 rechecks the task premise and verified example results on the common claim base, then confirms or updates this bounded plan before implementation.

IC1 confirmed current clean common claim base 705aa580b8c0b14905471942918834115329d533 and created the assigned isolated branch. Review base da018d5d1dd309ee5767ac8483fc746d7ff3155f is retained across task checkpoints. The earlier read-only evidence distinguishes the working repeated-PDF qualifier from the failing parenthesized conjunction; no parser repair is part of this task. Current execution scope is light setup and plan preparation pending the coordinated quiet-window release. A bounded Astra Ultra support agent is inspecting only the intended fixture matrix through light reads, with no edits or tests.

Premise rechecked on the common claim base through the actual ArchiveDatabase schema, indexing and search methods using only an in-memory database: all 12 selected Boolean/Example/grouping queries returned their exact expected synthetic IDs. The original unqualified invoice OR branch returned the attachment-free invoice decoy; the proposed repeated qualifier excluded it. The date case included midnight at the cutoff and a later year while excluding the pre-cutoff row and body-only urgent decoy. Positive-context phrase exclusion distinguished exact from separated words. Astra Ultra fixture support completed read-only; expectations were independently executed by IC1. This task-only plan checkpoint is ready before implementation.
<!-- SECTION:NOTES:END -->
