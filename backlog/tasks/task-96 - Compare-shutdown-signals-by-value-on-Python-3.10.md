---
id: TASK-96
title: Compare shutdown signals by value on Python 3.10
status: In Progress
assignee: []
created_date: '2026-09-15 03:58'
updated_date: '2026-09-15 03:58'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The detached-download shutdown test receives SIGINT correctly but fails on Python 3.10 because the handler records the numeric signal while the assertion compares its text with the enum string. Compare numeric values so the test verifies the received signal across supported Python versions.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The shutdown test compares the received signal value with SIGINT without relying on enum string formatting
- [ ] #2 Focused shutdown tests and repository checks pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
CI run 34925231956 failed only at the shutdown marker assertion on Python 3.10; 3.11 and 3.12 passed. Python documents IntEnum.__str__ changing to int.__str__ in 3.11: https://docs.python.org/3/library/enum.html#enum.IntEnum. The test now parses the numeric marker before comparison. All 9 focused shutdown tests pass on Python 3.14.6. Restoring Enum.__str__ on signal.Signals reproduces the old assertion failure and passes with the corrected assertion. No local Python 3.10 interpreter was found; the supported-version CI matrix must verify that runtime after push. Full repository checks and commit remain pending. This CI compatibility fix is separate from Mail ownership.
<!-- SECTION:NOTES:END -->
