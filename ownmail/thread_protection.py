"""Read-only observations used to protect live server conversations."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ownmail import roles


@dataclass(frozen=True)
class ThreadProtection:
    """A scoped observation, which must be refreshed before server cleanup.

    ``complete`` requires known membership and known finished or Active state
    for every relevant member. A revision is evidence of the observed state,
    not a guarantee that it remains unchanged after this check.
    """

    source_name: str
    account: str
    message_id: str
    thread_id: str | None = None
    candidate_roles: frozenset[str] = frozenset()
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    revision: str | None = None
    complete: bool = False
    active: bool = False
    reason: str | None = "Thread state is unavailable"

    @property
    def allows_cleanup(self) -> bool:
        """Whether this observation clears message and thread protection."""
        protected_roles = {roles.INBOX, roles.DRAFTS, roles.TRASH, roles.SPAM}
        return self.complete and not self.active and not self.candidate_roles.intersection(protected_roles)
