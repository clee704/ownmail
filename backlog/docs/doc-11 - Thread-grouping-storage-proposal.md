---
id: doc-11
title: Thread grouping storage proposal
type: specification
created_date: '2026-10-21 06:56'
---

## Decision

Approved by the maintainer on 2026-11-26 for
[TASK-6.1](<../tasks/task-6.1 - Derive-thread-grouping-Gmail-threadId-IMAP-Message-ID-References-chain.md>).
Thread grouping derives from `.eml` headers alone, for every provider. Two
derived database tables hold per-message header inputs and indexed thread
membership. Implementation lands through a branch and PR under CONTRIBUTING.md.

Scope is storage and membership lookup for owned and Active messages. TASK-6.2
owns list presentation, search-result grouping, visibility rules and
thread-level actions. Grouping supplies no evidence for server cleanup, whose
fresh provider checks remain authoritative. The design changes no sidecar,
Active JSON or capture format, adds no runtime dependency and contacts no
provider.

Native Gmail thread IDs are not stored. Mail already in the archive has no
stored native ID and cannot obtain one offline, so headers are the only signal
available for the archive as captured. Storing native IDs for new captures would
change both capture paths, the sidecar format and the Active cache, and would
group old and new mail by different rules. Header grouping can differ from
Gmail's own threads: Gmail joins same-subject messages without reply headers,
such as repeated notifications, and splits a thread when its subject changes.

## Storage

Both tables are disposable caches under invariant #1. Rebuilding from `.eml`
files reproduces them without network access. Schema initialization creates
them empty and scans no message on startup.

`thread_inputs` exists in every ownmail index database: the archive database
and the Active cache database. One row per indexed message holds:

| Column | Content |
|---|---|
| `email_id` | TEXT PRIMARY KEY; the message's `emails.email_id` |
| `account` | TEXT; the message's account |
| `message_id` | TEXT; its valid Message-ID, or NULL |
| `references_json` | TEXT NOT NULL; valid References identifiers in header order, as a JSON array |
| `in_reply_to_json` | TEXT NOT NULL; valid In-Reply-To identifiers, as a JSON array |
| `subject_key` | TEXT NOT NULL; the normalized subject defined under grouping rules |
| `is_reply` | INTEGER NOT NULL; 1 when normalization removed a reply or forward prefix |

Every path that writes a message's search index row also writes its inputs,
from the same parse. Deleting the `emails` row deletes its inputs and, in the
archive database, its membership row. Each store owns its inputs, so the Active cache's existing
rebuild from its files keeps Active inputs current.

`thread_members` lives in the archive database and maps `email_id` to
`thread_id` for owned and Active messages, with an index on
`(thread_id, email_id)`. It stores only components with two or more members.
A message without a row is a singleton.

## Refresh

A refresh reads `thread_inputs` from the archive database and, when it exists,
the Active cache database. It computes components with the grouping rules and
replaces `thread_members` in one transaction. Refresh scans every input once,
so callers run it at batch boundaries and never per message. An interrupted
refresh leaves the previous membership intact.

Commands that change indexed messages refresh once after their work: download
and live sync, import, scan and rebuild. `rebuild --only threads` backfills
inputs for owned messages that lack them, by parsing their `.eml` files in
committed batches, then refreshes. It is Ctrl-C safe and resumes where it
stopped. With `--force` it re-derives inputs for every owned message.

Membership can lag between refreshes. A message indexed since the last refresh
is a singleton. A removed message leaves its component joined until the next
refresh. Lookups therefore return identifiers that callers resolve through the
existing visibility rules, which already tolerate missing messages.

## Lookup

`ArchiveDatabase` returns the member IDs of a message's thread, sorted, from the
index alone. The result always contains the requested ID, and is that ID alone
when the message has no membership row or the database predates
`thread_members`. Read-only entry points open old databases without migrating
them and get the same singleton result. Lookups never parse messages or
recompute components.

## Grouping rules

1. Identifiers are `<...>` tokens without whitespace in Message-ID, References
   and In-Reply-To, compared exactly with case preserved. Malformed tokens are
   ignored, and a message without a valid Message-ID still links through its
   own reference headers. Messages sharing any identifier, as their own
   Message-ID or as a referenced one, join one component. Referenced
   identifiers that no indexed message carries still join their referrers, so
   siblings group before their parent arrives. Links may span accounts and
   stores, so an Active copy and its owned capture join through their shared
   Message-ID. Duplicate identifiers and reference cycles terminate.
2. Subject fallback runs after reference components exist. The subject key
   strips repeated leading `Re:`, `Fw:` and `Fwd:` prefixes from the decoded
   subject, collapses whitespace and case-folds. A reply or forward with a
   non-empty subject key and no valid References or In-Reply-To identifiers
   joins a candidate component other than its own, in the same account with the
   same subject key, when exactly one exists. A candidate component has two or more members, or
   contains a matching message without a reply prefix. Ambiguous replies stay
   where reference links put them. Equal subjects never join original messages
   to one another. Every fallback decision uses the reference components, so
   the result does not depend on processing order.
3. A component's `thread_id` is its smallest member `email_id`. It can change
   after a merge, split or rebuild, so callers look up membership through a
   message ID.

## Validation

Tests use synthetic messages and cover: reference chains, missing ancestors,
malformed and cyclic references, cross-account and Active-to-owned links,
subject fallback with zero, one and several candidates, original messages that
share a subject, deterministic results under reordered input, interrupted and
resumed backfill, removal followed by refresh, and singleton lookup on a
database without the new tables. A rebuild from files reproduces membership.
Lookup is checked with parsing disabled. The required pre-push gate passes and
the complete diff is reviewed before the PR opens.

[RFC 5322 section 3.6.4](https://www.rfc-editor.org/rfc/rfc5322#section-3.6.4)
defines the identification and reply-reference fields. The subject fallback and
component rules are ownmail policy.
