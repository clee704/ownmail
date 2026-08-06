---
id: TASK-36
title: Label provenance — separate server-provided labels from locally-added ones
status: To Do
assignee: []
created_date: '2026-08-06 18:38'
labels: []
dependencies: []
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Labels today are a flat set with no record of where each one came from. That
conflates two different things: what the provider reported at capture, and what
the user added in ownmail. Keeping them in one bag is what forces every
server-reading operation to choose between clobbering local edits and being
unable to correct stale server state.

## Shape

Tag each label with its origin — `server` (captured from provider folders /
Gmail labels) or `local` (added by the user in ownmail). The two partitions are
disjoint and never merged in storage; the UI shows their union.

Any operation that re-reads the server then replaces the *server* partition
wholesale and leaves the *local* partition untouched. No conflict resolution is
needed because there is no conflict.

## Why it belongs with TASK-5.4

Local labels do not exist yet — there is no route, helper, or UI for adding one
(doc-8 § Status). Every label in every archive today is server-provided, so the
distinction is unobservable until local editing ships. Designing the storage
before its only writer exists would be speculative.

## What it does and does not settle

- **Settles:** a server re-read can never destroy a user's own label. This is
  what makes TASK-35's `--strategy server` safe rather than merely
  currently-harmless, and it lets `--strategy` be deleted in favour of one
  provenance-aware behaviour.
- **Does not settle:** whether post-capture server *removals* should be
  followed. Replacing the server partition wholesale does follow them, which is
  a departure from doc-8's snapshot semantics regardless of how well local
  labels are fenced off. That question needs its own answer in doc-8.

## Cost

Touches the DB schema (`email_labels` needs an origin column) and the sidecar
format (v1 is a bare `labels` list — needs a version bump with a
backward-compatible read path that treats every v1 label as `server`). Both are
STOP-list changes needing sign-off. Also touches capture, update-labels, the
query layer, and the web UI's label display.
<!-- SECTION:DESCRIPTION:END -->
