"""Email providers package."""

from ownmail.providers.base import EmailProvider
from ownmail.providers.imap import ImapProvider

__all__ = ["EmailProvider", "ImapProvider"]
