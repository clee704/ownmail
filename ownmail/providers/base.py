"""Abstract base class for email providers."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple


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
        """Provider name (e.g., 'gmail', 'imap', 'outlook').

        Used for config keys and display.
        """
        ...

    @property
    @abstractmethod
    def account(self) -> str:
        """Account identifier (email address).

        Used for directory structure and database tracking.
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
    def get_all_message_ids(self) -> List[str]:
        """Get all message IDs from the mailbox.

        Used for initial full sync.

        Returns:
            List of message IDs (provider-specific format)
        """
        ...

    @abstractmethod
    def get_new_message_ids(self, since_state: Optional[str]) -> Tuple[List[str], Optional[str]]:
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
    def download_message(self, msg_id: str) -> Tuple[bytes, List[str]]:
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
    def get_current_sync_state(self) -> Optional[str]:
        """Get current sync state from the provider.

        For incremental sync support. Each provider has its own sync state format:
        - Gmail: historyId
        - IMAP: highest UID per folder + UIDVALIDITY
        - Outlook: deltaLink

        Returns:
            Provider-specific sync state string, or None if not available
        """
        ...
