---
id: TASK-14
title: Archive capture and optional server cleanup
status: To Do
assignee: []
created_date: '2026-07-24 22:45'
updated_date: '2026-09-14 09:08'
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
Deliver archive capture and optional server cleanup under
[Ownership philosophy](../../docs/philosophy.md). Ownmail owns successfully
archived copies; servers retain authority over live mail. Downloading content
for the Active view is independent of both archival and server cleanup.

TASK-14.3 supplies eligibility-driven capture and TASK-14.1 supplies the existing
canonical-role filter. Their completed implementation remains the current
behavior: permitting Inbox or Drafts through that filter creates permanent
archive copies. TASK-28 adds the planned Active distinction; it must not be
implemented by simply relaxing the current filter.

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
- [ ] #6 The existing capture filter uses canonical system roles rather than raw provider folder strings (TASK-14.1)
- [ ] #7 Provider capture filtering uses the shared role mechanism (TASK-14.1)
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
<!-- SECTION:NOTES:END -->
