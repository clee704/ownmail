---
id: TASK-98
title: Stop all download sources after Ctrl-C
status: To Do
assignee: []
created_date: '2026-09-21 03:16'
updated_date: '2026-09-26 02:23'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When a provider download catches KeyboardInterrupt and returns interrupted=True, cmd_download prints Download Paused but continues authenticating and downloading later configured sources. A single Ctrl-C should stop the overall command after retaining completed work and reporting the partial result.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An interrupted source stops the source loop before constructing or authenticating the next provider.
- [ ] #2 Completed saves and counters remain available, the command returns failure, and the overall summary identifies interruption.
- [ ] #3 A multi-source regression covers interruption during live enumeration and verifies later sources are untouched; full pre-push checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed in real terminal history and a synthetic two-source invocation: the first result was interrupted=True, yet both providers authenticated and both backups ran. The loop at ownmail/cli.py:620 records interruption without breaking. This behavior predates TASK-28. No runtime behavior changed during diagnosis.

2026-09-25 review: cmd_download already returns failure when interrupted, but its summary does not name the interruption. The web Stop button sends SIGINT, so it is affected too.
<!-- SECTION:NOTES:END -->
