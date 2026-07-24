---
id: TASK-10
title: Headless server support — encrypted file fallback for keyring-less hosts
status: To Do
assignee: []
created_date: '2026-07-24 20:29'
labels: []
milestone: m-4
dependencies: []
priority: low
ordinal: 51
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Carried over from ROADMAP.md's unscheduled Backlog section: 'Encrypted file fallback for servers without a desktop keyring.'

keychain.py currently requires a working keyring backend (macOS Keychain, Windows Credential Locker, or a Linux Secret Service provider). On a headless Linux box - the natural place to run ownmail on a schedule - there's usually no D-Bus session and no Secret Service, so setup and every subsequent run fail with no usable fallback. Add an encrypted-file credential store used only when no keyring backend is available, with the passphrase supplied by env var or prompt.

Touches credential handling, which is a STOP-and-ask area per AGENTS.md: get the design signed off (key derivation, file location/permissions, how the passphrase reaches a cron job without ending up in a process listing) before implementing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Credentials can be stored and loaded on a host with no keyring backend available
- [ ] #2 Keyring remains the default when one is available; the file fallback is opt-in or auto-detected, never silently preferred
- [ ] #3 Credential file is encrypted at rest with restrictive permissions, and the passphrase never lands in argv or logs
<!-- AC:END -->
