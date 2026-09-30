---
id: TASK-129
title: PDF export for archived messages
status: In Progress
assignee:
  - Ownmail backend IC
created_date: '2026-09-30 16:53'
updated_date: '2026-09-30 18:26'
labels: []
milestone: m-4
dependencies:
  - TASK-9
references:
  - backlog/tasks/task-9 - Email-export-ownmail-export-format-mbox-pdf.md
priority: medium
type: feature
ordinal: 112000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Split from TASK-9 under its explicit PDF alternative. Add PDF export for archived messages selected with the existing query syntax when a concrete document-export need justifies the rendering cost. Keep mbox export independent. Select and document the rendering approach and output layout; follow the repository approval rule before adding any runtime dependency. Active-only cache export and label-header synthesis are outside this follow-up.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ownmail export --format pdf supports archived messages filtered with the existing --query syntax
- [ ] #2 The selected PDF renderer and output behavior are documented, with any required runtime dependency approved before introduction
- [ ] #3 Synthetic fixtures verify readable plain-text and HTML message output, headers, and clear attachment treatment without modifying source mail
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Planning checkpoint: inherited TASK9 head 121c55ac82027ffe28073a587fb6983f203fcce1; no implementation before TASK9 is Done and integrated. Keep To Do until that dependency closes, then merge the finished local master normally, pin the resulting implementation review base and claim this task before source edits. 1. Add PDF as a lazily selected export format using the already-declared Playwright/Chromium tooling as an explicitly optional renderer. Check Node, module and browser availability only for PDF; fail clearly before creating output when unavailable. Never install/download packages or browsers, alter dependency manifests, or change ordinary startup or mbox behavior. 2. Export one PDF per selected archived message to a new output directory; preserve existing query, ordering, Trash/date, owned-source and destination protections. Keep mbox independent and share only directly reused selection/source-read/publication helpers. Document output naming, empty/partial results, existing-directory refusal and restart-safe failure/interrupt cleanup. 3. Reuse reader MIME presentation, established decoders, sanitizer, body extraction and attachment descriptors through a small directly shared helper; use a dedicated printable template with visible subject/from/recipients/date, readable text or sanitized HTML, safe embedded CID images and an explicit attachment inventory. Do not embed attachment payloads, include Active-only bodies, synthesize label headers, or print the interactive reader UI. Keep message styles isolated by rendering each PDF separately. 4. Use a bounded Node runner with a private browser/context lifecycle, explicit Chromium sandbox, page JavaScript disabled, service workers blocked and strict resource blocking for remote and local-file loads; feed document content in memory, not an archive file URL. Use real sanitizer startup with install=False, never the test passthrough or automatic installation path. Surface sanitizer/render failures and release processes/temp output on failure or Ctrl-C. 5. Add synthetic CLI/query/ownership/output lifecycle regressions and real leased-browser checks for readable Latin/CJK text, long/wide HTML, headers, attachments and zero unauthorized resource/script activity. Verify failure tests with meaningful mutations. Obtain independent focused review and run the unchanged mandatory full gate; close only proven criteria, then integrate to clean local master normally with backups and exact tested-tree proof. No source mail, credentials, schema, remote push or unrelated task changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Targeted preparation found a compliant optional-renderer route. The coordinator explicitly resolved ordinary layout/support choices: one PDF per message retaining existing reader styling with strict remote-resource blocking is the minimal default, and existing Playwright/Chromium may be availability-checked and used only on the selected PDF path. The optional feature does not add a package, promote Playwright from devDependencies, install/update tooling, or make Node/browser startup mandatory for normal commands. Repository AGENTS requires approval for adding a runtime dependency; no such package change is planned. Missing renderer is a clear command failure, not an automatic installer. PDF provides readable local message documents alongside faithful mbox interchange. Concrete constraints verified with synthetic nonbrowser preparation: index-parser body text includes named text attachments, so reuse reader MIME presentation instead; the sanitizer uses a single message CSS scope, so separate PDFs avoid cross-message style interference. TASK9 is still In Progress, therefore no implementation or acceptance completion has started.

