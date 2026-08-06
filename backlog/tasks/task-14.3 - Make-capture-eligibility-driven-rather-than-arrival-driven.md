---
id: TASK-14.3
title: Make capture eligibility-driven rather than arrival-driven
status: In Progress
assignee: []
created_date: '2026-07-25 05:53'
updated_date: '2026-08-06 19:56'
labels: []
milestone: m-5
dependencies:
  - TASK-17
parent_task_id: TASK-14
priority: high
ordinal: 3
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Prerequisite for TASK-14.1, split out of it once the hole audit showed the config surface was the small half.

THE PROBLEM. A download filter is a statement about a message's CURRENT state on the server. Every mechanism underneath it is a statement about ARRIVAL:
- Gmail API asks for historyTypes=['messageAdded'] only (gmail.py:214)
- IMAP tracks a max-UID watermark per folder
- Gmail-over-IMAP watermarks All Mail, where a message's UID never changes after arrival

So a message that is ineligible when it arrives and becomes eligible later is never revisited. Concretely, all of these are missed on the Gmail API path:
- inbox -> archive (user files a message)
- trash -> archive (user restores a message they had deleted)
- spam -> inbox -> archive

None of this bites today, for one reason only: the inbox is downloaded, so essentially everything is captured eagerly on arrival before it can transition anywhere. That eager capture is the safety net a download filter removes. This must land before any filter ships, or the filter turns a working archive into one with silent holes.

SHAPE OF THE FIX (decide before building):
- Treat a sync signal as producing a CANDIDATE message id, not a download decision. Then re-evaluate each candidate's current state against the filter. A message trashed and restored between two runs produces two events and one correct answer.
- Gmail API: subscribe to labelAdded/labelRemoved alongside messageAdded. Every transition then produces a candidate.
- Gmail-over-IMAP: departure from a folder leaves no trace (imap.py:546-551 only sees UIDs above the watermark), so folders whose membership the filter depends on must be rescanned in full each run. Bounded and cheap for INBOX; confirm before assuming for others.
- Plain IMAP: already correct. A folder move allocates a new UID above the destination's watermark, so transitions are detected for free. No change needed.
- REJECTED: recording filtered-but-seen ids as 'deferred' and re-checking them. Grows without bound — every message ever trashed would be re-checked forever.

TRANSIENT VS STANDING EXCLUSIONS (user, 2026-07-26). This resolves the 'confirm before assuming for others' caveat above, and it is the same growth problem that killed the deferred-id list, arriving from the other direction.

Re-evaluating an excluded message every run is only affordable when the excluded population is BOUNDED. The exclusion set splits in two, and the two halves need opposite treatment:

- TRANSIENT — the role terms: inbox, trash, spam, drafts. What is excluded is the message's STATE, and that state changes. Departure is common (restore from trash, file from inbox) and MUST be detected, so membership has to be read live each run. Affordable precisely because each population is self-bounding: an inbox is small by nature, and trash and spam are capped by the provider's retention. That bound is not a lucky property — it is why only role terms are allowed to be transient.

- STANDING — named folders and labels. What is excluded is the CONTAINER, not a state, and the user's statement is durable: 'I never want this'. The population has no bound; a named label can hold 50k messages and only grow. Rescanning it every run is unaffordable AND pointless, because nothing about a message sitting in an excluded folder is going to change the answer.

THE COST INVARIANT UNDERNEATH (corrected 2026-07-26; the first version of this note framed the problem as a Gmail-over-IMAP quirk, which mislocated it).

Anything excluded but not captured stays a candidate forever and is re-evaluated forever — that is what 'eligibility is re-evaluated until capture' means. So THE COST OF A FILTER IS PROPORTIONAL TO WHAT IT EXCLUDES, NOT TO WHAT IT ADMITS. Provider-independent, and the actual reason the transient/standing split matters: role terms stay cheap because their populations are self-bounding, and a long-lived user folder does not.

DEPARTURE DETECTION, per provider. Two of three paths get it free:
- Plain IMAP: moving out of an excluded folder allocates a new UID above the destination's watermark. Detected.
- Gmail API: labelRemoved fires. Detected, once this task subscribes to it.
- Gmail-over-IMAP: NOT detected, for any exclusion. The message sits in All Mail with an unchanging UID and merely vanishes from the excluded folder, so nothing above any watermark ever appears. Verified against imap.py:520-575 — the incremental path searches `UID <max+1>:*` per folder, so a message that only LEFT a folder is invisible to it.

