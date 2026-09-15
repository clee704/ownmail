"""Read-only observations of mail that remains under server authority."""

from dataclasses import dataclass, field

from ownmail import roles


class LiveLookupError(RuntimeError):
    """Current state could not be established; retain any cached copy."""


@dataclass(frozen=True)
class LiveMessage:
    """One current remote copy; identity is scoped by source and account.

    Unknown finished state remains live and must never authorize capture.
    Labels describe the configured saved snapshot; roles always describe the
    fresh server state, including when label saving is disabled.
    """

    message_id: str
    labels: tuple[str, ...] = ()
    roles: frozenset[str] = frozenset()
    state: str = "unknown"
    identity_token: str = ""
    thread_id: str | None = None
    raw: bytes | None = None
    reason: str | None = None
    download_allowed: bool = True


@dataclass(frozen=True)
class LiveSnapshot:
    """A mailbox enumeration, with partial results explicitly marked."""

    source_name: str
    account: str
    messages: list[LiveMessage] = field(default_factory=list)
    complete: bool = False
    reason: str | None = None


def message_state(current_roles: frozenset[str], *, finished: bool, uncertain: bool = False) -> str:
    """Apply ownership precedence without consulting download preferences."""
    if current_roles.intersection({roles.TRASH, roles.SPAM}):
        return "discarded"
    if current_roles.intersection({roles.INBOX, roles.DRAFTS}):
        return "active"
    return "eligible" if finished and not uncertain else "unknown"
