---
id: TASK-36
title: Reassess label provenance for explicit repairs
status: Done
assignee:
  - Codex
created_date: '2026-08-06 18:38'
updated_date: '2026-09-30 20:32'
labels: []
dependencies: []
priority: low
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reassess label provenance only for a concrete explicit-repair use case under
[Owning your mail](../../docs/philosophy.md). It is not a prerequisite for local
label editing (TASK-5.4) or the ownership design.

The earlier proposal would replace a server-origin label partition whenever
the server was re-read. That conflicts with the clarified ownership boundary:
all captured labels become ownmail's, including labels originally supplied by
the server. Routine download, Active refresh, and cleanup must leave that
snapshot and subsequent local edits alone.

Origin metadata could help explain or preview an operator-requested repair,
but that benefit must be demonstrated before adding storage and migration
cost. Provenance alone never authorizes a server refresh to replace labels or
restore labels the user removed locally. If no concrete need remains, close
this as a decision without adding provenance storage.

Any implementation that changes the database schema follows the existing
repository approval and PR requirements.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A concrete explicit-repair use case and its benefit are recorded before implementation, or the task is closed with a decision that provenance is unnecessary.
- [x] #2 Any retained provenance design preserves all captured and locally edited labels during routine operations, including intentional removals; it introduces no automatic server-partition replacement.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Verify the literal decision-only alternative in AC1 and conditional preservation requirement in AC2 against current ownership rules.
2. Record the actual standard-IMAP repair ambiguity, bounded synthetic preview evidence, limitations of current origin tags and missing historical intent, and why extra provenance storage is not justified for this repair scope. Preserve preview/--apply and all existing behavior.
3. Close through the decision alternative without schema, storage, code, policy or actual settings changes. Run normal hooks, preserve main/tested refs, and verify a ledger-only fast-forward against clean base 2c770e3903bbd892e0e8a521ebbde03867599d16.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: candidate concrete use for AC 1 is relabel. Its union strategy can re-add a folder label the user removed locally, and its server strategy drops local edits; origin metadata could separate those cases. Without such a use, close as unnecessary.

2026-09-30 engineering worth decision: do not add per-label provenance storage for the current explicit-repair scope. AC1 expressly permits closure with a decision that provenance is unnecessary. This decision does not claim the repair ambiguity is solved.
The candidate use was checked in actual code: relabel supports standard IMAP membership matched to captured account/provider IDs, refuses Gmail API and the Gmail All Mail path, reads owned sidecars first, and previews union or server strategies before a separate --apply. Union can re-add an intentionally removed folder; server replacement can discard a local addition. The existing preview shows counts and before/after samples for the first ten changes, not a complete per-message review of an arbitrarily large run. These limitations and the existing explicit repair choices remain unchanged.
Bounded synthetic evidence used actual local-edit and relabel preview paths with inert keychain/provider fixtures and network blocked. Capturing Saved+Waiting then removing Waiting locally produced the same current sidecar and identical union preview as never inheriting Waiting. Both previews proposed adding Waiting. A third preview showed the server strategy replacing Saved+Local with Saved+Waiting, including one removal. All three preserved message/sidecar bytes and saved labels; no --apply, actual account, credential, network, or real mail was used.
A current origin tag on a present label cannot recover the history of a label that is absent. Historical IMAP flattening, deliberate local removal, deliberate capture exclusion, and later server changes may therefore remain indistinguishable. Richer future capture/edit history could support additional explanations, but cannot retroactively recover the missing history of the old captures that this repair targets. No concrete additional repair benefit has been demonstrated that justifies storage, compatibility, rebuild and migration costs. The current capture identity/content metadata serves ownership verification, not label edit history. Do not repurpose it or silently retain label metadata omitted under TASK19.
Deliberate limitation: retain today's explicit repair strategies and their ambiguity. This is not approval for automated restoration of removed labels or server-partition refresh. A future request for automatic protection of local repair intent must specify its desired repair semantics and historical-data retention before a new design is considered.
Literal acceptance: AC1 is met by this documented decision to decline provenance storage after assessing the concrete repair use. AC2 is conditional on retaining a provenance design; none is retained. No routine code, owned snapshot, local edit/removal behavior, or server-partition replacement changes, so its preservation constraint is maintained without a schema/storage implementation. The old note suggesting origin metadata could separate all cases is superseded by the narrower evidence above.
Validation and delivery: decision-only ledger change from 2c770e3903bbd892e0e8a521ebbde03867599d16. The reviewed underlying code already passed the mandatory 4,455-test plus 370-subtest gate at 96.61% coverage; no code has changed and no broad suite or browser rerun is needed. Normal commit hooks and exact non-ledger tree equivalence are required for integration. TASK95 integrity, TASK6.1 schema/design and TASK50 physical-device gates remain open and untouched.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed as a decision: per-label provenance storage is unnecessary for the current explicit standard-IMAP repair scope. Reproduced the unresolved ambiguity and current preview safeguards; current origin tags do not recover missing edit history. No schema, storage, runtime behavior, repair policy or actual configuration change. Automatic protection of local repair intent is not promised or implemented.
<!-- SECTION:FINAL_SUMMARY:END -->
