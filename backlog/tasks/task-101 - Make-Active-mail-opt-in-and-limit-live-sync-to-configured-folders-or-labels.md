---
id: TASK-101
title: Make Active mail opt-in and limit live sync to configured folders or labels
status: In Progress
assignee: []
created_date: '2026-09-21 05:34'
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
- [ ] #1 Omitted or false Active configuration uses the legacy incremental request path, verified by first-run and unchanged-repeat command counts and by forbidding live/cache work.
- [ ] #2 Opt-out and re-enable behavior are documented and tested; previously cached and owned mail is preserved, and stale or excluded data is not presented as freshly synchronized.
- [ ] #3 Explicit Active folder/label scope avoids per-message metadata and body reads over excluded retained archives while preserving the selected ordinary-archiving behavior.
- [ ] #4 Configuration, CLI and web entry points agree; lifecycle transitions, ambiguous scope, partial failures, scope changes and resume are covered.
- [ ] #5 Independent review and required full pre-push checks pass, and changes are committed with a clean working tree.
<!-- AC:END -->
