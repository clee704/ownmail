---
id: TASK-14.1
title: Configurable download filter in canonical role terms
status: To Do
assignee: []
created_date: '2026-07-25 05:38'
updated_date: '2026-07-25 05:53'
labels: []
milestone: m-5
dependencies:
  - TASK-14.3
  - TASK-18
parent_task_id: TASK-14
priority: high
ordinal: 4
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Knob 2 of doc-6. Split out of TASK-14 because it is NOT a STOP item: it changes only what gets downloaded, deleting nothing and needing no OAuth scope change.

**Rescoped 2026-07-25 to the config surface only.** The hole audit (see this task's Implementation Notes) showed the machinery underneath was the large half. It now lives in TASK-14.3 (eligibility-driven capture), TASK-17 (history watermark race) and TASK-18 (unreachable includeSpamTrash). What remains here:

- A per-source download filter written in canonical role terms (roles.py, TASK-5.2). Per-source for consistency with exclude_folders, which is already per-source — decided, not defaulted.
- Filter is defined as EXCLUSIONS ONLY. Gmail has no ARCHIVE label — archived means the absence of INBOX — so an inclusion-shaped filter is unresolvable there while being well-defined for IMAP SPECIAL-USE \\Archive (audit hole 4).
- Unify the three existing filter sites into that one mechanism: imap.py exclude_folders, gmail.py's query terms, gmail.py's TRASH/SPAM labelIds re-check. Retire exclude_folders in favour of role terms, or define precisely how the two compose.
- Default filter excludes INBOX, TRASH and SPAM (user, 2026-07-26 — this supersedes the earlier 'trash, spam and drafts' default, which left inbox out). One rationale covers all three: the filter admits a message only once its owner has acted on it. Trash and spam mean a decision was made that the message is not worth keeping — by the user or by the provider. Inbox means no decision has been made yet; the message is still live in the mail client.
- Drafts: doc-6 had them in the default too, on the grounds that they are live working state. Not in the user's 2026-07-26 list. Keep or drop deliberately when implementing rather than inheriting either version by accident.
- TRASH AND SPAM ARE NOT CONFIGURABLE (user, 2026-07-26). Only part of the exclusion set is a knob. Configurable: inbox, drafts, and named folders/labels. Fixed: trash and spam, always excluded, with no way to opt in. Reasoning below under WHY TRASH IS FIXED. This reverses doc-6's resolution of TASK-15, which closed that question by making trash a config choice.
- THE FILTER IS THE WHOLE MECHANISM. There is no separate rule about which labels the archive inherits. A correct filter downloads a message only when it is not in inbox, trash or spam, so it cannot be carrying those labels at download time, and a healthy archive ends up with none of them without anything stripping them. An idea to strip these labels at capture as a second mechanism was raised and rejected on 2026-07-26 as redundant with the filter.
- config.example.yaml documents the filter, and documents that WIDENING it requires a full resync (audit hole 1, mechanism in TASK-14.3) and that NARROWING it makes the next purge run delete more (doc-6, once TASK-14.2 exists).

FILTERING IS NOT PERMANENT EXCLUSION (user, 2026-07-26). A filtered-out message is re-checked every run, not written off. Trash -> inbox -> archive means it becomes eligible and gets downloaded then. This is the same rule doc-8 states as 'eligibility is re-evaluated until capture succeeds' and TASK-14.3 implements; recorded here because it is what makes an exclusion-only default safe rather than lossy. The one-way door is capture, not filtering: once downloaded, ownmail never looks at the server's copy of that message again, even if it changes.

WHY TRASH IS FIXED RATHER THAN CONFIGURABLE (2026-07-26). Four arguments, strongest first.

1. PURGE DOES NOT CONVERGE OTHERWISE. This is structural, not a preference. doc-6 defines purge as a sweep over "every server message that passes the current filter and has a verified local copy", and defines purging as MOVE TO TRASH. With trash excluded, a purged message lands in trash, stops passing the filter, and leaves the sweep set — the sweep converges. With trash in the download set it keeps passing the filter forever, so the sweep set grows monotonically with every purge and every run re-processes every message ever purged. The only fix would be a "skip messages already in trash" special case inside purge, which is the trash exclusion again, reintroduced one layer down. doc-6 noted the exclusion "closes the loop" but did not record that the loop cannot be closed any other way. NOTE: this argument is specific to TRASH. Purge's destination is Trash, not Spam, so including spam does not break convergence — spam is fixed on the weaker grounds below.

2. RE-EVALUATION ALREADY COVERS THE RECOVERABLE CASES, so the knob buys nothing. Deleted something by mistake, or lost real mail to a spam false positive? Restore it in the mail client and it becomes eligible on the next run — filtering is not permanent exclusion (see above). The knob would only add the case "I deleted it, I meant it, and I still want it archived", which contradicts the model the default rests on: the filter admits a message once its owner has ACTED on it, and discarding is an action.

3. IT IS THE ONLY FILTER VALUE THAT COLLIDES WITH AN OWNMAIL CONCEPT. ownmail owns a local bin, also called Trash. Allowing server trash into the archive makes two unrelated things permanently share a name in the UI — the "Trash (server)" entry in doc-9. Fixing the exclusion makes that entry transitional instead: it can then only appear in an archive that predates role-based exclusion, so it is a signal that TASK-25 reconcile has not been run, and it disappears for good once it has.

4. NO KNOWN CONSUMER. AGENTS.md says write for what is needed now; doc-9 says this repo does not add knobs on spec.

ACCEPTED COST, and it must be documented rather than discovered: a message deleted in a mail client and never restored is never archived, so the two-path architecture has a permanent capture gap for anyone whose "delete" means "file it away". That is TASK-15 AC #3 — the loss window is documented so it is a known choice. REVISIT TRIGGER: a real user reporting they use delete-as-archive. Not before.

WHY EXCLUDING INBOX MATTERS INDEPENDENTLY OF PURGE (user, 2026-07-25): doc-6 justifies the inbox exclusion only via purge safety. A second, independent reason holds with purge off. In the two-path model the mail client owns triage, so inbox means 'not yet decided'. If ownmail archives inbox mail, a message the user later deletes in the client is already captured, and the delete decision has to be made a second time in ownmail. Adverts, one-time codes and similar arrive in the inbox, get deleted in the client, and would otherwise persist in the archive forever.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Hole audit, 2026-07-25

Verified against code, not inferred from doc-6. Two were found by the user (inbox capture, and trash→restore); the rest came from auditing the paths the filter would run through.

### Capture-losing

1. **Widening the filter silently captures nothing.** doc-6 records that *narrowing* the filter is destructive under purge sweep. The mirror is unrecorded and worse for being silent: under watermark-based incremental sync everything previously skipped sits *below* the watermark, so removing `inbox` from the exclusions later captures nothing retroactively — no error, just an archive permanently missing that mail. A filter change must force a full resync (detect the change, reset the watermark) or the option is a trap.

2. **Gmail history watermark race** (gmail.py:191-192). `_get_messages_since_history()` lists history, then a *separate* `get_current_sync_state()` getProfile call supplies the new watermark. A message arriving between the two calls has a historyId below the new watermark but was never listed → missed permanently. The `history.list` response carries its own `historyId`, which is the correct watermark; it is discarded. Pre-existing, but currently masked by eager inbox capture. Under a filter, incremental sync becomes the only capture path, so this goes from rare to load-bearing. Fix: take the watermark from the history response.

3. **`includeSpamTrash` is a request parameter, not a query term** (gmail.py:142-147). `users.messages.list` defaults it to False and the request never sets it, so the `-in:trash -in:spam` in `q` is redundant today. Consequence: removing `trash` from the filter would silently do nothing, which is precisely the config the option exists for (capturing client-side deletions, the old TASK-15). The filter must drive the API parameter as well as the query.

### Design-level

4. **Role vocabulary is asymmetric — the filter must be exclusion-only.** Gmail has no ARCHIVE label; archived means the *absence* of INBOX, which is why roles.py's Gmail map has no archive entry. A filter phrased as an inclusion ("download only archive") is well-defined for IMAP `\Archive` and unresolvable on Gmail. State exclusion-only in the config contract.

5. **Gmail-over-IMAP cannot answer "is it still in INBOX?" incrementally** (imap.py:546-551). Non-All-Mail folders contribute membership only for UIDs above their watermark. Arrival works (new in All Mail implies new in INBOX); departure does not, because a message leaving INBOX merely makes its UID vanish and nothing detects removal. Filtering on inbox requires *current* membership, so INBOX must be fully rescanned each run — cheap, since the inbox is bounded, but not what the code does.

6. **Exclusion is folder-scoped; the filter must be message-scoped.** `_list_folders` drops excluded folders entirely, which also removes them as *label sources* — `_scan_gmail` uses non-All-Mail folders purely for label mapping. Excluding INBOX on Gmail-over-IMAP would silently stop INBOX ever being recorded as a label. The unified mechanism must keep "don't download from here" separate from "don't read labels from here".

### Lesser

7. Sync state advances only when `error_count == 0` (archive.py:468). Correct today, but one reliably-failing message freezes the watermark indefinitely, and under candidate re-evaluation the frozen window is what gets re-checked every run.

8. Per-source vs global filter is unspecified in doc-6. `exclude_folders` is already per-source, so per-source is the consistent answer — decide it rather than defaulting into it.

### The pattern, and what it means for scope

Holes 1, 2, 3, 5 and both user-found ones are one shape: **the filter is a statement about current server state, while every mechanism underneath it is a statement about arrival.** Watermarks, `messageAdded`, folder-membership snapshots — all arrival-shaped.

doc-6 already named the right principle for purge ("the filter is evaluated live against server state at purge time"). The finding is that this is not a purge property; it is what a filter *is*. Applying it at download time is the actual work.

**This makes 14.1 materially bigger than "expose a config option" as doc-6 implies.** Re-estimate before starting, and consider whether the eligibility-driven capture rework wants to be its own task with the config surface layered on top.
<!-- SECTION:NOTES:END -->
