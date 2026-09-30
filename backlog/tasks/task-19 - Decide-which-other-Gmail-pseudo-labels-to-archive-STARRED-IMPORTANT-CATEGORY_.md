---
id: TASK-19
title: Decide whether to exclude recurring platform and workflow labels at capture
status: Done
assignee:
  - Codex
created_date: '2026-07-25 06:20'
updated_date: '2026-09-30 20:25'
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
- [x] #1 Decision recorded: add a per-source label exclusion option, or close as unnecessary, with reasoning against doc-8 and local label editing
- [x] #2 If added, the option accepts arbitrary label strings, defaults to empty, applies at capture alongside the TASK-103 status-label filtering, and cannot re-admit labels those filters drop
- [x] #3 If added, config.example.yaml and the docs describe it, and tests cover Gmail and IMAP sources
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add validated per-source exclude_labels with an empty default and exact-name matching at live and ordinary capture writes. Keep provider status filtering, eligibility, Active state, cursor fingerprints and existing sidecars unchanged.
2. Add synthetic regression controls for Gmail/IMAP paths, arbitrary strings and all-label omission; lifecycle/CHAT holds; no backfill/cursor reset; sidecar/index retry and local edits; and the existing reconcile preview consequence. Demonstrate meaningful failures before the implementation and with bounded mutations.
3. Document irreversible omission of label metadata, rebuild limits and reconcile evidence prominently in config.example.yaml and archive docs. No actual source settings change.
4. Freeze the full diff from 5aa3dba2381ff6009658b1262dac9bc21d967270 for independent review. Resolve findings, run required normal hooks/full gate with browser exclusivity, then update acceptance and integrate tested code with backups.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-30 premise/worth decision: add the opt-in option. Fixed status filters still retain categories and ordinary workflow labels; per-message local editing handles one-offs but repeats the same removal on every future capture. Gmail include_labels:false omits useful organization too, while download/Active exclusions select messages. The existing capture writers permit a small metadata-only filter with no schema or provider-query change. Default-empty preserves existing behavior and the owner chooses every omitted name; no automatic category policy. Live Gmail CHAT remains unknown and held, despite the older task example. Only future unsaved label snapshots are filtered. Omitted metadata cannot be reconstructed by rebuild or restored by removing the setting. Existing reconcile uses retained labels as filing evidence, so omission may change a later preview from report-only to bin candidate; separate --apply and current retention rules remain unchanged. No hidden provenance or new reconciliation policy. Source review and pure synthetic provider/classifier probes establish the premise without private data. Parent authorized this bounded engineering decision; TASK95 integrity and TASK6.1 design gates remain untouched.
Review base: 5aa3dba2381ff6009658b1262dac9bc21d967270. Implementation has not started at this checkpoint.

Implementation checkpoint: validated source exclude_labels is an exact-name, default-empty list. One six-line archive helper is used only at the ordinary capture sidecar write and the new live-capture sidecar construction. Provider extraction, Active data, eligibility, roles, failed-label handling, fingerprints/cursors, reconciliation and cleanup code are unchanged. Documentation prominently describes irrecoverable metadata omission and loss of filing evidence for later reconcile, retaining separate --apply. No actual source settings changed.
Validation: 44 dedicated synthetic cases plus 471 retained related cases passed together (515 total). The original implementation failed 24 feature regressions with 18 controls passing after correcting a Gmail test fixture's missing cursor. Three disposable-source mutations were caught: wildcard matching, re-filtering a saved capture sidecar, and resetting the live cursor. An initial late-label-failure test injected failure during listing, which correctly reports an incomplete scan rather than a per-message error; the final probe injects failure during the content lookup to exercise the intended retry/held-cursor path. All prior diagnostic outputs preserved outside the repository. Normal full pre-push gate and independent review remain required before task closure and main integration. No browser has been launched for this task.

Completion gate: independent focused review approved exact 3f1eb501ed65831d7b1028800baab70203421e54 against base 5aa3dba2381ff6009658b1262dac9bc21d967270 with no actionable findings and 27 independent synthetic checks. The unchanged mandatory full pre-push gate passed on that exact clean code/tree: 4,455 tests plus 370 subtests, 96.61% branch-inclusive coverage, zero failures/errors/skips. All 161 observed browser subprocesses exited successfully; the post-run private-profile process check was clear and the browser lease was released. Normal hooks passed. This closure changes only task metadata; no additional aggregate is needed for the unchanged tested code. No real source configuration was activated. TASK50 physical-iPhone acceptance and TASK95/TASK6.1 gates remain open and untouched.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-25 06:57
---
See doc-8 (Archival semantics) for the principle this knob serves: ownmail freezes metadata at capture and does not chase server-side changes. exclude_labels is how a user declares which of their labels are transient workflow state that should therefore not be frozen at all.
---
<!-- COMMENTS:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added optional exact-name per-source exclude_labels, defaulting to empty, at ordinary and live capture boundaries for Gmail API and IMAP. Existing owned labels, Active/lifecycle state, provider status filtering, failed-label holds and cursor behavior remain unchanged. Documentation prominently explains that omitted label metadata cannot be reconstructed by rebuild and may change later reconcile filing evidence; existing preview/--apply and retention rules are preserved. Dedicated synthetic tests, three caught mutations, independent review and the full mandatory gate passed. Ready for preserved-ref local integration of the tested code; no remote push or actual setting change.
<!-- SECTION:FINAL_SUMMARY:END -->
