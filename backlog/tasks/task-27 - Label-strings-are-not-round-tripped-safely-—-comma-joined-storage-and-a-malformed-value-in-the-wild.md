---
id: TASK-27
title: >-
  Label strings are not round-tripped safely — comma-joined storage, and a
  malformed value in the wild
status: Done
assignee: []
created_date: '2026-07-26 05:31'
updated_date: '2026-09-14 03:55'
labels:
  - bug
dependencies: []
priority: medium
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Preserve complete label strings through capture, indexing, rebuilding, and search. The existing comma-separated indexing argument splits a label such as "Receipts, 2026" into separate labels, and omitted labels can erase existing metadata during indexing.

Older ownmail versions also inserted X-Gmail-Labels after the first physical email-header line. When the first header was a folded References field, its continuation message IDs became part of the label. Removing the injected header later restored the email header but left malformed labels in the index and sidecars.

Fix the label boundary handling without a schema migration. Provide an evidence-based disposition for legacy malformed metadata and preserve legitimate label names rather than rejecting strings by appearance.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The producer of the malformed value is identified from the affected messages, not inferred
- [x] #2 A label containing a comma survives capture, indexing and search as one label, or the limitation is documented and enforced with an explicit rejection
- [x] #3 Existing archives holding a malformed label have a stated disposition — repaired, reported, or left alone with the reason recorded
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Trace the malformed labels against affected message headers and metadata. Preserve label boundaries through indexing without changing the schema. Add focused regression coverage and a bounded repair path, verify it against backups, and repair the authorized archive. Review base: 4f32c7d. Work is isolated from the active UI task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed the producer against affected archive files: replaying the historical Gmail label injector from 65dc4ee^ reproduces each malformed value exactly. It inserted X-Gmail-Labels after the first physical line of a folded References header, absorbing its continuation IDs. The later header-stripping code removed only the injected physical line, leaving valid References headers but retaining bad labels in metadata. Affected .eml bytes match their recorded content and index hashes; repair therefore changes sidecars and derived label rows only. Existing normalized label tables and JSON sidecars already support commas, so no schema migration is needed.

The fix passes exact label lists to indexing, treats omitted labels as preservation and an explicit empty list as clearing, and uses sidecar metadata when rebuilding. Legacy comma-separated API input is rejected before database writes. Import, capture, and interrupted-capture label consistency are included in the regression coverage. The legacy repair is a source-checkout maintenance script with a read-only preview, exact folded-header and file-hash evidence, private metadata journals, and per-message retry behavior; it does not rewrite email bytes or alter the schema.

Full pre-push hooks passed, including the complete test suite and 95% branch-coverage gate. Independent review verified the corrected import and interrupted-capture cases and completed a fresh pass with no unresolved findings. Regression mutation checks failed for deliberate comma splitting, whitespace trimming, missing sidecar reads/copies, stale capture ordering, and disabled repair hash checks.

Applied the bounded metadata repair to a real archive after an exact dry-run match and a consistent database backup. Verified original sidecar backups, unchanged email bytes and email records, only the expected normalized-label row replacements, database integrity, a clean rerun, and corrected navigation in the running web application. No unrelated label discrepancies required repair.

The maintainer approved landing the reviewed fix locally on master without a PR. The complete pre-push gate passed on an isolated snapshot containing the reviewed changes and the current master base; the integrated suite passed with 95.55% branch coverage. Independent integration review confirmed that later UI changes were preserved. All acceptance criteria are verified. No branch or base history was pushed.

Privacy audit follow-up: `fix/label-round-trip` is a stale TASK-27 branch whose ancestry retains private data removed from published history. Do not push or merge it. The fix is already on cleaned `master`; TASK-27 remains Done. Start further work from current `master`, transplanting only reviewed, sanitized changes if needed. The old branch and worktree remain local.
<!-- SECTION:NOTES:END -->
