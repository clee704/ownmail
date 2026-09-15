---
id: TASK-28
title: Active messages — surface the pre-capture set so ownmail is a complete view
status: In Progress
assignee: []
created_date: '2026-07-26 07:01'
updated_date: '2026-09-15 04:04'
labels: []
milestone: m-5
dependencies:
  - TASK-14.3
  - TASK-90
priority: medium
ordinal: 7
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement the Active view in [Ownership philosophy](../../docs/philosophy.md).
Ownmail should provide consolidated reading and search across live and archived
mail while preserving their different authorities. Inbox messages and unfinished
outgoing mail remain server-owned; successfully archived copies are ownmail-owned.

## Behavior

- Download Active contents for reading and search alongside Archived mail.
  Keep status and freshness visible wherever Active messages appear.
- Follow confirmed server edits, role changes, and deletion for Active copies.
  Trash and Spam stay out of the view. Failed or incomplete refreshes must not
  be interpreted as deletion.
- Store Active data in a disposable cache outside the archive. Downloading an
  Active message does not capture it or make it eligible for server cleanup.
- Archive an eligible message when its contents and configured label snapshot
  are successfully saved. Failed or interrupted saves leave the handoff
  incomplete and retryable. Successful capture freezes the snapshot and leaves
  one Archived result. Thread activity can delay server cleanup (TASK-38),
  but never eligible capture.
- A previously archived message returning to server Inbox keeps its owned copy
  unchanged. The Active view and cleanup checks must represent the live server
  state without replacing that copy or duplicating it in ordinary results.
- Live triage remains in the mail client. Active messages cannot receive local
  archive label edits; archived messages retain ownmail's local management.

## Presentation

Use `is:active` and `is:archived` search terms, with unknown values producing a
parse error. An Active sidebar entry links to its search and shows a count.
Active messages appear in ordinary results with a subtle row treatment and a
detail-view explanation of server ownership. Keep status distinct without
adding a list-row chip, following doc-9.

## Scope and implementation choices

This revision supersedes the 2026-07-26 default-off and headers/snippet-only
proposal. The product direction includes Active contents in consolidated
reading and search. Per-source enablement defaults, refresh cadence, count
semantics, and behavior when cached data is old still need implementation
choices. Reuse the existing download scheduler. CLI downloads and manual or
scheduled web downloads must apply the same lifecycle and report refresh and
capture outcomes accurately; finishing an archive pass does not by itself make
the Active view current.

Reuse TASK-14.3's eligibility and provider enumeration where applicable. Its
implemented candidate calculation uses arrivals and departures from transient
excluded states; the old proposal's full-mailbox enumeration is not a required
Active implementation. TASK-90 fixes failed required label acquisition in the
existing capture path before Active promotion builds on it.

Document the Inbox and unfinished outgoing states that Gmail API, Gmail over
IMAP, and standard IMAP can identify, with explicit behavior for unavailable or
uncertain state. Trash and Spam take precedence over Active states; Inbox and
unfinished outgoing states take precedence over Sent and filing labels. Failed
or incomplete state checks cannot establish eligibility.

Define compatibility for existing `exclude_roles` settings without allowing
them to make Inbox or unfinished outgoing mail owned. Document how the settings
affect Active enablement or are migrated. Introducing Active must preserve
existing archived contents, labels, and local Trash. Historical `INBOX` or
`DRAFT` labels do not establish current server state or turn owned copies into
disposable cache.

