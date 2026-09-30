---
id: TASK-11
title: Encryption at rest for .eml files and database
status: Done
assignee:
  - Codex
created_date: '2026-07-24 20:29'
updated_date: '2026-09-30 20:42'
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
- [x] #1 A decision is recorded on whether per-file encryption is worth building given OS-level volume encryption already covers the threat model
- [x] #2 If built: mixed encrypted/unencrypted archives work transparently, and losing the keychain entry is a documented, non-silent failure
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve the original description and both acceptance criteria; use the explicit decision-only alternative after the bounded engineering worth assessment at base 28ceda92c78415a36fe5dc5def1a9b866e141df9.
2. Record the limited at-rest threat model, existing plaintext-storage and backup disclosures, coverage/interoperability/recovery costs, and decision not to add built-in encryption. Do not assert actual volume encryption or satisfaction of an owner threat model.
3. Close this ledger-only decision through the supported workflow, run normal hooks, verify exact non-ledger equality to the tested code, preserve backup refs, and fast-forward clean local master only if the expected base and clean state remain unchanged. No encryption, schema, source, key/access handling, security settings, or remote changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-30 engineering worth decision: decline built-in per-file and database encryption for the currently documented at-rest scope. The task explicitly permits closing with a decision record when the answer is no. This preserves the existing storage/security contract; it does not adopt a new security policy or declare the archive encrypted.
Threat-model boundary: the task names OS-level encrypted volumes as its existing alternative. That alternative addresses offline access to protected storage when its encryption key is unavailable. Neither that premise nor this decision establishes protection against an unlocked host, authorized processes, or plaintext copies exported outside protected storage. No broader owner threat model is specified in the task/design context. No actual volume encryption, backup protection, security settings, keychain, credentials, or satisfaction of the user's threat preferences was inspected or verified.
Existing disclosure remains authoritative and unchanged: README's Privacy and security section says messages, attachments, label sidecars, search index and account configuration can contain sensitive information, recommends encrypted storage and protected backups, and explicitly says ownmail does not encrypt the archive itself. docs/archive.md likewise discloses plaintext storage and the need to preserve messages, sidecars and configuration in backups. This decision does not certify that an operator has followed that guidance.
Technical evidence at the review base: archive.py saves ordinary RFC 822 bytes; sidecar.py saves JSON alongside them; database.py stores searchable metadata and full-text index terms in SQLite. The index may use a separate db_dir. ActiveCache keeps message bytes, JSON metadata and its own index outside the archive. Encrypting only .eml files would therefore leave sensitive metadata and derived search information exposed. A complete implementation would need coordinated coverage of these storage locations and transient writes/journals, with an explicit boundary for exports and backups.
Engineering cost and recovery: direct .eml interoperability, import/scan/rebuild, JSON reading, exports and cleanup's raw-content verification currently consume ordinary files. Built-in encryption would require coordinated compatibility work, restartable mixed-format conversion and recovery behavior, and durable key recovery independent of one keychain entry. Key loss could render owned mail unrecoverable after server copies disappear. This is substantial archive-format, operational and maintenance cost without a demonstrated additional requirement beyond the existing encrypted-storage alternative. Do not implement a speculative encryption layer or weaken existing ownership/integrity checks.
Decision boundary: declining new machinery under the existing contract is the engineering decision explicitly delegated by this task, not a choice of the owner's personal threat preferences. A future requirement to keep copied archives encrypted outside protected storage, or to impose a separate application-unlock boundary, would need an explicit threat/coverage/recovery contract and the existing archive-format/key-handling sign-off before design or implementation. Neither requirement is inferred here.
Literal acceptance: AC1 is met by this recorded worth decision evaluating the task's bounded at-rest premise and existing alternative; it is not a statement that volume encryption satisfies every possible threat or that it is active on any actual device. AC2 is expressly conditional on implementation; no encryption is built, so no mixed-format or key-loss behavior is introduced or claimed. The description and both acceptance criteria remain unchanged.
Validation and delivery: the only intended repository change is this TASK11 ledger, from clean base 28ceda92c78415a36fe5dc5def1a9b866e141df9. Normal commit hooks and exact non-ledger tree equivalence to reviewed/full-gate-tested 3f1eb501ed65831d7b1028800baab70203421e54 are required before local fast-forward integration. That unchanged code passed 4,455 tests plus 370 subtests at 96.61% coverage; no broad suite or browser rerun is needed for this decision-only record. No encryption, source, schema, key/access handling, security setting, actual configuration, or remote change. TASK95 integrity, TASK6.1 design, TASK10 credential-design and TASK50 physical-iPhone gates remain open.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed through the explicit decision-only alternative: built-in archive encryption is not justified for the documented at-rest scope given the existing encrypted-storage alternative and interoperability, coverage and key-recovery costs. Plaintext-storage and backup-protection disclosures remain unchanged. No actual volume encryption or satisfaction of the user's threat preferences was verified. No encryption, source, schema, key/access handling, security settings or actual data changed.
<!-- SECTION:FINAL_SUMMARY:END -->
