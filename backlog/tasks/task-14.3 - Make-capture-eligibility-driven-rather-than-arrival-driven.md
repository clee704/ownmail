---
id: TASK-14.3
title: Make capture eligibility-driven rather than arrival-driven
status: To Do
assignee: []
created_date: '2026-07-25 05:53'
updated_date: '2026-07-25 06:57'
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

CONSEQUENCE, per provider. Standing exclusions need no rescan on plain IMAP or the Gmail API: moving a message out of an excluded folder allocates a new UID in the destination, or fires labelAdded, so departure is detected for free by the machinery already there. The one gap is Gmail-over-IMAP, where the message sits in All Mail throughout and its UID never changes, so leaving an excluded label produces no signal at all.

ACCEPTED COST for that gap: departure from a standing exclusion is NOT detected on Gmail-over-IMAP. Reorganising mail out of an excluded label does not retroactively capture it. The escape hatch already exists — hole 1 requires a filter change to force a full resync — so the documented answer is 'resync after reorganising'. Do not build departure detection for standing exclusions; that is the deferred-id list again, wearing a different hat.

NOT A CONFIG CHOICE. Which half a term falls in follows from the term itself — role terms are transient, named terms are standing — so this needs no second config key and the user is never asked to classify anything. What it does need is one line in config.example.yaml stating the asymmetry, since 'my restored mail came back but my un-labelled mail did not' is otherwise indistinguishable from a bug.

Also in scope, because they are the same class of problem (hole numbers refer to the audit in TASK-14.1's notes):
- Hole 1: widening the filter must force a full resync. Previously-skipped messages sit below the watermark, so relaxing the filter otherwise captures nothing retroactively, silently. Detect the filter change and invalidate the watermark.
- Hole 6: keep 'do not download from here' separate from 'do not read labels from here'. _list_folders currently drops excluded folders entirely, which also removes them as label sources (_scan_gmail uses non-All-Mail folders purely for label mapping).

Depends on TASK-17: the history watermark race makes incremental sync lossy, and this task makes incremental sync the only capture path. Fixing the race first keeps the two failure modes separable.
<!-- SECTION:DESCRIPTION:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-25 06:57
---
Governing principle now recorded in doc-8 (Archival semantics): metadata is frozen once a message is captured, eligibility is re-evaluated until it is. This task is the second half of that rule.

doc-8 also adds an argument for this task independent of purge: capture timing sets label fidelity. Arrival-driven capture snapshots a message before its owner has filed it, so the archive keeps INBOX plus a CATEGORY_* and none of the user's own organizing. Moving capture to eligibility means capture-at-filing, which is what makes the capture-once policy defensible rather than merely cheap.
---
<!-- COMMENTS:END -->