New storage state may require a schema change. Follow the repository's existing
approval and PR rules before implementing such a change. Server actions from
ownmail are outside this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Active contents are available for reading and searchable alongside Archived messages, with their status visibly distinct
- [x] #2 Confirmed server changes update Active copies; confirmed deletion, Trash, or Spam removes them from the Active view; failed or incomplete refreshes do not remove them
- [x] #3 An eligible Active message becomes one Archived result only after its contents and configured label snapshot are successfully saved; the saved snapshot is frozen, and thread activity does not delay capture
- [x] #4 Active messages cannot be label-edited locally in ownmail
- [x] #5 Active data lives outside the archive directory and its removal never touches archive content
- [x] #6 The age of the Active view is visible wherever Active messages are shown
- [x] #7 Enablement defaults, refresh cadence, count semantics, and stale-cache presentation are recorded and documented
- [x] #8 is:active / is:archived parse, with an unknown value producing a parse error rather than an empty result
- [x] #9 Active messages appear in ordinary search results, visually distinguishable without a chip in the list view
- [x] #10 A captured message that returns to server Inbox keeps its archived contents and labels unchanged, exposes its Active server state, and does not produce duplicate ordinary results
- [x] #11 Failed content or required label acquisition and interrupted saves leave promotion incomplete and retryable; a later successful run completes capture once without losing the message or overwriting an owned copy
- [x] #12 Gmail API, Gmail over IMAP, and standard IMAP have documented and tested Inbox and unfinished-state detection, limitations, and behavior when state is unavailable or uncertain; Trash/Spam outrank Active states, which outrank Sent and filing labels
- [x] #13 Existing exclude_roles values have a documented and tested compatibility policy that preserves Active ownership for Inbox and unfinished outgoing mail regardless of download enablement
- [x] #14 Upgrade preserves existing archived contents, labels, and local Trash, including copies carrying historical INBOX or DRAFT labels; current Active state is established separately without duplicate ordinary results
- [x] #15 CLI downloads and manual or scheduled web downloads apply the same lifecycle, with scheduled runs reusing the existing scheduler; status distinguishes capture from Active refresh and never presents a failed or partial refresh as current
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Complete the Active cache on master using the approved direct landing workflow. Preserve current reader fixes while incorporating the existing cache implementation. Restore normal filed-mail capture through explicit unfinished-state checks, including documented scheduled and queued signals. Verify provider observations and preserve failure/unknown-state holds. Keep archive capture separate from cleanup; complete focused regressions, independent review, full pre-push checks, and commit the coherent result.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approval checkpoint, 2026-09-14: the proposed new cache schema and replacement/removal of disposable cached .eml files require explicit sign-off under AGENTS.md. No ownmail.db migration is required by the proposal. Next action: obtain approval for that bounded storage behavior, implement TASK-28 on a feature branch, and deliver through a PR. Credential/OAuth changes and server mutations remain outside this approval.

2026-09-14: The user explicitly approved the separate disposable Active cache, its new local database schema, and replacement/removal of cached message files after reviewing the storage proposal. Existing archive contents, labels, local Trash, and ownmail.db schema remain unchanged. Delivery is through a feature branch and PR. Server cleanup, credential/OAuth changes, and narrowed cleanup support were not approved and remain separate pending decisions. Review base: abda815; branch feat/active-mail-cache in a separate worktree to preserve concurrent reader-layout work. Implement provider observations, atomic cache storage, capture/search integration, then reading/freshness UI and lifecycle tests. Unknown provider state remains server-owned and cannot establish capture eligibility.

Implementation checkpoint: separate cache storage, provider observations, Active refresh, frozen capture, consolidated search, reader controls, and download status are implemented on feat/active-mail-cache. Cache payloads and metadata are atomic; the existing ownmail.db schema is unchanged. Source/account-scoped identity and verified owned bytes prevent duplicate ordinary results or replacement of owned copies, including local Trash. Independent review found and fixed malformed optional capture provenance breaking search. Recovery tests cover failed contents/labels/storage/index writes, interruptions, index rebuild, historical INBOX/DRAFT labels, and a captured message returning to Inbox with changed live contents. Deliberate mutations were rejected by provider, storage, lifecycle, search, UI, and progress regressions. The full intermediate suite passed 3,097 tests with one expected failure and 96.01% branch coverage; final acceptance additions and pre-push checks remain pending.

Remaining scope: AC #3 stays open because automatic capture currently establishes finished state only for confirmed Sent mail. Received/filed Gmail mail and non-Sent IMAP mail remain readable/searchable with unknown state, and broad capture is not complete. AC #12 records this documented, tested limitation rather than claiming complete provider visibility. A fresh eligible candidate can be captured during an unrelated incomplete listing, but incomplete listings or message failures defer cache removals and cannot mark refresh current. Cleanup/OAuth remain unapproved and unimplemented. The legacy low-level backup sidecar-save retry defect is filed separately as TASK-91; the new Active lifecycle has its own tested retry-safe capture path.

