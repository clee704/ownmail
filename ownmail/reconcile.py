"""What in the archive the current download filter would no longer admit.

The download filter decides what enters the archive. It says nothing about
what is already in there, and it moves: a bug fix widens it, a config edit
narrows it. Reconcile is that filter evaluated in the other direction —

    purge      sweeps the SERVER  for mail the filter admits and that is
               safely archived, and trashes the server copy
    reconcile  sweeps the ARCHIVE for mail the filter now rejects, and moves
               it to ownmail's bin

— which is why it is a standing capability and not a migration. See TASK-25.

Reconcile cannot be as precise as the filter it mirrors. The filter reads live
server state; here there is only what was stored at capture, so this is a
heuristic over a snapshot. That is the whole reason the destination is the bin
and not a delete: every answer is reversible.

Two things follow from working off stored labels. It only finds mail whose
excluded role was *recorded* as a label — the historical trash-folder bug and
any narrowing filter edit both satisfy that. And it has to be told apart from
mail that merely passes through an excluded place: a message carrying a real
label alongside the excluded one was filed somewhere, so it is reported and
left where it is.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ownmail import roles

# Labels that are not evidence a message was ever filed anywhere.
#
# Gmail hangs its own classifiers on mail nobody has touched — IMPORTANT is its
# guess, CATEGORY_* is its bucketing — so a message carrying only those and an
# excluded label was never acted on, and treating them as filing would put
# every Gmail archive in the report-only pile. STARRED is deliberately absent:
# starring is something the owner did.
#
# UNREAD joins them for archives synced before TASK-5.3, which stored it.
# Exact-match Gmail label IDs throughout, for the reason in
# roles.STALE_STATE_LABELS: a case-folded match would hide a real folder.
NON_FILING_LABELS = (
    frozenset(
        {
            "IMPORTANT",
            "CATEGORY_PERSONAL",
            "CATEGORY_SOCIAL",
            "CATEGORY_PROMOTIONS",
            "CATEGORY_UPDATES",
            "CATEGORY_FORUMS",
        }
    )
    | roles.EPHEMERAL_LABELS
)


@dataclass(frozen=True)
class SourceFilter:
    """One source's effective download filter, as reconcile reads it."""

    name: str
    account: str
    exclude_roles: frozenset[str]
    exclude_folders: frozenset[str]

    def rejects(self, label: str) -> bool:
        """Whether this label alone would keep a message out of the archive.

        Folders are matched by exact name because that is how the filter
        matches them at download time; roles by resolving the stored string,
        which is the accepted imprecision above.
        """
        if label in self.exclude_folders:
            return True
        return roles.role_for_label(label) in self.exclude_roles

    def describe(self) -> str:
        """The filter in one line, for the report."""
        parts = [f"roles: {', '.join(sorted(self.exclude_roles))}"]
        if self.exclude_folders:
            parts.append(f"folders: {', '.join(sorted(self.exclude_folders))}")
        return "; ".join(parts)


@dataclass(frozen=True)
class Candidate:
    """An archived message the filter would now reject."""

    email_id: str
    account: str
    rejected: tuple[str, ...]
    kept: tuple[str, ...]


@dataclass
class Plan:
    """Everything a reconcile run found, before anything moves."""

    filters: list[SourceFilter] = field(default_factory=list)
    sweep: list[Candidate] = field(default_factory=list)
    reported: list[Candidate] = field(default_factory=list)
    unconfigured: list[tuple[str, int]] = field(default_factory=list)


def source_filters(config: dict) -> list[SourceFilter]:
    """The configured download filter of every source, one per account.

    Read from config on every run rather than baked in, so that editing
    ``exclude_roles`` or ``exclude_folders`` changes what reconcile finds with
    no code change. Two sources on one account would be indistinguishable
    afterwards — every archived row records the account, not the source — so
    the first one wins, as elsewhere in ownmail.
    """
    filters = {}
    for source in config.get("sources", []):
        account = source.get("account")
        if not account or account in filters:
            continue
        filters[account] = SourceFilter(
            name=source.get("name", account),
            account=account,
            exclude_roles=roles.resolve_exclude_roles(source.get("exclude_roles")),
            exclude_folders=frozenset(source.get("exclude_folders") or ()),
        )
    return list(filters.values())


