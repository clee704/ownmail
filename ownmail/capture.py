"""Capture state — what a source remembers between runs.

Incremental sync used to store one thing: a cursor. A Gmail history ID, or a
JSON map of per-folder IMAP watermarks. That is a record of what has
*arrived*, and it cannot answer the question a download filter asks, which is
about where a message is *now*. A message that arrives ineligible and becomes
eligible later sits below every watermark forever.

So a source remembers two more things alongside the cursor:

- **The membership of the transient excluded roles**, as of the last run.
  Diffing it against this run's membership turns a departure — the transition
  no watermark can express — into a plain set difference.
- **A fingerprint of the filter** that produced it, because widening the
  filter has to invalidate the cursor. Previously-skipped messages sit below
  the watermark, so relaxing the filter would otherwise capture nothing
  retroactively, and do it silently.

The membership set is REPLACED every run, never accumulated. That distinction
is what separates it from the "remember every id we skipped" design TASK-14.3
rejected: this set is bounded by the size of the excluded roles, which are
self-bounding, rather than growing with every message ever trashed.

See ``backlog/docs/doc-8`` for the ownership model this serves.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# Bumped only if the envelope's shape changes incompatibly. Its presence is
# also how a stored envelope is told apart from the legacy formats below.
VERSION = 1


@dataclass
class CaptureState:
    """A source's incremental state: cursor, excluded membership, filter."""

    cursor: str | None = None
    excluded: frozenset[str] = field(default_factory=frozenset)
    fingerprint: str | None = None

    def departed(self, current_excluded: frozenset[str]) -> frozenset[str]:
        """Ids that were excluded last run and no longer are.

        These are candidates, not downloads — a message can leave trash for
        the inbox, which is one exclusion for another. Callers subtract the
        current excluded set from the union of candidates to settle that.
        """
        return self.excluded - current_excluded

    def stale(self, fingerprint: str) -> bool:
        """Whether the filter has changed since this state was written.

        Unknown (no fingerprint recorded, i.e. state written before this
        existed) counts as unchanged. Treating it as changed would force a
        full resync on every existing archive the first time it upgrades,
        which is a large cost for a filter that demonstrably has not moved.
        """
        return self.fingerprint is not None and self.fingerprint != fingerprint


def load(raw: str | None) -> CaptureState:
    """Parse stored sync state, accepting the two formats that predate this.

    Legacy state is a cursor and nothing else: Gmail stored a bare history ID
    string, IMAP a JSON object mapping folder names to watermarks. Both are
    kept as the cursor with no excluded membership, so the first run after an
    upgrade behaves exactly as before and does not force a resync.
    """
    if not raw:
        return CaptureState()

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Gmail's bare history ID.
        return CaptureState(cursor=raw)

    if not isinstance(parsed, dict) or parsed.get("v") != VERSION:
        # IMAP's per-folder watermark map, or anything else we didn't write.
        # The provider parses it itself, so hand back the original string.
        return CaptureState(cursor=raw)

    return CaptureState(
        cursor=parsed.get("cursor"),
        excluded=frozenset(parsed.get("excluded") or ()),
        fingerprint=parsed.get("fingerprint"),
    )


def dump(state: CaptureState) -> str:
    """Serialize state for the ``sync_state`` table.

    Ids are sorted so an unchanged run produces an unchanged string, which
    keeps the stored value diffable by eye when debugging a sync.
    """
    return json.dumps(
        {
            "v": VERSION,
            "cursor": state.cursor,
            "excluded": sorted(state.excluded),
            "fingerprint": state.fingerprint,
        }
    )


def fingerprint(*parts: object) -> str:
    """A stable digest of whatever defines a source's effective filter.

    Order-insensitive, because a filter is a set: reordering ``exclude_folders``
    in config is not a filter change and must not trigger a resync.
    """
    material = "\n".join(sorted(str(p) for p in parts))
    return hashlib.sha256(material.encode()).hexdigest()[:16]