That blindness applies to inbox exactly as much as to a named label. Since inbox is the default exclusion, it is the main case, not a footnote — the previous framing of this as a standing-exclusion issue understated it.

SHAPE OF THE FIX FOR THAT PATH. Do not add per-folder rescans plus remembered membership. Define the candidate set by ABSENCE FROM THE ARCHIVE instead of by arrival: candidates = (All Mail) − (already archived). Departure then needs no detection at all — a message that leaves the inbox is simply still in the difference and now passes the filter. The enumeration already exists (_scan_gmail, imap.py:326, does a full All Mail UID search), no new persistent state is required, and the difference is naturally small because everything eligible has already been captured — it converges to exactly the excluded population.

Which is the cost invariant again, now load-bearing: with only role exclusions the candidate set is inbox-sized. Add a standing exclusion over a 50k-message label and every run re-evaluates all 50k. If that ever needs fixing, subtract the standing-excluded folders' contents from the candidate set — enumerated from the server per run, never stored, so it is not the rejected deferred-id list.

NOT A CONFIG CHOICE. What is exposed is one exclusion list, not a temporary/permanent choice per entry. Which half a term falls in follows from the term itself — role terms are transient, named terms are standing — so the user is never asked to classify anything. The only knob this could ever justify is 'keep re-evaluating this named exclusion', and there is no case for it: named exclusions are durable by nature, and hole 1's forced resync already covers a reorganisation. What it does need is one line in config.example.yaml stating that moving mail out of an excluded folder needs a resync on Gmail-over-IMAP, since 'my restored mail came back but my un-labelled mail did not' is otherwise indistinguishable from a bug.

