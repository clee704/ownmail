---
id: TASK-18
title: Gmail trash/spam exclusion is unreachable — includeSpamTrash is never set
status: Done
assignee: []
created_date: '2026-07-25 05:53'
updated_date: '2026-07-31 23:30'
labels: []
milestone: m-5
dependencies: []
priority: medium
ordinal: 2
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
gmail.py:142-147 builds the message listing request without the includeSpamTrash parameter:

    request_args = {"userId": "me", "pageToken": ..., "maxResults": 500, "q": query}

users.messages.list defaults includeSpamTrash to False, so trash and spam are already excluded before the query string is considered. The '-in:trash -in:spam' hardcoded into q (gmail.py:130) is therefore redundant — it restates the API default.

Not currently losing data: the effective behaviour is the intended one. Two problems with it anyway:

1. MISLEADING. The query term looks like the mechanism controlling trash/spam exclusion. It is not. Anyone changing the filter would edit the query string and observe no behaviour change, with no indication why.
2. THE INCLUSION PATH DOES NOT EXIST. There is no way to ask Gmail for trashed messages, because that requires includeSpamTrash=True and nothing sets it. This is exactly the configuration doc-6 resolved TASK-15 with: removing 'trash' from the download filter is how a user opts into capturing mail deleted in a mail client before the provider's retention window closes. That option would silently do nothing.

FIX: drive includeSpamTrash from the same place the filter decides trash/spam, and drop the redundant query terms (or keep them only where they express something the parameter cannot). Note the parameter is all-or-nothing across both trash AND spam, so a filter excluding one but not the other needs the query string as well — worth checking the combination behaves as expected rather than assuming.

Blocks TASK-14.1: the filter cannot be honestly described as configurable while one of its values is unreachable.

Related, found while checking: DRAFT-labelled messages ARE downloaded today (confirmed against a real archive), consistent with doc-6 noting that excluding drafts is the only default behaviour change TASK-14 introduces. includeSpamTrash does not affect drafts; excluding them needs a query term or a labelIds check.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Trash/spam exclusion on the full-sync path is expressed once, at the mechanism that performs it — the redundant '-in:trash -in:spam' query terms are gone
- [x] #2 messages.list sets includeSpamTrash explicitly rather than relying on an invisible API default
- [x] #3 Effective behaviour is unchanged: full syncs still exclude trash and spam, and the history path still filters them by labelIds
- [x] #4 A test fails if the redundant query terms return, and a second fails if the parameter is dropped — both confirmed against deliberately broken code
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
RESCOPED 2026-07-31. Argument 2 above ("THE INCLUSION PATH DOES NOT EXIST") is dead. It rested on doc-6's resolution of TASK-15, where removing "trash" from the download filter was a supported configuration. TASK-14.1 reversed that on 2026-07-26: trash and spam are permanently excluded, with no way to opt in. Nothing will ever need includeSpamTrash=True, so there is no unreachable config value to make reachable.

What survives:

- Argument 1 (MISLEADING) stands unchanged. The `-in:trash -in:spam` in `q` looks like the mechanism and is not. Under TASK-14.1 the filter becomes the single place trash/spam exclusion is expressed, so a redundant query term restating an API default in a second place is exactly the kind of duplication that task exists to remove.
- The DRAFTS half is now the load-bearing part. includeSpamTrash does not affect drafts, and drafts are a configurable exclusion under TASK-14.1, so excluding them needs a real mechanism — a query term or a labelIds check. That is genuine filter work, not cleanup.

CONSEQUENCE FOR SEQUENCING: this no longer blocks TASK-14.1 on correctness grounds. It is kept ahead of it in the m-5 order as cheap tidy-up in the same file, done first so the filter is built over one exclusion mechanism rather than layered on top of a misleading one. If it slips behind TASK-14.1, nothing breaks. See doc-4 Phase 5.

## Done 2026-07-31

`get_all_message_ids` no longer seeds its query with `-in:trash -in:spam`; the query now carries date terms only, and can be empty. `messages.list` passes `includeSpamTrash=False` explicitly, with the comment sitting on the parameter rather than anywhere else — that is the whole mechanism for this path, and the comment says so, says the parameter is all-or-nothing over exactly the two roles in `DEFAULT_EXCLUDE_ROLES`, and says a third exclusion will need a query term or labelIds check of its own. `_is_excluded`'s docstring no longer claims to mirror a query that no longer exists; it now names the real asymmetry — `history.list` has no such parameter, so it filters client-side on labelIds.

No behaviour change, by design: parameter False plus no query terms returns the same set as parameter False plus redundant query terms.

DRAFTS WAS NOT BUILT HERE, deliberately. Turning drafts into an exclusion means putting DRAFTS in the excluded role set, and that set is shared with imap.py — it is a default-behaviour change, and doc-6 calls excluding drafts the only one TASK-14 introduces. TASK-14.1 owns the decision (its description already reserves it) and now owns the mechanism too. Building the query term here would have left a role nothing selects: dead code by AGENTS.md, and unverifiable besides, since no test can exercise an exclusion the role set never asks for. What this task leaves 14.1 is the honest surface it needed — one visible mechanism per path, no decoy.

VERIFIED BY BREAKING THE CODE, both directions: dropping `includeSpamTrash` fails `test_trash_and_spam_excluded_by_request_parameter`; putting `-in:trash -in:spam` back fails that test and `test_date_filters_become_query_terms`. The old `test_trash_and_spam_always_excluded` was rewritten rather than duplicated — it asserted the redundant query string, so it was pinning the misleading structure in place.

STILL UNVERIFIED AGAINST THE LIVE API, and worth flagging for 14.1: the Gmail search operator for drafts was not settled here. `is:draft` and `in:draft` are both plausible and a wrong guess fails silently — Gmail would read the term as a user label name and filter nothing. Confirm it against a real account before relying on it.
<!-- SECTION:NOTES:END -->
