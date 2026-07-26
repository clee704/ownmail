---
id: TASK-15
title: Decide whether client-side deletions should reach the archive before purge
status: Done
assignee: []
created_date: '2026-07-24 22:46'
updated_date: '2026-07-24 22:59'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Dissolved into TASK-14 rather than implemented separately.

## Answer changed, 2026-07-26

doc-6 closed this by making it a config choice: trash in the download filter meant deletions were captured, out meant they were not. That is no longer the resolution. TASK-14.1 now fixes trash as permanently excluded, so this task's question gets a direct answer rather than a knob:

**Client-side deletions do not reach the archive.** 'Delete' means 'I do not want this', which was this task's first option all along.

The deciding argument is structural rather than philosophical: purge moves a message to server Trash, so a download filter that admits trash never lets a purged message leave the purge sweep set, and the sweep cannot converge. Full reasoning in TASK-14.1 under WHY TRASH IS FIXED RATHER THAN CONFIGURABLE.

This routes to AC #3, not AC #2: the loss window must be documented so it is a known choice. Both ACs stay unticked — TASK-14.1 owns the work.

Scope of that gap, corrected same day: it is narrower than 'anyone whose delete means file-it-away'. If a client's delete moves mail to an ORDINARY folder, ownmail downloads it by default like any other folder, and excluding it is a normal named exclusion — the general mechanism already covers that workflow. The gap applies only to the provider's designated discard location, which is the one place where 'I put it here' means 'destroy this'. So what config.example.yaml has to say is specific: mail you delete into Trash is never archived, and if you want it kept, delete it into a folder instead.

The question 'should client-side deletions reach the archive?' was filed as a code decision. Under TASK-14's two-knob design (optional purge + configurable download filter) it stops being one: it is simply whether 'trash' appears in the configured download filter. Excluded (the default) means deletions stay deleted and never enter the archive; removed from the filter means Trash is downloaded and deletions are captured within the provider's retention window.

No behaviour was decided away - the choice is now a documented config knob rather than a hardcoded query string, which is what the original task was asking for. TASK-14 AC #8 covers the default value and AC #12 covers documenting it.
<!-- SECTION:NOTES:END -->
