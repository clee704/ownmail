---
id: TASK-18
title: Gmail trash/spam exclusion is unreachable — includeSpamTrash is never set
status: To Do
assignee: []
created_date: '2026-07-25 05:53'
updated_date: '2026-07-31 22:54'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
RESCOPED 2026-07-31. Argument 2 above ("THE INCLUSION PATH DOES NOT EXIST") is dead. It rested on doc-6's resolution of TASK-15, where removing "trash" from the download filter was a supported configuration. TASK-14.1 reversed that on 2026-07-26: trash and spam are permanently excluded, with no way to opt in. Nothing will ever need includeSpamTrash=True, so there is no unreachable config value to make reachable.

What survives:

- Argument 1 (MISLEADING) stands unchanged. The `-in:trash -in:spam` in `q` looks like the mechanism and is not. Under TASK-14.1 the filter becomes the single place trash/spam exclusion is expressed, so a redundant query term restating an API default in a second place is exactly the kind of duplication that task exists to remove.
- The DRAFTS half is now the load-bearing part. includeSpamTrash does not affect drafts, and drafts are a configurable exclusion under TASK-14.1, so excluding them needs a real mechanism — a query term or a labelIds check. That is genuine filter work, not cleanup.

CONSEQUENCE FOR SEQUENCING: this no longer blocks TASK-14.1 on correctness grounds. It is kept ahead of it in the m-5 order as cheap tidy-up in the same file, done first so the filter is built over one exclusion mechanism rather than layered on top of a misleading one. If it slips behind TASK-14.1, nothing breaks. See doc-4 Phase 5.
<!-- SECTION:NOTES:END -->
