---
id: TASK-101
title: Make Active mail opt-in and limit live sync to configured folders or labels
status: In Progress
assignee: []
created_date: '2026-09-21 05:34'
updated_date: '2026-09-21 05:59'
labels: []
dependencies: []
priority: high
ordinal: 102000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Active mail must require explicit opt-in. Omitted or false active_downloads must use the pre-Active incremental download path without live scans or cache initialization. Opt-out semantics must be clear and preserve existing data. Opted-in sources need folder/label scope controls that avoid repeated full work over retained server archives, with documented effects on ordinary archiving and safe lifecycle handling.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Omitted or false Active configuration uses the legacy incremental request path, verified by first-run and unchanged-repeat command counts and by forbidding live/cache work.
- [x] #2 Opt-out and re-enable behavior are documented and tested; previously cached and owned mail is preserved, and stale or excluded data is not presented as freshly synchronized.
- [x] #3 Explicit Active folder/label scope avoids per-message metadata and body reads over excluded retained archives while preserving the selected ordinary-archiving behavior.
- [x] #4 Configuration, CLI and web entry points agree; lifecycle transitions, ambiguous scope, partial failures, scope changes and resume are covered.
- [ ] #5 Independent review and required full pre-push checks pass, and changes are committed with a clean working tree.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Explicit opt-in dispatch and legacy first/repeat routing are implemented and verified. Active exclusions affect tracking only; ordinary eligible capture remains enabled. Provider enumeration separates capture candidates from tracked live mail. Cursor advancement waits for complete processing; unfinished out-of-scope candidates retain the prior cursor. Work is isolated from the running server until validation completes. Review base: 0ac9752.

Scoped provider and lifecycle regressions pass, including opt-out cache preservation, re-enable, exact scope validation, source/account isolation, scope changes, unknown/unfinished retry, explicit Gmail candidate 404, partial batches, dates and interrupts. Synthetic standard IMAP excluded Archive with 1,000 retained messages: unchanged enumeration 5 to 3 commands and 1,000 to zero metadata records. Active capture checkpoints are atomic per-source cache metadata; cache removal or scope change safely rescans. Independent OpenAI review fixes are verified. Anthropic review verified cursor/scope/404 design; its conditional alternate-writer concern is unreachable (only sync_live writes status in production), stale excluded cache retention is intended, and a metadata-save failure now permits other captures. Unresolved excluded states retain the cursor unless provider membership guarantees rediscovery; this conservative performance tradeoff is documented.
<!-- SECTION:NOTES:END -->
