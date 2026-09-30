---
id: TASK-129
title: PDF export for archived messages
status: In Progress
assignee:
  - Ownmail backend IC
created_date: '2026-09-30 16:53'
updated_date: '2026-09-30 17:39'
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
<!-- SECTION:NOTES:END -->
