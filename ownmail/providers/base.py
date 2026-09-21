"""Abstract base class for email providers."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from ownmail.live import LiveLookupError, LiveMessage, LiveSnapshot
from ownmail.thread_protection import ThreadProtection


@dataclass(frozen=True)
class TrashResult:
    """A scoped outcome: trashed, uncertain, or denied; never permanent deletion."""

    source_name: str
    account: str
    message_id: str
    thread_id: str | None = None
    status: str = "uncertain"
    reason: str | None = None


class EmailProvider(ABC):
    """Abstract base class for email providers.

    Each provider (Gmail, IMAP, Outlook, etc.) implements this interface
    to provide a consistent way to:
    - Authenticate with the email service
    - List available messages
    - Download messages with their labels/folders
    - Track sync state for incremental backups
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider type (e.g., 'gmail', 'imap', 'outlook').

        Used for sync state key selection.
        """
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Source name from config (e.g., 'gmail_personal').

        Used for directory structure on disk.
        """
        ...

    @property
    @abstractmethod
    def account(self) -> str:
        """Account identifier (email address).

        Used for database tracking and dedup.
        """
        ...

    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the email service.

        Should handle:
        - Loading stored credentials from keychain
        - Refreshing expired tokens
        - Initiating auth flow if no credentials exist

        Raises:
            Exception: If authentication fails
        """
        ...

    @abstractmethod
    def get_all_message_ids(self) -> list[str]:
        """Get all message IDs from the mailbox.

        Used for initial full sync.

        Returns:
            List of message IDs (provider-specific format)
        """
        ...

    @abstractmethod
    def get_new_message_ids(self, since_state: str | None) -> tuple[list[str], str | None]:
        """Get message IDs added since the given sync state.

        Used for incremental sync.

        Args:
            since_state: Provider-specific sync state (e.g., Gmail history_id).
                        None means full sync required.

        Returns:
            Tuple of (message_ids, new_state):
            - message_ids: List of new message IDs
            - new_state: Updated sync state to save, or None if full sync was performed
        """
        ...

    @abstractmethod
    def download_message(self, msg_id: str) -> tuple[bytes, list[str]]:
        """Download a message.

        Args:
            msg_id: Message ID to download

        Returns:
            Tuple of (raw_email_bytes, labels):
            - raw_email_bytes: Raw RFC 2822 email content
            - labels: List of labels/folders (provider-specific)

        Raises:
            Exception: If download fails
        """
        ...

    @abstractmethod
    def get_current_sync_state(self) -> str | None:
        """Get current sync state from the provider.

        For incremental sync support. Each provider has its own sync state format:
        - Gmail: historyId
        - IMAP: highest UID per folder + UIDVALIDITY
        - Outlook: deltaLink

        Returns:
            Provider-specific sync state string, or None if not available
        """
        ...

    def list_live_messages(self, *, on_progress: Callable[[int], None] | None = None) -> LiveSnapshot | None:
        """Return current observations, reporting cumulative metadata checks.

        Counts include failed and cross-folder checks, and restart at zero per scan.
        Return None when live enumeration is unsupported.
        """
        return None

    def read_live_message(self, message_id: str) -> LiveMessage | None:
        """Read current state and content; None means confirmed absence."""
        raise LiveLookupError("Provider does not support live message lookup")

    def verify_cleanup_account(self) -> None:
        """Require a provider to establish the authenticated cleanup account."""
        raise LiveLookupError("Provider cannot verify an account for server cleanup")

    def trash_message(self, message_id: str, thread_id: str) -> TrashResult:
        """Deny mutation unless the provider has a verified Trash operation."""
        return TrashResult(
            self.source_name,
            self.account,
            message_id,
            thread_id,
            status="denied",
            reason="Provider does not support server cleanup",
        )

    def check_thread_protection(self, message_id: str) -> ThreadProtection:
        """Hold cleanup when complete current thread state is unavailable.

        Capture filters and header matches cannot establish that a server
        thread is inactive. Providers override this only with fresh evidence.
        """
        return ThreadProtection(
            source_name=self.source_name,
            account=self.account,
            message_id=message_id,
            reason="Provider cannot establish complete thread state",
        )