Acceptance audit completed web and CLI ownership/freshness checks. CLI results now show Active ownership, last-check time, and incomplete/unconfirmed status; a mutation removing this status fails the regression. Historical INBOX/DRAFT upgrade fixtures verify that saved labels alone never create Active state, and fresh live edits preserve owned bytes/labels without duplicate results. Actual dual-state web label POST verifies that only owned sidecar/index labels change, leaving cached contents/metadata and provider state unchanged. All acceptance criteria except broad capture AC #3 are verified; keep In Progress pending that behavior and PR review.

Final pre-commit run -a --hook-stage pre-push passed with OWNMAIL_REQUIRE_BROWSER_TESTS=1 and 96.08% branch coverage. All 3,114 collected tests completed under the gate (one existing expected failure). The feature checkpoint is ready for draft review; broad capture AC #3 and human review remain open. The fixed review base is abda815 because GitHub master has not yet received the local baseline commits.

2026-09-14 approved checkpoint: the user approved only separate disposable Active-cache storage, its database, and replacement/removal of cached copies. Implementation is committed as 43c6c0f on feat/active-mail-cache and reviewed in draft PR https://github.com/clee704/ownmail/pull/1, against fixed base abda815. Use the existing worktree for that branch when resuming; this master checkout does not contain the feature implementation. All feature acceptance criteria except broad capture AC #3 are verified in that branch; full required pre-push checks passed with 96.08% branch coverage and required browser tests. GitHub CI was running when the PR opened. Automatic capture currently proves only confirmed Sent completion; received/filed mail with uncertain finished state remains in the readable/searchable cache. Next action: resolve the finished-state rule for broad filed-mail capture, complete the draft and CI/review, then land through PR. Keep the task In Progress. Server cleanup, OAuth changes, and narrowed cleanup support remain unapproved.

2026-09-14 workflow correction: the user requested closing PR #1 after clarifying that this disposable cache does not require the archive-data PR exception. The PR is confirmed CLOSED. Feature commit 43c6c0f remains on feat/active-mail-cache. Continue the normal direct-to-master workflow for this change once its remaining capture behavior and checks are complete; do not recreate the PR. The user requested a fuller explanation of the filed-mail capture question and has not approved changing its finished-state rule. Separate cleanup/OAuth approvals remain pending.

Evidence correction while explaining the filed-mail question: blanket Sent-only capture is an implementation policy, not a provider requirement or evidence that ordinary received/filed mail is unfinished. RFC 9979 (Informational, May 2026), section 8.2, registers the Scheduled mailbox attribute; RFC 5550 section 5.10 defines $SubmitPending for messages awaiting submission. These supply explicit unfinished-state signals and must be considered. Special-use attributes remain optional, and Gmail Scheduled API representation remains unverified by the primary documentation checked. Next action: implement documented queued/scheduled exclusions and verify provider-specific Scheduled exposure before claiming comprehensive detection. The existing product goal already includes capture of ordinary filed mail; do not present a blanket premature-capture exception as a prerequisite to implementing that goal. Sources: https://www.rfc-editor.org/rfc/rfc9979.html#section-8.2 ; https://www.rfc-editor.org/rfc/rfc5550.html#section-5.10 ; https://developers.google.com/workspace/gmail/api/guides/labels .

The user authorized continuing after the corrected unfinished-state explanation. Work is now consolidated onto master, based on a2abeb0, preserving the completed reader-style fixes and all existing approval/correction notes. Do not recreate PR #1. Verify scheduled/queued signals and replace blanket Sent-only classification with documented state-based eligibility. Existing archive files and database schema remain preserved; cleanup and credential/OAuth changes remain separate pending approvals.

Observed-state capture is implemented on master: ordinary filed and Sent mail can be captured after fresh required reads, while Inbox/Drafts, advertised IMAP Scheduled membership, and SubmitPending remain Active. Unknown state and read failures hold affected mail. Gmail catalog lookup failures now retain cached contents; a regression verifies successful capture on retry. Provider/lifecycle tests verify filed handoff, fresh draft and scheduling changes, immutable identity and UIDVALIDITY checks, frozen labels, and one-result deduplication. Independent Gmail and IMAP reviews completed, with the catalog failure finding fixed and mutation-tested. Gmail Scheduled API semantics remain unverified and hidden states remain outside provider observations. All acceptance criteria have focused evidence; the integrated required gate and direct commit remain pending.
<!-- SECTION:NOTES:END -->
