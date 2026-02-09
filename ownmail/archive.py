"""Email archive orchestrator.

This module coordinates between providers, database, and filesystem
to backup, index, and search emails.
"""

import email
import hashlib
import os
import signal
import sqlite3
import sys
import tempfile
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ownmail.database import ArchiveDatabase
from ownmail.keychain import KeychainStorage
from ownmail.parser import EmailParser
from ownmail.providers.base import EmailProvider


class EmailArchive:
    """Orchestrates email backup, indexing, and search.

    This class handles:
    - Coordinating between email providers and local storage
    - File operations (atomic writes, directory structure)
    - Search and indexing via the database
    - Progress display and resumable operations
    """

    def __init__(
        self,
        archive_dir: Path,
        config: Dict[str, Any] = None,
    ):
        """Initialize the email archive.

        Args:
            archive_dir: Root directory for the archive
            config: Configuration dictionary
        """
        self.archive_dir = archive_dir
        self.config = config or {}
        self.db = ArchiveDatabase(archive_dir)
        self.keychain = KeychainStorage()

        # Batch connection for fast writes
        self._batch_conn: Optional[sqlite3.Connection] = None

    def get_emails_dir(self, account: str = None) -> Path:
        """Get emails directory for an account.

        Args:
            account: Email address. If None, returns legacy single-account path.

        Returns:
            Path to emails directory
        """
        if account:
            return self.archive_dir / "accounts" / account / "emails"
        else:
            # Legacy single-account structure
            return self.archive_dir / "emails"

    # -------------------------------------------------------------------------
    # Backup
    # -------------------------------------------------------------------------

    def backup(
        self,
        provider: EmailProvider,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> dict:
        """Backup emails from a provider.

        Args:
            provider: Authenticated email provider
            since: Only backup emails after this date (YYYY-MM-DD)
            until: Only backup emails before this date (YYYY-MM-DD)

        Returns:
            Dictionary with success_count, error_count, interrupted
        """
        account = provider.account
        emails_dir = self.get_emails_dir(account)
        emails_dir.mkdir(parents=True, exist_ok=True)

        # Get downloaded IDs for this account
        downloaded_ids = self.db.get_downloaded_ids(account)

        # Get sync state
        sync_state = self.db.get_sync_state(account, "history_id")

        # Get new message IDs (with optional date filter)
        print("Checking for new emails...")
        new_ids, new_state = provider.get_new_message_ids(sync_state, since=since, until=until)

        # Filter out already downloaded
        new_ids = [mid for mid in new_ids if mid not in downloaded_ids]

        if not new_ids:
            print("\n✓ No new emails to download. Archive is up to date!")
            # Update sync state even if nothing new
            if new_state:
                self.db.set_sync_state(account, "history_id", new_state)
            elif sync_state is None:
                # After full sync, get current state
                current_state = provider.get_current_sync_state()
                if current_state:
                    self.db.set_sync_state(account, "history_id", current_state)
            return {"success_count": 0, "error_count": 0, "interrupted": False}

        print(f"\nFound {len(new_ids)} new emails to download")
        print("(Press Ctrl-C to stop - progress is saved, you can resume anytime)\n")

        success_count = 0
        error_count = 0
        interrupted = False
        start_time = time.time()
        last_commit_count = 0
        COMMIT_INTERVAL = 10

        # Handle Ctrl-C gracefully
        def signal_handler(signum, frame):
            nonlocal interrupted
            if interrupted:
                print("\n\nForce quit.")
                sys.exit(1)
            interrupted = True
            print("\n\n⏸ Stopping after current email... (Ctrl-C again to force quit)")

        original_handler = signal.signal(signal.SIGINT, signal_handler)

        # Use shared connection for batching
        self._batch_conn = sqlite3.connect(self.db.db_path)
        self._batch_conn.execute("PRAGMA journal_mode = WAL")
        self._batch_conn.execute("PRAGMA synchronous = NORMAL")

        last_rate = 0.0
        last_eta_str = "..."

        # Check if provider supports batch downloads
        from ownmail.providers.gmail import GmailProvider
        has_batch = isinstance(provider, GmailProvider)
        batch_size = 50 if has_batch else 1

        try:
            i = 0
            while i < len(new_ids) and not interrupted:
                # Get batch of IDs to download
                batch_ids = new_ids[i:i + batch_size]

                # Show progress
                if success_count > 0 and last_rate > 0:
                    print(f"\r\033[K  [{i + 1}/{len(new_ids)}] {last_rate:.1f}/s | ETA {last_eta_str:>5} | downloading batch...", end="", flush=True)
                else:
                    print(f"\r\033[K  [{i + 1}/{len(new_ids)}] downloading...", end="", flush=True)

                # Download batch
                if has_batch and len(batch_ids) > 1:
                    batch_results = provider.download_messages_batch(batch_ids)
                else:
                    # Fallback to sequential for single items or non-batch providers
                    batch_results = {}
                    for msg_id in batch_ids:
                        try:
                            raw_data, labels = provider.download_message(msg_id)
                            batch_results[msg_id] = (raw_data, labels, None)
                        except Exception as e:
                            batch_results[msg_id] = (None, [], str(e))

                # Process batch results
                for j, msg_id in enumerate(batch_ids):
                    if interrupted:
                        break

                    current_idx = i + j + 1
                    result = batch_results.get(msg_id)

                    if result is None or result[0] is None:
                        error_msg = result[2] if result else "Unknown error"
                        print(f"\n  Error downloading {msg_id}: {error_msg}")
                        error_count += 1
                        continue

                    raw_data, labels, _ = result

                    # Save to file
                    filepath = self._save_email(
                        raw_data, msg_id, account, emails_dir
                    )

                    if filepath:
                        size_bytes = filepath.stat().st_size
                        size_str = self._format_size(size_bytes)

                        # Index the email
                        self._index_email(msg_id, filepath, raw_data, skip_delete=True)

                        # Mark as downloaded
                        content_hash = hashlib.sha256(raw_data).hexdigest()
                        self.db.mark_downloaded(
                            message_id=msg_id,
                            filename=str(filepath.relative_to(self.archive_dir)),
                            content_hash=content_hash,
                            account=account,
                            conn=self._batch_conn,
                        )

                        success_count += 1

                        # Commit periodically
                        if success_count - last_commit_count >= COMMIT_INTERVAL:
                            self._batch_conn.commit()
                            last_commit_count = success_count

                        # Update progress stats
                        elapsed = time.time() - start_time
                        last_rate = success_count / elapsed if elapsed > 0 else 0
                        remaining = len(new_ids) - current_idx
                        eta = remaining / last_rate if last_rate > 0 else 0
                        last_eta_str = self._format_eta(eta, current_idx)

                        print(f"\r\033[K  [{current_idx}/{len(new_ids)}] {last_rate:.1f}/s | ETA {last_eta_str:>5} | {size_str:>7}", end="", flush=True)
                    else:
                        error_count += 1

                i += len(batch_ids)

        finally:
            self._batch_conn.commit()
            self._batch_conn.close()
            self._batch_conn = None
            signal.signal(signal.SIGINT, original_handler)

        # Update sync state if completed
        if not interrupted:
            if new_state:
                self.db.set_sync_state(account, "history_id", new_state)
            else:
                current_state = provider.get_current_sync_state()
                if current_state:
                    self.db.set_sync_state(account, "history_id", current_state)

        return {
            "success_count": success_count,
            "error_count": error_count,
            "interrupted": interrupted,
        }

    def _save_email(
        self,
        raw_data: bytes,
        msg_id: str,
        account: str,
        emails_dir: Path,
    ) -> Optional[Path]:
        """Save email to filesystem atomically.

        Returns:
            Path to saved file, or None on error
        """
        try:
            # Parse date for directory structure
            email_msg = email.message_from_bytes(raw_data)
            date_str = email_msg.get("Date", "")

            try:
                msg_date = parsedate_to_datetime(date_str)
                date_prefix = msg_date.strftime("%Y%m%d_%H%M%S")
                year_month = msg_date.strftime("%Y/%m")
            except Exception:
                date_prefix = "unknown"
                year_month = "unknown"

            msg_dir = emails_dir / year_month
            msg_dir.mkdir(parents=True, exist_ok=True)

            # Create filename from date + hash of message ID
            safe_id = hashlib.sha256(msg_id.encode()).hexdigest()[:12]
            filename = f"{date_prefix}_{safe_id}.eml"
            filepath = msg_dir / filename

            # Atomic write
            fd, temp_path = tempfile.mkstemp(dir=msg_dir, suffix=".tmp")
            try:
                os.write(fd, raw_data)
                os.close(fd)
                os.rename(temp_path, filepath)
            except Exception:
                os.close(fd)
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

            return filepath

        except Exception as e:
            print(f"\n  Error saving {msg_id}: {e}")
            return None

    def _index_email(
        self,
        message_id: str,
        filepath: Path,
        content: bytes = None,
        skip_delete: bool = False,
    ) -> bool:
        """Index an email for full-text search.

        Args:
            message_id: Message ID
            filepath: Path to .eml file
            content: Raw email bytes (avoids re-reading file)
            skip_delete: Skip DELETE before INSERT (for new emails)

        Returns:
            True if successful
        """
        try:
            # Parse email
            if content:
                parsed = EmailParser.parse_file(content=content)
            else:
                parsed = EmailParser.parse_file(filepath=filepath)

            # Use batch connection if available
            conn = self._batch_conn

            self.db.index_email(
                message_id=message_id,
                subject=parsed["subject"],
                sender=parsed["sender"],
                recipients=parsed["recipients"],
                date_str=parsed["date_str"],
                body=parsed["body"],
                attachments=parsed["attachments"],
                conn=conn,
                skip_delete=skip_delete,
            )

            return True

        except Exception as e:
            print(f"\n  Error indexing {filepath}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def search(self, query: str, account: str = None, limit: int = 50) -> List:
        """Search emails.

        Args:
            query: Search query
            account: Filter to specific account (optional)
            limit: Maximum results

        Returns:
            List of search results
        """
        return self.db.search(query, account=account, limit=limit)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes > 1_000_000:
            return f"{size_bytes / 1_000_000:.1f}MB"
        elif size_bytes > 1_000:
            return f"{size_bytes / 1_000:.0f}KB"
        else:
            return f"{size_bytes}B"

    @staticmethod
    def _format_eta(eta_seconds: float, iteration: int) -> str:
        """Format ETA for display."""
        if iteration < 3:
            return "..."
        elif eta_seconds > 3600:
            return f"{eta_seconds/3600:.1f}h"
        elif eta_seconds > 60:
            return f"{eta_seconds/60:.0f}m"
        else:
            return f"{eta_seconds:.0f}s"
