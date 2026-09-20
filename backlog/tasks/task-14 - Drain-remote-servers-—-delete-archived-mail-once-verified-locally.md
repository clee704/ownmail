---
id: TASK-14
title: Mail ownership workstream
status: In Progress
assignee: []
created_date: '2026-07-24 22:45'
updated_date: '2026-09-15 04:48'
labels: []
milestone: m-5
dependencies:
  - TASK-5.2
documentation:
  - docs/philosophy.md
priority: high
ordinal: 1
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Workstream

Make ownmail a consolidated view of live mail and an owned archive whose server
copies can be removed, following the [ownership philosophy](../../docs/philosophy.md).
This task is the workstream container. Its remaining scope is these five tasks:

| Task | Outcome |
|---|---|
| [TASK-90](<task-90 - Keep-capture-retryable-when-required-labels-cannot-be-fetched.md>) | Retry capture when required labels cannot be fetched |
| [TASK-28](<task-28 - Active-messages-—-surface-the-pre-capture-set-so-ownmail-is-a-complete-view.md>) | Include live mail through a server-authoritative Active view |
| [TASK-38](<task-38 - Thread-level-capture-deferral-—-hold-a-message-until-its-thread-is-settled.md>) | Protect active threads from server cleanup |
| [TASK-14.2](<task-14.2 - Optional-purge-—-trash-archived-mail-on-the-server-once-verified.md>) | Safely remove eligible server copies through optional cleanup |
| [TASK-5.4](<task-5.4 - Local-label-editing-in-the-web-UI.md>) | Edit owned labels locally without changing server labels |

