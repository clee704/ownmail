---
id: TASK-113
title: Isolate commit-message tests from user Git signing settings
status: Done
assignee: []
created_date: '2026-09-24 18:50'
updated_date: '2026-09-27 05:48'
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
- [x] #1 The range tests pass with inherited commit signing enabled and an unavailable signer, without launching a signing prompt.
- [x] #2 Test isolation preserves the developer's Git configuration and signing behavior for real repository commits.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Disable commit signing in the fixture repository's local config, alongside the existing user.name/email settings. Local config overrides global and system settings for that temporary repository only, so the developer's own config is untouched. Verify with a temporary global config that enables signing through a nonexistent signer. Review base: a9ae4f9.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The fixture repository now sets commit.gpgsign=false in its own .git/config. Local config overrides global, system and included settings, so fixture commits are unsigned while the developer's configuration and real commits keep their signing behavior. Verified with GIT_CONFIG_GLOBAL pointing at a config that enables signing through a nonexistent signer: all 13 tests pass with the change, and both range tests fail without it. Settings forced through git -c or GIT_CONFIG_COUNT outrank local config and are out of scope.
<!-- SECTION:NOTES:END -->