def classify(email_id: str, account: str, labels: list[str], source_filter: SourceFilter) -> Candidate | None:
    """Decide what one archived message's stored labels mean.

    Returns None when the filter has no objection to it. Otherwise the
    candidate's ``kept`` labels are the evidence that it was filed somewhere
    real — empty means the message exists in the archive only because of a
    place the filter now rejects, and it can be swept.
    """
    rejected = [label for label in labels if source_filter.rejects(label)]
    if not rejected:
        return None
    kept = [
        label
        for label in labels
        if label not in rejected and label not in NON_FILING_LABELS and roles.role_for_label(label) != roles.ALL
    ]
    return Candidate(email_id=email_id, account=account, rejected=tuple(sorted(rejected)), kept=tuple(sorted(kept)))


def build_plan(db_path: Path, config: dict) -> Plan:
    """Sweep the archive against every configured source's filter.

    Messages already in ownmail's bin are skipped — they have been dealt with,
    and re-reporting them would make an applied run look like it did nothing.
    """
    plan = Plan(filters=source_filters(config))
    by_account = {f.account: f for f in plan.filters}

    with sqlite3.connect(db_path) as conn:
        plan.unconfigured = _unconfigured_accounts(conn, by_account)
        if not by_account:
            return plan

        rejected_labels = {
            label
            for (label,) in conn.execute("SELECT DISTINCT label FROM email_labels")
            if any(f.rejects(label) for f in plan.filters)
        }
        if not rejected_labels:
            return plan

        placeholders = ",".join("?" for _ in rejected_labels)
        rows = conn.execute(
            f"""
            SELECT e.email_id, e.account, el.label
            FROM emails e
            JOIN email_labels el ON el.email_rowid = e.rowid
            WHERE e.trashed_at IS NULL
              AND e.rowid IN (SELECT email_rowid FROM email_labels WHERE label IN ({placeholders}))
            ORDER BY e.email_id
            """,
            sorted(rejected_labels),
        ).fetchall()

    for email_id, account, labels in _group_by_email(rows):
        source_filter = by_account.get(account)
        if not source_filter:
            continue
        candidate = classify(email_id, account, labels, source_filter)
        if candidate:
            (plan.reported if candidate.kept else plan.sweep).append(candidate)

    return plan


def counts_by_label(candidates: list[Candidate]) -> list[tuple[str, str, int]]:
    """Break a set of candidates down as (label, account, count), largest first.

    A message rejected for two reasons is counted under both, so these sum to
    more than the message count — the point of the breakdown is to show which
    part of the filter is responsible.
    """
    counts: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        for label in candidate.rejected:
            key = (label, candidate.account)
            counts[key] = counts.get(key, 0) + 1
    return sorted(((label, account, count) for (label, account), count in counts.items()), key=lambda row: -row[2])


def _unconfigured_accounts(conn: sqlite3.Connection, by_account: dict) -> list[tuple[str, int]]:
    """Archived mail belonging to no configured source, which reconcile skips.

    Imported mail lands here (``import`` takes the account from the From
    header), as does a source the operator has since removed from config.
    There is no filter to evaluate for it, and inventing one would be
    reconcile deciding what a user wants archived.
    """
    rows = conn.execute(
        "SELECT account, COUNT(*) FROM emails WHERE trashed_at IS NULL GROUP BY account",
    ).fetchall()
    return sorted(
        ((account or "(unknown)", count) for account, count in rows if account not in by_account),
        key=lambda row: -row[1],
    )


def _group_by_email(rows: list[tuple[str, str, str]]):
    """Collapse (email_id, account, label) rows into one entry per message."""
    current_id = None
    account = None
    labels: list[str] = []
    for email_id, row_account, label in rows:
        if email_id != current_id:
            if current_id is not None:
                yield current_id, account, labels
            current_id, account, labels = email_id, row_account, []
        labels.append(label)
    if current_id is not None:
        yield current_id, account, labels
