---
id: TASK-11
title: Encryption at rest for .eml files and database
status: To Do
assignee: []
created_date: '2026-07-24 20:29'
labels: []
milestone: m-4
dependencies: []
priority: low
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Carried over from ROADMAP.md's unscheduled Backlog section, verbatim: 'Encrypt .eml files (AES-256-GCM per file) and database. ownmail encrypt / ownmail decrypt commands. Key in system keychain. Mixed encrypted/unencrypted handled transparently. Alternative: use OS-level encrypted volumes (APFS, LUKS, BitLocker).'

Note the tension with the project's first invariant: encrypting the .eml files makes them unreadable by any other tool, which is most of what 'files are the source of truth' buys you. ROADMAP already recorded the alternative - an OS-level encrypted volume - and README's Privacy and security section and docs/archive.md already say ownmail does not encrypt the archive and recommend encrypted storage. The archive now also includes per-message .json sidecars and the Active cache, which any built-in encryption would have to cover. So the real first question is whether this should be built at all, not how.

Decide that before designing anything. If the answer is no, close this task with a decision record rather than leaving it open indefinitely. If yes, it touches both the archive format and key handling, so it needs sign-off per AGENTS.md's STOP list.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision is recorded on whether per-file encryption is worth building given OS-level volume encryption already covers the threat model
- [ ] #2 If built: mixed encrypted/unencrypted archives work transparently, and losing the keychain entry is a documented, non-silent failure
<!-- AC:END -->