TASK9 is Done and integrated at b09e99c08c6af5e7c6d853a28340bda188022e29. Normally merged that exact master into the preserved ec80c86 plan branch; implementation review base is 8bac6425a142ab8e821fb82a27e6bf1745323af1. Claim TASK129 now; implementation has not yet started. Proposed cooperation boundary: backend owner owns ownmail/pdf_export.py, ownmail/pdf_renderer.js, ownmail/templates/pdf.html, minimal shared selection/source-read/publication extraction in ownmail/export.py, MIME presentation extraction in ownmail/web.py, tests/test_pdf_export.py and TASK129 metadata. Export contributor owns ownmail/cli.py export dispatch/parser only, README.md export documentation and tests/test_pdf_export_cli.py plus existing tests/test_export.py CLI expectations. Shared public boundary is export_pdf(archive, output: Path, query: str = "") -> tuple[int, list[tuple[str, str]]] from ownmail.pdf_export, matching mbox result semantics. Invalid query raises ValueError; missing renderer/destination/publication/renderer failure raises OSError; cancellation propagates. Source-read failures are reported as skipped messages. PDF is lazily imported only when selected. Output is a new directory of one PDF per message, not one merged report. Confirm exact file ownership through coordinator before concurrent source writes; no additional task or dependency change is introduced.

Renderer implementation checkpoint: added a lazily selected optional PDF module, bounded Node/Chromium runner and dedicated printable document. Selection, owned source reads and exclusive file publication reuse extracted TASK9 helpers; the reader MIME body extraction is AST-identical to the previous statements. Separate message contexts retain per-message styling, with JavaScript disabled, service workers blocked, offline routing, restrictive response CSP and explicit Chromium sandbox. Documents are staged locally, renderer output is validated before directory publication, and source read failures retain mbox-style partial reporting. Missing Node/browser or sanitizer failure is explicit; no installer or normal startup changes. Plain-text export does not start the HTML sanitizer. Initial extraction validation passed 381 retained mbox/reader tests. PDF plus retained mbox nonbrowser checks passed 66 cases; two added actual-process/missing-browser cases also passed, including synthetic Ctrl-C terminating its renderer child. Runtime-only sanitizer-failure and directory-race mutations each failed the intended regression; production files remain restored. Two actual Chromium/PDF validity/readability/security tests are written but queued behind TASK111's exclusive browser lease. Reviewed the disjoint CLI contribution b0dbf79 against its base: API/errors, lazy dispatch and preserved mbox scope agree; combine normally next. Independent renderer review, actual PDF/browser evidence and final unchanged full gate remain pending; keep In Progress and all ACs unchecked.

Independent renderer review found one P2 in timeout cleanup: inherited pipes could keep the final unbounded communicate blocked, and a SIGTERM-resistant descendant could survive after its leader closed the pipes. Corrected diagnostic capture to a temporary regular file, removed Popen context-manager/unbounded pipe waits, kept every wait finite, and force-stopped the owned POSIX group even after the leader exits. A second bounded SIGTERM lets Playwright force its own detached browser closed before group escalation. Windows cleanup targets the launched renderer PID and descendant tree with the OS taskkill utility, without new packages. Added timeout/Ctrl-C regressions for both inherited and closed output descriptors plus a SIGTERM-resistant leader. The initial focused PDF batch passed 31 tests; the expanded five-case actual-process matrix passed all five, with owned process cleanup verified. Actual-browser results remain separate: the original two-case batch exited 1 with one pass and one mixed Latin/Korean whitespace assertion failure; both Chromium processes closed and profiles cleaned. Independent pdfinfo, layout text extraction and visual inspection confirmed valid 1-page plain and 3-page HTML PDFs, all 100 ordered paragraphs, both table edges, attachment labels and no malicious canaries. Corrected only extraction whitespace normalization and strengthened ordered paragraph verification; preserved original failed evidence. Browser rerun and same-reviewer correction recheck are pending before reconciliation with TASK111 main and the final required full gate.
<!-- SECTION:NOTES:END -->
