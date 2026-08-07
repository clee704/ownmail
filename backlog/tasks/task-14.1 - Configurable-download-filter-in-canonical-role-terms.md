---
id: TASK-14.1
title: Configurable download filter in canonical role terms
status: Done
assignee: []
created_date: '2026-07-25 05:38'
updated_date: '2026-08-07 18:40'
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
- SENT IS DELIBERATELY ADMITTED, and must not be 'fixed' into the default exclusions later. Outgoing mail has no triage step — nobody files their Sent folder — so a rule demanding an action before capture would mean never archiving the user's own mail. Sending IS the settling action: it cannot be undone and the content is final. Accepted cost, the mirror of the inbox argument: deleting your own sent mail afterwards does not un-archive it. Rare enough to be worth it, and bounded by purge, which removes the server copy so the two cannot keep diverging. Sent gets no special handling anywhere — a proposal to exempt it from purge was rejected on 2026-07-26; see TASK-14.2 for why.
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

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A per-source exclude_roles option is read from config and drives download exclusion on both providers; a role outside the configurable set is rejected by validate_config with a message that distinguishes always-excluded (trash, spam) from roles that are not filter terms
- [x] #2 With no config, the effective filter on both gmail_api and imap sources excludes inbox, drafts, trash and spam
- [x] #3 Trash and spam are excluded whatever exclude_roles and exclude_folders say — no configuration admits them
- [x] #4 exclude_folders is additive to role exclusion rather than replacing it; a named exclusion stays a label source, a role exclusion does not
- [x] #5 Gmail API: inbox and drafts membership is enumerated live each run, so inbox/draft mail is never captured — including on date-filtered runs — and mail leaving the inbox becomes a candidate
- [x] #6 Gmail-over-IMAP: All Mail candidates are filtered by current inbox/draft membership answered in All-Mail UID space, and that membership is diffed across runs so a message that merely loses the inbox label becomes a candidate
- [x] #7 Changing exclude_roles changes the filter fingerprint, forcing a rescan on the next run
- [x] #8 config.example.yaml documents the filter, the fixed trash/spam exclusion, that widening forces a full resync, and that narrowing makes a future purge delete more
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Landed 2026-08-07

Three commits: the mechanism, the tests, the README. Every AC verified by a
test checked against deliberately broken code (eleven breaks, each caught by
exactly the tests meant to catch it).

### The config surface as built

`exclude_roles`, per source, on both provider types. Values: `inbox`,
`drafts`. Naming `trash` or `spam` is a CONFIG ERROR rather than a silent
no-op — accepting it would leave the reader believing that removing it again
re-admits trash, which is the exact false belief the fixed exclusion exists
to prevent. `[]` is honoured as written (fixed roles only); absent takes the
default. That distinction matters and is why `resolve_exclude_roles` checks
`is None` rather than truthiness.

Drafts is excluded, per the 2026-08-06 amendment.

### exclude_folders: composition settled as ADDITIVE

The description left "retire it or define how the two compose" open. It
stays, as the by-name escape hatch for folders no role describes, and it now
ADDS to the role exclusion instead of replacing it wholesale. The old
replace semantics had exactly one purpose — opting into archiving your own
trash — and that configuration is gone by decision, so the semantics had no
remaining consumer. Removing it also collapsed `_is_label_source` to
`role not in excluded_roles`: a NAMED exclusion is still a label source, a
ROLE exclusion never is. Two test expectations were deliberately reversed
here, and one setup test: setup now REPORTS the server's excluded folder
names instead of writing them into the config as a commented block.

### The Gmail-over-IMAP hole, which was the real work

All Mail is that path's sole download source, so filing an inbox message
does not move it — it keeps its UID and loses a label. Neither a watermark
nor the folder scan can see that (INBOX is excluded, and its UIDs are a
different UID space anyway). Membership is now read in All-Mail UID space
and diffed across runs, the same shape TASK-14.3 built for the Gmail API.

`X-GM-RAW "in:inbox"` for inbox, as TASK-14.3 predicted. **Drafts uses the
RFC 3501 `DRAFT` flag search, not a Gmail term** — that closes TASK-18's
open `is:draft` vs `in:draft` question a second way, by not asking Gmail at
all. Standard IMAP, exact, and it cannot fail silently the way an
unrecognized X-GM-RAW term would.

A failed SEARCH RAISES. The graceful answer — an empty excluded set — would
capture the entire inbox, so this is a correctness failure for the run, not
a skippable message.

Plain IMAP needed nothing: a folder move is a delivery, so the destination
allocates a UID above its watermark and the departure arrives as an arrival.

### Ordering, absorbed from a near-miss

Both providers now read excluded membership BEFORE listing arrivals and
persist that same snapshot. Enumerating afterwards lets a message filed
mid-run fall out of both the listing and the stored membership, so the next
run's diff never sees it — the same shape as the watermark bug TASK-14.3
fixed in its full-sync path. The accepted cost is the mirror: a message that
ENTERS an excluded role mid-listing is captured one run early. Eager beats
lossy.

Consequence worth knowing: on the Gmail API path the enumeration now runs
before `history.list`, so it happens even on runs that then fail.

### Date-filtered runs are filtered too

`--since` used to be filtered only incidentally, by `includeSpamTrash=False`.
Left alone it would have become a way to pull in the inbox mail every other
path defers. `get_all_message_ids` now means "everything currently
ELIGIBLE" on both providers rather than "everything on the server", which
also fixes `sync-check`: it would otherwise have reported the whole inbox as
missing and told the user to run `download`.

### First run after upgrade

The default filter changed, so the stored fingerprint is stale on every
existing archive and the first run rescans. Correct but strictly
unnecessary: this is a NARROWING, and only widening can capture anything
retroactively. `stale()` does not track direction and should not learn to —
a one-off full scan re-reads folders without re-downloading, and the
conservative answer is the right default. Nothing already archived is
removed; that is TASK-25's job.

### Not done, deliberately

`X-GM-RAW "in:inbox"` has not been confirmed against a real Gmail account —
only against mocks. The operator itself is documented and stable (unlike
`is:draft`, which is why drafts avoids the question entirely), but the
failure mode if it is wrong is the loud one, not the silent one: Gmail would
read it as a user label, the search would return nothing, and the whole
inbox would be captured on the next run. Worth one look at a real archive
before purge is enabled.
<!-- SECTION:NOTES:END -->

## Comments

<!-- COMMENTS:BEGIN -->
created: 2026-07-31 23:30
---
From TASK-18 (done 2026-07-31): the drafts exclusion mechanism is yours, not built there. gmail.py now excludes trash and spam solely via `includeSpamTrash=False` on `messages.list`, and that parameter is all-or-nothing over those two roles — it cannot express drafts, inbox, sent or a named label. Every further exclusion this filter grows needs a query term (full-sync path) *and* a labelIds check (history path); `_is_excluded` is the second one and already reads the role set. TASK-18 stopped short of adding DRAFTS to the excluded set because that set is shared with imap.py, making it the default-behaviour change doc-6 attributes to TASK-14. Also unsettled: whether the Gmail search operator is `is:draft` or `in:draft`. A wrong guess fails silently — Gmail reads an unknown term as a user label name and filters nothing — so confirm against a real account rather than a mock.
---
<!-- COMMENTS:END -->
