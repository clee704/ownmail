"""
ownmail - Own your mail.

A file-based email backup and search tool.
"""

__version__ = "0.3.0"

# Re-export main classes for backward compatibility
from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase
from ownmail.keychain import KeychainStorage
from ownmail.parser import EmailParser
from ownmail.providers.gmail import GmailProvider

# Backward compatibility alias (deprecated, use EmailArchive + GmailProvider)
GmailArchive = None  # Will be set below after import


def _create_gmail_archive_compat():
    """Create backward-compatible GmailArchive class."""
    import hashlib
    import sqlite3
    import time
    from pathlib import Path
    from typing import Any, Dict, Optional

    class GmailArchiveCompat:
        """Backward-compatible wrapper for GmailArchive.

        Deprecated: Use EmailArchive + GmailProvider instead.
        """

        def __init__(self, archive_dir: Path, config: Dict[str, Any] = None):
            self.archive_dir = archive_dir
            self.emails_dir = archive_dir / "emails"
            self.keychain = KeychainStorage()
            self.db = ArchiveDatabase(archive_dir)
            self.config = config or {}
            self.include_labels = self.config.get("include_labels", True)
            self._batch_conn: Optional[sqlite3.Connection] = None

        def index_email(
            self,
            email_id: str,
            filepath: Path,
            update_hash: bool = True,
            debug: bool = False,
            skip_delete: bool = False,
        ) -> bool:
            """Index an email for full-text search."""
            try:
                t0 = time.time()
                with open(filepath, "rb") as f:
                    content = f.read()
                t_read = time.time() - t0

                t0 = time.time()
                new_hash = hashlib.sha256(content).hexdigest() if update_hash else None
                t_hash = time.time() - t0

                t0 = time.time()
                parsed = EmailParser.parse_file(content=content)
                t_parse = time.time() - t0

                conn = self._batch_conn

                t0 = time.time()
                self.db.index_email(
                    email_id=email_id,
                    subject=parsed["subject"],
                    sender=parsed["sender"],
                    recipients=parsed["recipients"],
                    date_str=parsed["date_str"],
                    body=parsed["body"],
                    attachments=parsed["attachments"],
                    conn=conn,
                    skip_delete=skip_delete,
                )
                t_fts = time.time() - t0

                t0 = time.time()
                if update_hash and new_hash:
                    if conn:
                        conn.execute(
                            "UPDATE emails SET content_hash = ?, indexed_hash = ? WHERE email_id = ?",
                            (new_hash, new_hash, email_id)
                        )
                    else:
                        import sqlite3 as sql
                        with sql.connect(self.db.db_path) as c:
                            c.execute(
                                "UPDATE emails SET content_hash = ?, indexed_hash = ? WHERE email_id = ?",
                                (new_hash, new_hash, email_id)
                            )
                            c.commit()
                t_update = time.time() - t0

                if debug:
                    total = t_read + t_hash + t_parse + t_fts + t_update
                    print(f"\n    DEBUG: read={t_read*1000:.0f}ms hash={t_hash*1000:.0f}ms "
                          f"parse={t_parse*1000:.0f}ms fts={t_fts*1000:.0f}ms "
                          f"update={t_update*1000:.0f}ms TOTAL={total*1000:.0f}ms")

                return True
            except Exception as e:
                print(f"\n  Error indexing {filepath}: {e}")
                return False

    return GmailArchiveCompat


# Create the compatibility class
GmailArchive = _create_gmail_archive_compat()

__all__ = [
    "EmailArchive",
    "ArchiveDatabase",
    "KeychainStorage",
    "EmailParser",
    "GmailProvider",
    "GmailArchive",  # Deprecated
]
