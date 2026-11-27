---
id: TASK-157
title: Fix rebuild resume messages and docs that name a nonexistent --only option
status: To Do
assignee: []
created_date: '2026-11-27 04:26'
labels: []
dependencies: []
priority: low
ordinal: 126000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The rebuild command selects a mode with --index-only, --date-only, --sidecars-only and --threads-only. It has no --only option. The dates backfill's resume message, a commands.py docstring and docs/archive.md tell users to run 'ownmail rebuild --only dates' or '--only sidecars', which argparse rejects. Point every reference at the real flags, or replace the flags with one --only choice if that reads better, and cover the resume message with a test.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every user-facing rebuild instruction names a flag the CLI accepts
- [ ] #2 A test fails if the dates resume message names an unknown option
<!-- AC:END -->
