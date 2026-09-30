---
id: TASK-78
title: Correct per-account archived totals after duplicate downloads
status: In Progress
assignee:
  - Ownmail IC2
created_date: '2026-09-14 03:58'
updated_date: '2026-09-30 10:34'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The per-account download summary adds backup success_count to the prior archive count, but success_count also includes content-dedup skips. The summary can therefore overstate archived messages. Read the final account count when reporting archive size.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per-account archived totals equal the stored message count after a download containing content duplicates.
- [ ] #2 A regression test covers successful downloads that do not add archive rows.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve the reviewed base 384a8b941178e7322196d8a3bd53a6ae069c59a4 on isolated branch fix/account-archive-totals. Commit this task-only claim and plan before production or test changes.
2. Change only the two cmd_download per-account Total archived calculations to read archive.db.get_email_count(account) after backup returns. Retain the prior-count display, returned success/Downloaded counters, overall summary, accountless semantics, provider behavior and TASK-98 interruption/cleanup.
3. Extend TestCmdDownloadSources with Gmail and IMAP successful duplicate-only/no-row-growth cases and per-source assertions in the existing distinct/shared-account regression. Establish failures on unchanged production code, then verify final committed account counts and all retained download/interruption behavior with synthetic fixtures.
4. Run focused tests, repository Ruff check/format-check and deptry, author self-review against the original base, and the complete required-browser pre-push coverage gate in private runtime state. Reserve/report the shared browser interval immediately before the full gate and release it on actual exit; other isolated checks need no slot.
5. Record only verified acceptance criteria and finish with normal local commit hooks and a clean branch. No main mutation, merge/rebase, publication, real mail/credential/service access, denied TASK-37/95/125 work, schema or dependency changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: affects the default EmailArchive.backup path only. The overall summary already reads the database count; the per-account 'Total' and 'Downloaded' lines in cli.py still add success_count, which includes content-duplicate skips.

Owner: Ownmail IC2. Branch: fix/account-archive-totals. Review base: 384a8b941178e7322196d8a3bd53a6ae069c59a4, preserving completed TASK-98 and TASK-110. TASK-124 remains preserved separately. The execution-order table selects this item immediately after TASK-95; no dependencies are declared. The approved preflight verified an in-memory call of the exact candidate cmd_download with mocked archive, database, providers, authentication and expiry: ten unchanged stored rows plus two successful duplicate skips report twelve per account for both Gmail and IMAP, while the overall summary correctly reports ten. EmailArchive.backup intentionally counts duplicate skips as successful operations and commits before returning; the existing get_email_count(account) already supplies the correct display count. The bounded fix changes no counting policy or archive authority. Existing distinct/shared-account CLI coverage models successes exceeding row growth but omits per-account totals, so it will be strengthened rather than duplicated. Only the two CLI total calculations, TestCmdDownloadSources regressions and this task ledger are owned. Author self-review is the ordinary-fix review requirement. Next action: commit the task-only checkpoint with normal hooks before editing code.
<!-- SECTION:NOTES:END -->
