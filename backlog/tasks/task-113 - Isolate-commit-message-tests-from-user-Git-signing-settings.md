---
id: TASK-113
title: Isolate commit-message tests from user Git signing settings
status: To Do
assignee: []
created_date: '2026-09-24 18:50'
updated_date: '2026-09-26 02:23'
labels: []
dependencies: []
references:
  - tests/test_check_commit_msg.py
priority: high
type: bug
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The temporary repositories in tests/test_check_commit_msg.py inherit user Git signing settings. With commit signing enabled and a signer unavailable, both range tests fail while creating fixture commits before exercising the checker. All 13 tests in this file pass when signing is disabled only for the test process. Keep fixture behavior independent of the developer's signing configuration.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The range tests pass with inherited commit signing enabled and an unavailable signer, without launching a signing prompt.
- [ ] #2 Test isolation preserves the developer's Git configuration and signing behavior for real repository commits.
<!-- AC:END -->