Individual tasks hold their status, acceptance evidence, blockers, and next
action. [Execution order](<../docs/doc-4 - Execution-order-—-2026-07-24-sequencing-decision.md#phase-5-order-updated-2026-09-14>)
is the ordering authority. Completed foundations and other backlog tasks are
outside this remaining scope; discovered work is filed separately and does not
automatically join the workstream.

## Resume

“Continue the work” and “continue Mail ownership” mean:

1. Read the repository rules, working tree, and current member tasks, including
   their dependencies and implementation notes. Account for existing edits and
   running work before making changes.
2. Resume an eligible member already in progress; otherwise select the next
   eligible member using the execution order, including its TASK-5.4 fallback.
   TASK-14 is a container. Unrelated in-progress tasks do not take priority.
3. Complete one member through its acceptance criteria, required checks, and
   commit. A request to continue until complete repeats this process within the
   same five-task scope. Existing approval and PR requirements still apply.
4. If a member is blocked, record the reason and exact next action in that task,
   leave any changes at a safe checkpoint, and try another eligible member. If
   none is ready, report what is needed to continue. Do not bypass dependencies
   or approvals to keep the workstream moving.
5. Before ending, update the member task with verified progress, relevant commit
   or PR, and any remaining blocker or next action. Report what finished and what
   comes next so a later session can resume from the repository alone.

Set this container to `In Progress` when member implementation starts. Mark it
`Done` only when all five members are `Done` and the cleanup acceptance criteria
below have been verified. If only that final verification remains, complete it
before closing the container. Once complete, report completion and stop; do not
select unrelated backlog work.

## Cleanup contract

Deliver archive capture and optional server cleanup under
[Ownership philosophy](../../docs/philosophy.md). Ownmail owns successfully
archived copies; servers retain authority over live mail. Downloading content
for the Active view is independent of both archival and server cleanup.

TASK-14.3 supplies eligibility-driven capture and TASK-14.1 supplies canonical
roles. TASK-28 separates the disposable Active cache from permanent ownership:
current Inbox and unfinished outgoing states cannot become owned copies through
legacy filter settings. Eligible filed and Sent mail is captured after fresh
provider checks and successful storage of its contents and required labels.

TASK-14.2 supplies optional server cleanup. It may move a server copy to Trash
only after verifying the owned archive copy and confirming that the message and
its thread are no longer Active. TASK-38 supplies thread protection. Cleanup
uses current server state solely to decide whether to remove the server copy;
server changes never update the archive's contents or labels.

Cleanup sweeps all previously captured messages as well as new captures, is
opt-in and dry-run by default, and never hard-deletes. Final removal follows
each provider's Trash policy. Active cached copies never qualify as verified
archive copies, and changing a download filter cannot authorize cleanup of
Inbox or unfinished outgoing mail.

Verification covers the saved message and required label metadata, with a
server identity that demonstrably corresponds to that owned copy. Local Trash,
expired or deleted copies, and incomplete captures do not qualify. Revalidate
local eligibility and current server activity before mutation as far as the
provider permits; changed or uncertain state postpones cleanup.

This replaces the original two-knob premise that anything downloadable is
purgeable. Historical implementation notes below describe the earlier split;
the current philosophy governs future work.

Server deletion and OAuth changes retain the repository's existing sign-off
and PR requirements. Documentation of the design does not approve those
implementation changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Server cleanup is opt-in and off by default; with it off, ownmail makes no server deletions
- [ ] #2 Cleanup moves messages to the provider's Trash rather than hard-deleting; whether and when final removal occurs follows the provider's actual retention behavior
- [ ] #3 Cleanup requires an owned archive copy whose local .eml is re-hashed at cleanup time and matches its recorded content hash; an Active cached copy never qualifies
- [ ] #4 Cleanup sweeps eligible server copies of previously captured messages as well as messages captured in the current run
- [ ] #5 Current server state and TASK-38 thread protection prevent cleanup of Active messages and live threads, including a previously captured message returned to Inbox
- [x] #6 The existing capture filter uses canonical system roles rather than raw provider folder strings (TASK-14.1)
- [x] #7 Provider capture filtering uses the shared role mechanism (TASK-14.1)
- [ ] #8 Active Inbox and unfinished outgoing mail stay protected from cleanup regardless of whether their contents have been downloaded
- [ ] #9 Dry-run is the default for cleanup: reports what would be trashed, per account, and changes nothing
- [ ] #10 Verification failure, missing archive files, or incomplete server/thread state skips affected messages and reports the reason without aborting the run
- [ ] #11 Cleanup is resumable and batch-committed; Ctrl-C leaves consistent state
- [ ] #12 Configuration documentation distinguishes Active download, archive capture, and optional server cleanup, including their eligibility rules
- [ ] #13 Provider-specific Trash moves and retention, including mailbox.org, are verified and documented before enabling each path; moving to Trash does not promise permanent removal
- [ ] #14 Any required Gmail OAuth scope widening is signed off separately, with a documented re-consent path that preserves read-only access for users without cleanup
- [ ] #15 Human sign-off is recorded and server cleanup work lands via PR
- [ ] #16 Cleanup requires complete, durable capture metadata, including required labels in a readable sidecar; failed required label retrieval, missing or malformed metadata, and incomplete capture postpone cleanup
- [ ] #17 Each server candidate is matched to its owned copy within the correct source and account; ambiguous or reused identifiers and content that cannot be shown to correspond to that copy skip cleanup
- [ ] #18 Local Trash, expired or deleted local copies, and Active caches do not qualify for cleanup; local label edits never substitute for current server roles
- [ ] #19 Local eligibility, server identity, and message/thread activity are revalidated before mutation as far as the provider permits; detected changes postpone cleanup, and documented provider limits describe any remaining race
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Historical split, 2026-07-25.** The current description and [Ownership philosophy](../../docs/philosophy.md) supersede the original filter-to-purge coupling recorded below.

Sequence within milestone m-5:

| Ordinal | Task | STOP? |
|---|---|---|
| 1 | TASK-17 — Gmail history watermark race (standalone data-loss bug) | no |
| 2 | TASK-18 — includeSpamTrash unreachable (standalone, blocks the filter) | no |
| 3 | TASK-14.3 — make capture eligibility-driven | no |
| 4 | TASK-14.1 — the download filter config surface | no |
| 5 | TASK-14.2 — purge | **yes** |

Two reasons for the shape.

**Risk separation.** The original TASK-14 bundled both knobs, so the safe half inherited the dangerous half's gate. Only purge deletes user email and widens the OAuth scope; everything above it lands on master normally. This mattered in practice — the user's working model needs `inbox` excluded from download now, for a reason independent of purge (inbox = untriaged, so archiving it forces the delete decision twice), and blocking that behind a purge sign-off was accidental coupling.

**The audit changed the size of the work.** doc-6 describes knob 2 as "not new machinery — unify three existing filter sites and expose them in config". That is true of the config surface and false of everything beneath it. A filter is a statement about a message's *current* server state, while watermarks, `messageAdded` and folder-membership snapshots are all statements about *arrival*. Making capture eligibility-driven (TASK-14.3) is the real work; the config surface (TASK-14.1) is the small half that was mistaken for the whole.

TASK-17 and TASK-18 were pulled out as standalone because they are defects in today's code rather than new capability, and they are independently verifiable. TASK-17 loses mail right now; TASK-18 makes one of the filter's intended values unreachable. Both sit directly under the filter, so fixing them first keeps failure modes separable.

Full hole audit — eight findings with file:line — is in TASK-14.1's Implementation Notes.

2026-09-14: Established Mail ownership as a named workstream with fixed remaining membership, task-local progress, and a repository-level continuation route. Setup changes no feature status or implementation acceptance evidence.

2026-09-14 checkpoint: TASK-90 is Done (4d25a77). TASK-38 has a tested, reviewed read-only protection checkpoint (b18454c), with broad provider clearance still blocked. TASK-5.4 has a tested, reviewed owned-label editor (371855b), with Active/cleanup integration ACs still open. TASK-28 awaits explicit approval for its separate Active-cache schema and disposable cache-file replacement/removal. TASK-14.2 awaits its dependencies and separate server-cleanup/OAuth approvals. Approval requests were presented and have not been answered; no dependent implementation or real-account cleanup was performed. Existing canonical capture-role filtering remains verified. Final full pre-push checks passed with required browser tests and 95.97% branch coverage. No member is currently eligible for further implementation without the recorded approvals or provider-state evidence; resume from those task-local next actions. The workstream remains incomplete.

Active-cache approval was granted after a single bounded storage explanation. TASK-28 now has a tested feature-branch implementation with final acceptance checks and PR delivery in progress. Its broad received/filed capture AC remains open because provider state currently proves only Sent completion; uncertain mail stays readable in the disposable cache. TASK-38 broad provider clearance and TASK-14.2 cleanup remain blocked, and TASK-5.4 still needs cleanup integration. Server cleanup, OAuth changes, and narrowed cleanup support have not been approved. TASK-91 records a separate legacy sidecar-save retry defect and does not expand the five-member workstream.

2026-09-14 continuation checkpoint: Active-cache storage was explicitly approved and implemented in 43c6c0f on feat/active-mail-cache; draft PR https://github.com/clee704/ownmail/pull/1 uses fixed base abda815 because the local baseline is ahead of GitHub master. Continue on that feature branch rather than requesting storage approval again. TASK-28 broad received/filed capture remains open: provider state currently proves only Sent completion, and uncertain mail stays cached. TASK-5.4 Active-only and dual-state label editing was verified in the feature; cleanup integration remains open. TASK-38 broad provider clearance and TASK-14.2 dependencies/cleanup/OAuth approvals remain unresolved. TASK-91 (legacy sidecar retry) and TASK-95 (repeated cache-body reads) are separate discoveries outside the fixed workstream membership. Feature and main-checkout full pre-push gates passed; no feature merge or server cleanup was performed.

2026-09-14 workflow correction: the user requested closing PR #1 after clarifying that this disposable cache does not require the archive-data PR exception. The PR is confirmed CLOSED. Feature commit 43c6c0f remains on feat/active-mail-cache. Continue the normal direct-to-master workflow for this change once its remaining capture behavior and checks are complete; do not recreate the PR. The user requested a fuller explanation of the filed-mail capture question and has not approved changing its finished-state rule. Separate cleanup/OAuth approvals remain pending.

Current checkpoint: TASK-90, TASK-28, and TASK-38 are Done. Active cache, ordinary filed/Sent capture, and supported read-only thread clearance are committed directly on master in 8657a68; PR #1 remains closed. TASK-5.4 has verified Active integration and awaits cleanup integration only. TASK-14.2 now has its dependencies satisfied and a concrete preview/verification/Trash plan, but server-cleanup implementation and Gmail OAuth changes still require the recorded explicit sign-offs. No real-account cleanup has run. Resume at that one approval boundary; do not re-ask cache approval or reintroduce blanket Sent-only capture. TASK-91, TASK-95, and TASK-96 remain separate discoveries rather than added workstream members.

Current implementation route: continue feat/server-cleanup, based on d660e9d, before selecting another member. The user approved optional Gmail server cleanup with preview default, explicit apply, and IMAP accounts held. That behavior is committed in 50190ad and passes the full gate with 3,318 tests and 96.19% branch coverage. TASK-5.4 is Done in that branch after cleanup integration. The separate Gmail cleanup OAuth/keychain proposal is the next single approval and remains unanswered; do not ask again for cache storage or cleanup behavior approval. TASK-90/TASK-28/TASK-38 are Done on master, and the Active delivery at d660e9d passed GitHub CI on Python 3.10-3.12. PR #1 remains closed; no new PR or real-account cleanup has run.
Paused at the user's request after separate Gmail cleanup OAuth/keychain implementation approval. Both cleanup behavior and separate cleanup authorization are approved for implementation and synthetic tests; do not ask again. Resume feat/server-cleanup and TASK-14.2's latest checkpoint before selecting another task. Cleanup preview/verification/Trash behavior is committed and pushed through 7f4f6e3, with TASK-5.4 Done on that branch; the additional OAuth/keychain/CLI draft is being saved locally at this pause. Finish authorization-specific tests, fake-backend end-to-end integration, independent review, and final checks before delivery. TASK-90/TASK-28/TASK-38 are Done on master; TASK-14 and TASK-14.2 remain In Progress. PR #1 remains closed. No new PR, actual account authorization, or real-account cleanup is part of this checkpoint.
<!-- SECTION:NOTES:END -->