Also in scope, because they are the same class of problem (hole numbers refer to the audit in TASK-14.1's notes):
- Hole 1: widening the filter must force a full resync. Previously-skipped messages sit below the watermark, so relaxing the filter otherwise captures nothing retroactively, silently. Detect the filter change and invalidate the watermark.
- Hole 6: keep 'do not download from here' separate from 'do not read labels from here'. _list_folders currently drops excluded folders entirely, which also removes them as label sources (_scan_gmail uses non-All-Mail folders purely for label mapping).

Depends on TASK-17: the history watermark race makes incremental sync lossy, and this task makes incremental sync the only capture path. Fixing the race first keeps the two failure modes separable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A message that becomes eligible after arrival is captured on a later run, on every provider path
- [ ] #2 Departure from a transient excluded role is detected by diffing that role's membership across runs, not by a watermark
- [ ] #3 The persisted excluded-membership set is replaced each run and never accumulates
- [ ] #4 Eligibility is decided against the CURRENT excluded enumeration, so an arrival that was filed before ownmail saw it is judged by where it is now
- [ ] #5 Per-run server cost is flat in mailbox size on the incremental path: no full enumeration of the eligible set
- [ ] #6 Standing (named-folder) exclusions are not diffed, and config.example.yaml says moving mail out of one needs a resync
- [ ] #7 Widening the filter invalidates the watermark and forces a full resync (hole 1)
- [ ] #8 A folder excluded from download still contributes labels (hole 6)
- [ ] #9 Existing sync state from before this change is read without a forced full resync
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Five steps, each independently committable.

1. VOCABULARY. `roles.TRANSIENT_EXCLUDE_ROLES` — the subset of exclusions whose membership is diffed. Today {trash, spam}; inbox and drafts join it at TASK-14.1. Named folders never join it (standing exclusions are not diffed).

2. CAPTURE STATE ENVELOPE (new module `capture.py`). Wraps what is stored in `sync_state`: {cursor, excluded, filter_fingerprint}. Must load both legacy shapes without forcing a resync — Gmail's bare history_id string and IMAP's JSON per-folder dict (AC #9).

3. GMAIL API — the path with a real bug today. Enumerate current membership of each transient excluded role (`messages.list q=in:trash` / `in:spam`), then:
       candidates = (arrivals ∪ (last_excluded − current_excluded)) − current_excluded
   Note the trailing subtraction replaces `_is_excluded` on the history events: eligibility is judged against where the message is NOW, not the labelIds the event carried (AC #4).
   CONCRETE BUG THIS FIXES: mail that lands in spam fires `messageAdded` with SPAM, is skipped, and is never revisited — so a spam false positive the user rescues is silently never archived. Today's only saving grace is that inbox mail is captured eagerly, which TASK-14.1 removes.

4. IMAP — no diff, and that is the finding rather than a shortcut.
   - Plain IMAP: a move allocates a new UID above the destination watermark, so departure is already an arrival. Nothing to add.
   - Gmail-over-IMAP: trash and spam are NOT IN All Mail, so a trashed message is already invisible to the scan and reappears with a fresh UID above the watermark when restored — also free. The path only needs diffing once INBOX is excluded (TASK-14.1), because that is the case where the message stays in All Mail at an unchanged UID and merely loses a label. Then it is one `UID SEARCH X-GM-RAW "in:inbox"` inside All Mail, which answers in All-Mail UID space with no header fetches.
   So providers declare which roles they can enumerate in their own download-id space, and IMAP declares none today. No dead code, and TASK-14.1 slots inbox in without new machinery.

5. THE TWO HOLES.
   - Hole 1 (AC #7): store a fingerprint of the effective filter in the envelope; a change invalidates the cursor and forces a full resync. Real consumer today — `exclude_folders` is already user-editable config.
   - Hole 6 (AC #8): `_list_folders` currently drops excluded folders entirely, which also removes them as label sources. Split 'do not download from here' from 'do not read labels from here'.

Then config.example.yaml for AC #6, and tests.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Candidate set: settled 2026-08-06 (user). Amends the SHAPE OF THE FIX above.

The description prescribes `candidates = (All Mail) − (already archived)` for the Gmail-over-IMAP path, and rejects 'per-folder rescans plus remembered membership'. That call was made without costing the enumeration. **It is wrong, and the reason generalises to every provider.**

WHY THE ELIGIBLE SET IS THE EXPENSIVE ONE TO ENUMERATE. The eligible set is, by construction, essentially the whole archive — everything the filter admits, captured or not. So enumerating it is O(mailbox) *per run, forever*, and it grows monotonically as the archive does. Measured shapes: Gmail API pages `messages.list` at 500, so ~60 round trips at 30k messages (~15-30s) and ~400 at 200k (~2-3 min), against ~0.3s for today's `history.list`. The subtraction converges; the enumeration underneath it never does.

THE INVERSION. Enumerate the EXCLUDED set instead and diff it across runs:

    arrivals   = history.list / UID watermark        (existing mechanism)
    excluded   = live enumeration of inbox, drafts, trash, spam
    departed   = last_excluded − excluded
    candidates = arrivals ∪ departed
    for each candidate: re-check current state, download if eligible
    persist(excluded)

Departure detection becomes a set difference, which is exactly the transition a watermark cannot see. Costs, flat in mailbox size on all three paths:

- **Gmail API** — ~5 `messages.list` calls per run (inbox, drafts, trash+spam), 1-2s, and it does not grow.
- **Gmail-over-IMAP** — one `SEARCH` of the inbox folder. This fixes that path's blindness without touching All Mail at all, which is the whole reason the rejected option existed.
- **Plain IMAP** — unchanged. A folder move allocates a new UID above the destination watermark, already detected.

WHY REMEMBERED MEMBERSHIP IS SAFE HERE, HAVING BEEN REJECTED ABOVE. The rejection of the 'deferred id list' stands: that list ACCUMULATED, so every message ever trashed would be re-checked forever. This set does not accumulate — it is REPLACED each run, and it holds exactly the transient roles, which this task already argues are self-bounding (an inbox is small by nature; trash and spam are capped by provider retention). The bound is the same one the transient/standing split rests on, used one layer down.

STANDING EXCLUSIONS ARE NOT DIFFED, deliberately. A named 50k label is a durable statement, so moving mail out of one is not detected and needs a resync — which hole 1 already requires and config.example.yaml already has to document. This is the one regression against the enumeration approach, and it is the cost the transient/standing split was written to accept.

STORAGE. `sync_state` (database.py:337) is a free-form key-value table, so this is a new key rather than a schema change. Not a STOP item.

FULL ENUMERATION SURVIVES AS A FALLBACK ONLY — history expiry (gmail.py:204), UIDVALIDITY change, and hole 1's filter-widening resync. Re-adding `history.list`-style fast paths on top is available later if a run's wall clock ever bites; not built on spec.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-25 06:57
---
Governing principle now recorded in doc-8 (Archival semantics): metadata is frozen once a message is captured, eligibility is re-evaluated until it is. This task is the second half of that rule.

doc-8 also adds an argument for this task independent of purge: capture timing sets label fidelity. Arrival-driven capture snapshots a message before its owner has filed it, so the archive keeps INBOX plus a CATEGORY_* and none of the user's own organizing. Moving capture to eligibility means capture-at-filing, which is what makes the capture-once policy defensible rather than merely cheap.
---
<!-- COMMENTS:END -->
