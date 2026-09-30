---
id: TASK-64
title: Fix CLI Trash listing with database result rows
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-13 08:07'
updated_date: '2026-09-30 11:51'
labels:
  - cli
dependencies: []
priority: low
type: bug
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The trash command unpacks six values from get_trashed_emails, although the database returns additional date and snippet fields (and now an attachment flag). Listing a nonempty Trash raises ValueError. This predates TASK-63; existing CLI tests hide it by supplying six-field mock rows. Reproduced with a temporary synthetic database.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The trash command lists a nonempty Trash using rows returned by ArchiveDatabase, including the correct trash date, sender, and subject.
- [x] #2 A regression test uses the real database row shape and fails against the old unpacking.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Claim TASK-64 on isolated branch fix/cli-trash-listing-rows from clean tested review base 1126bfa054c47c10d431536496a4a06fe7e568b0. Commit this task-only plan with normal hooks before changing code or tests; retain this review base for final review.
2. Extend the existing TestCmdTrash listing regression to use ArchiveDatabase rows from a disposable synthetic database, with distinct message and trash dates and populated metadata/attachment flag. Preserve a failing baseline against the six-field unpacking. Correct the other existing listing mocks to the documented nine-field row shape and retain placeholder, truncation and 50-row pagination assertions.
3. Change only cmd_trash's listing unpacking to consume the existing nine-field database contract and display trashed_at. Preserve metadata formatting, empty-list output, result limit and remainder notice. Do not change database/schema or trash, delete, expire, restore, provider, credential or sanitizer behavior.
4. Run focused and retained CLI/database checks with private runtime fixtures, Ruff check and format-check, deptry and author review. Review the complete task diff against the fixed base; use Astra Ultra review support if useful. Verify listing cannot invoke deletion/expiration and that the regression fails on the original code.
5. Preserve a reviewed local implementation checkpoint, then run the complete required mandatory-browser pre-push gate after TASK-56 releases Chromium. Keep the existing coverage floor, test selection, assertions and timeouts. Close the task only after required checks pass, with accurate ledger evidence and normal hooks. No main changes, integration, rebase/merge, publication or next task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise and worth verified before claim on 1126bfa054c47c10d431536496a4a06fe7e568b0: the actual ArchiveDatabase.get_trashed_emails returns nine fields, but cmd_trash's nonempty listing unpacks six and raises ValueError. A disposable synthetic database reproduced the crash with different message and trash dates, a subject/sender/snippet and an attachment flag; listing left database bytes unchanged and invoked neither deletion nor expiration. The three existing nonempty listing tests hide the mismatch by supplying six-field mock tuples. The web Trash reader already consumes the correct nine-field contract, so no database API or schema change is needed. Independent Astra Ultra preflight agrees this is a bounded ordinary fix with no unresolved owner-policy or STOP-list decision.

The manager explicitly assigned TASK-64 after TASK-112's dependency on blocked TASK-111 and TASK-9's unresolved export scope were identified. TASK-64 itself is To Do/unassigned with no dependencies at claim. Owned scope is only cmd_trash listing unpacking in ownmail/cli.py, existing TestCmdTrash listing tests in tests/test_cli.py, and this ledger. All fixture data is synthetic; no physical email files or real trash actions are needed. TASK-56 retains the browser interval, and blocked TASK-37/95/111/125 plus integration/publication remain outside scope.

Task-only claim/plan checkpoint 1503a65583aa391226bccf1bbcbd878fc7a390b3 was committed with normal hooks before any test or production edits. The existing TestCmdTrash listing test now obtains actual nine-field rows from a disposable ArchiveDatabase, with distinct message/trash dates, sender, subject, snippet and attachment flag. The other nonempty listing mocks now use the same row contract; placeholder checks remain, pagination verifies 50 displayed rows and get_trashed_emails(limit=50), and listing asserts deletion/expiration were not called. Against the unchanged production code, these tests produced three failures and three passes. The one-line unpacking fix then made all six cases pass. All 216 retained CLI/database tests passed; Ruff check, format-check, deptry and whitespace checks passed. The formatter only wrapped the owned test changes.

Author review verified that production code differs from the fixed review base only in cmd_trash's listing unpacking. The existing nine-field contract matches the web Trash reader, and output formatting, limits, placeholders, empty-list handling and destructive-action dispatch are unchanged. Test changes are contained within TestCmdTrash. Fresh independent Astra Ultra review found no correctness findings, blocking test gaps or scope/approval issue. All fixtures were synthetic, with no physical email files or real account operations. A fresh private development environment and task-specific runtime directories are prepared. The complete required mandatory-browser pre-push gate remains unrun while TASK-56 owns Chromium, so the task remains In Progress despite verified acceptance behavior.

Next action: run the prepared complete mandatory-browser pre-push gate after TASK-56 releases Chromium; record the actual aggregate result and close with normal hooks only when that gate passes.
<!-- SECTION:NOTES:END -->
