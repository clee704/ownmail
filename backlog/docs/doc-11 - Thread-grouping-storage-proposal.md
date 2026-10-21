---
id: doc-11
title: Thread grouping storage proposal
type: specification
created_date: '2026-10-21 06:56'
---

## Decision awaiting approval

[TASK-6.1](<../tasks/task-6.1 - Derive-thread-grouping-Gmail-threadId-IMAP-Message-ID-References-chain.md>)
will retain native Gmail thread metadata in message sidecars and Active JSON,
then derive one indexed membership table spanning owned and Active messages.
Approval covers the additive schema, metadata format and grouping rules below.
Implementation must use a branch and PR under CONTRIBUTING.md.

Scope is storage and membership lookup. TASK-6.2 owns list presentation,
search-result grouping and thread-level actions. UI grouping supplies no evidence
for server cleanup; its existing fresh provider checks remain authoritative.
This proposal adds no runtime dependency and requires no OAuth changes.

## Durable metadata

Add an optional top-level `thread` object to archive sidecars and Active entries:

```json
{"thread": {"provider": "gmail", "account": "owner@example.test", "id": "1234abcd"}}
```

The example ID is a hexadecimal string. Normalize Gmail API IDs and Gmail IMAP
`X-GM-THRID` values to lowercase hexadecimal. Scope them by provider and account;
the same number from different accounts is insufficient to join conversations.
The existing live IMAP parser already converts decimal IDs to hexadecimal.
Generic IMAP and imported messages may omit the object.

Keep sidecar version 1: this optional field extends the existing object, and
current readers tolerate additional fields. Validate it independently; malformed
thread metadata is reported and ignored for grouping while the message remains
available. Keep capture provenance unchanged. Preserve other sidecar fields on
every label-only update, including maintenance and relabel operations. Refuse
to overwrite unreadable existing metadata during such an update.

Propagate native metadata through both legacy downloads and live capture. Save it
atomically alongside labels before recording successful capture. Active saves
retain it before indexing. Required metadata-write failures leave capture
retryable under the existing rules.
New Gmail captures require a valid native ID from the provider response;
missing or invalid IDs are retryable failures. Compatibility with old metadata
does not relax that requirement for new captures.

Old sidecars and Active entries remain valid. Rebuild derives their groups from
headers without network requests. Previously discarded native IDs cannot be
recovered offline, and ordinary refresh skips already-owned copies. Historical
native-ID enrichment is out of scope; no automatic server backfill is proposed.

## Rebuildable database cache

Create `thread_members` in the archive database. It also holds derived inputs
for cached Active messages, whose IDs already differ from owned message IDs.
It adds no columns to `emails` and preserves existing rows and full-text data.

| Column | Type and purpose |
|---|---|
| `email_id` | TEXT PRIMARY KEY; existing owned or Active ID |
| `store` | TEXT NOT NULL; `owned` or `active` |
| `account` | TEXT; account used for subject fallback |
| `native_key` | TEXT; canonical encoding of the validated native thread object |
| `message_id` | TEXT; parsed Message-ID, if valid |
| `references_json` | TEXT NOT NULL; ordered valid References IDs as a JSON array |
| `in_reply_to_json` | TEXT NOT NULL; valid In-Reply-To IDs as a JSON array |
| `subject_key` | TEXT NOT NULL; normalized decoded subject |
| `is_reply` | INTEGER NOT NULL; subject had a recognized reply/forward prefix |
| `thread_id` | TEXT NOT NULL; computed component identifier |

Add an index on `(thread_id, email_id)`. This table is entirely disposable:
headers come from `.eml` files, native keys from sidecars or Active JSON.
Derived component IDs never become authoritative sidecar metadata.

Reuse the existing schema-initialization and batch transaction conventions.
Migration creates an empty table and index without scanning message bodies on
startup. Add `rebuild --only threads` to populate missing inputs and repair
membership from local files; a full forced rebuild also includes thread data.
The backfill commits bounded batches and is interruptible and restartable.
Until backfilled, an otherwise available message without membership is treated
as a singleton. Read-only entry points accept old databases without migrating
them and apply the same singleton behavior.

Capture, import, scan, rebuild and Active refresh update cached inputs. At batch
boundaries, compute components from those inputs and commit membership changes
atomically. A first implementation may scan all cached inputs once per completed
batch; it must avoid a full graph pass for each message. Lookups use the index
and never parse the archive or recompute the graph on each request.

Remove obsolete inputs when a message leaves its store, and recompute components
after removals so a stale bridge cannot keep unrelated messages joined. Handle
Active-to-owned transitions, linked legacy copies, cache recovery and disabled
sources through existing visibility and identity rules. Group lookup returns
each visible logical message once and keeps local Trash separate from normal
results. Active entries remain under server authority even though their derived
membership resides in the archive database.

## Grouping rules

1. Extract valid identifiers from Message-ID, References and In-Reply-To using
   the existing parser's header handling. Preserve identifier case and ignore
   malformed tokens. Connect messages with the same scoped native key or exact
   header identifiers. Missing ancestors remain graph nodes so siblings can
   join before their parent arrives. Exact header links may span accounts.
   Cycles and duplicate identifiers must terminate deterministically.
2. Reference links and native keys establish components before subject fallback.
   Strip repeated leading `Re:`, `Fw:` and `Fwd:` prefixes, collapse whitespace
   and case-fold the decoded subject. An unlinked reply/forward with no valid
   reference headers may join exactly one candidate component with the same
   non-empty subject in the same account. It must have no native key of its own.
   Candidate components have native/reference evidence or a matching message
   without a reply prefix. Ambiguous replies remain singletons; equal subjects
   alone never merge independent original messages. Reconsider fallback when
   the available components change.
3. Choose component IDs deterministically from their members. IDs may change
   after a merge, split or rebuild; callers look up membership using an existing
   message ID. Native metadata and exact header links can produce a group that
   differs from Gmail's current UI. Grouping is a local display heuristic.

## Evidence and validation

At review base `0c6bd26`, `LiveMessage.thread_id` exists, and both live providers
populate it. `ActiveCache.put`, `live_sync._capture` and the legacy download
results discard it. The parser's indexing result omits reference headers, and
the rebuild command has a separate SQL indexing path. `sidecar.write_labels`
replaces the entire object; preserving metadata there is necessary before
adding durable thread fields.

Gmail defines `threadId` in its [message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages).
Its [IMAP extension](https://developers.google.com/workspace/gmail/imap/imap-extensions#access_to_the_gmail_thread_id_x-gm-thrid)
returns the corresponding thread ID as a decimal integer.
[RFC 5322 section 3.6.4](https://www.rfc-editor.org/rfc/rfc5322#section-3.6.4)
defines the identification and reply-reference fields. The subject fallback and
component rules above are ownmail policy.

After approval, verify native metadata capture and label-edit preservation,
legacy metadata compatibility, missing ancestors, malformed/cyclic references,
cross-account links, scoped native-ID collisions, ambiguous subjects and
deterministic arrival order. Exercise Active-to-owned transitions, cache loss,
Trash visibility and interrupted backfill. Rebuilding both indexes from files
must reproduce membership without contacting a provider. Check indexed lookup
with parsing and regrouping disabled, then run the required pre-push gate and
review the complete implementation diff before opening the PR.
