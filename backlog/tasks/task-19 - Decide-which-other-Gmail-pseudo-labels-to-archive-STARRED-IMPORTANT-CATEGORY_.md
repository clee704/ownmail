---
id: TASK-19
title: Decide whether to exclude recurring platform and workflow labels at capture
status: To Do
assignee: []
created_date: '2026-07-25 06:20'
updated_date: '2026-09-26 02:24'
labels: []
dependencies: []
priority: low
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Filed 2026-07-25 as a config knob for Gmail pseudo-labels, with a design that filtered the index and kept every provider label in the sidecar. Later work settled most of that:

- TASK-5.3 drops UNREAD at capture (roles.EPHEMERAL_LABELS).
- TASK-103 drops Gmail STARRED and IMPORTANT, and IMAP \\Flagged and \\Important, at capture as mailbox status (roles.GMAIL_STATUS_LABELS and related sets). Star state is not archived, so the proposed canonical `flagged` role is no longer wanted.
- TASK-5.4 made sidecars hold ownmail-owned labels, including local edits, so a sidecar is no longer a record of what the server sent. Local label editing covers one-off removals.
- doc-8 describes `exclude_labels` as an inheritance rule applied at the handoff, and says it earns its keep only for recurring platform labels across many messages.

What remains: Gmail CATEGORY_* and CHAT labels, and user-created workflow labels such as `Waiting` or `To Read` that describe state at capture, still enter the archive. Decide whether a per-source exclusion list for such labels is worth adding. If local editing is enough, close this task with that reason.

The original design (filter the index, rebuild in both directions) is in this file's git history.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded: add a per-source label exclusion option, or close as unnecessary, with reasoning against doc-8 and local label editing
- [ ] #2 If added, the option accepts arbitrary label strings, defaults to empty, applies at capture alongside the TASK-103 status-label filtering, and cannot re-admit labels those filters drop
- [ ] #3 If added, config.example.yaml and the docs describe it, and tests cover Gmail and IMAP sources
<!-- AC:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-25 06:57
---
See doc-8 (Archival semantics) for the principle this knob serves: ownmail freezes metadata at capture and does not chase server-side changes. exclude_labels is how a user declares which of their labels are transient workflow state that should therefore not be frozen at all.
---
<!-- COMMENTS:END -->
