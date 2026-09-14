---
id: TASK-28
title: Active messages — surface the pre-capture set so ownmail is a complete view
status: To Do
assignee: []
created_date: '2026-07-26 07:01'
updated_date: '2026-09-14 09:07'
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
- [ ] #1 Active contents are available for reading and searchable alongside Archived messages, with their status visibly distinct
- [ ] #2 Confirmed server changes update Active copies; confirmed deletion, Trash, or Spam removes them from the Active view; failed or incomplete refreshes do not remove them
- [ ] #3 An eligible Active message becomes one Archived result only after its contents and configured label snapshot are successfully saved; the saved snapshot is frozen, and thread activity does not delay capture
- [ ] #4 Active messages cannot be label-edited locally in ownmail
- [ ] #5 Active data lives outside the archive directory and its removal never touches archive content
- [ ] #6 The age of the Active view is visible wherever Active messages are shown
- [ ] #7 Enablement defaults, refresh cadence, count semantics, and stale-cache presentation are recorded and documented
- [ ] #8 is:active / is:archived parse, with an unknown value producing a parse error rather than an empty result
- [ ] #9 Active messages appear in ordinary search results, visually distinguishable without a chip in the list view
- [ ] #10 A captured message that returns to server Inbox keeps its archived contents and labels unchanged, exposes its Active server state, and does not produce duplicate ordinary results
- [ ] #11 Failed content or required label acquisition and interrupted saves leave promotion incomplete and retryable; a later successful run completes capture once without losing the message or overwriting an owned copy
- [ ] #12 Gmail API, Gmail over IMAP, and standard IMAP have documented and tested Inbox and unfinished-state detection, limitations, and behavior when state is unavailable or uncertain; Trash/Spam outrank Active states, which outrank Sent and filing labels
- [ ] #13 Existing exclude_roles values have a documented and tested compatibility policy that preserves Active ownership for Inbox and unfinished outgoing mail regardless of download enablement
- [ ] #14 Upgrade preserves existing archived contents, labels, and local Trash, including copies carrying historical INBOX or DRAFT labels; current Active state is established separately without duplicate ordinary results
- [ ] #15 CLI downloads and manual or scheduled web downloads apply the same lifecycle, with scheduled runs reusing the existing scheduler; status distinguishes capture from Active refresh and never presents a failed or partial refresh as current
<!-- AC:END -->
