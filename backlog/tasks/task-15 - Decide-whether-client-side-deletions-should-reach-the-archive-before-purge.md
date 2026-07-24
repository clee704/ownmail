---
id: TASK-15
title: Decide whether client-side deletions should reach the archive before purge
status: To Do
assignee: []
created_date: '2026-07-24 22:46'
labels: []
milestone: m-5
dependencies: []
documentation:
  - >-
    backlog/docs/doc-6 -
    Email-stack-architecture-—-ownmails-role-and-the-remote-drain.md
priority: medium
ordinal: 2
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Discovered while settling the stack in doc-6. Not part of the drain (TASK-14) - a separate gap in the two-path architecture.

The two paths are independent: ownmail pulls on its own schedule, while mail clients talk to the providers directly. So path B can destroy mail before path A captures it. gmail.py:130 hardcodes '-in:trash -in:spam' (and imap.py has DEFAULT_EXCLUDE_FOLDERS), which means a message deleted on a phone before ownmail's next sync is gone permanently, with no archive copy anywhere.

The decision is what 'delete' should mean:
- 'I do not want this' - current behaviour is correct, deletions are real and the archive is a record of mail you kept.
- 'Get it out of my inbox' - then Trash should be synced (at least optionally) so deletions land in the archive before the provider purges them, using Gmail's 30-day Trash retention as the capture window.

Either answer is defensible; the point is that it should be a conscious config choice rather than inherited from a hardcoded query string.

Related but distinct from TASK-5.2, which covers canonical naming/display of provider system folders in the UI, not whether their contents get archived at all.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded (in doc-6 or its own doc) on whether provider Trash is archived, with the reasoning
- [ ] #2 If adopted: Trash sync is configurable per source rather than hardcoded, and documented in config.example.yaml
- [ ] #3 If rejected: the permanent-loss window is documented so the behaviour is a known choice, not a surprise
<!-- AC:END -->
