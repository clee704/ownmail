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

from ownmail.config import get_db_dir
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
        db_dir = get_db_dir(self.config)
        self.db = ArchiveDatabase(archive_dir, db_dir=db_dir)
        self.keychain = KeychainStorage()

        # Batch connection for fast writes
        self._batch_conn: Optional[sqlite3.Connection] = None

    def get_emails_dir(self, account: str) -> Path:
        """Get emails directory for an account.

        Args:
            account: Email address.

        Returns:
            Path to emails directory
        """
        return self.archive_dir / "accounts" / account

    # -------------------------------------------------------------------------
    # Backup
    # -------------------------------------------------------------------------

    def backup(
        self,
        provider: EmailProvider,
        since: Optional[str] = None,
        until: Optional[str] = None,
        verbose: bool = False,
    ) -> dict:
        """Backup emails from a provider.

        Args:
            provider: Authenticated email provider
            since: Only backup emails after this date (YYYY-MM-DD)
            until: Only backup emails before this date (YYYY-MM-DD)
            verbose: Show detailed progress output

        Returns:
            Dictionary with success_count, error_count, interrupted
        """
        account = provider.account
        emails_dir = self.get_emails_dir(account)
        emails_dir.mkdir(parents=True, exist_ok=True)

        # Get downloaded IDs for this account
        if verbose:
            print("[verbose] Loading downloaded IDs from database...", flush=True)
        downloaded_ids = self.db.get_downloaded_ids(account)
        if verbose:
            print(f"[verbose] Found {len(downloaded_ids)} previously downloaded IDs", flush=True)

        # Get sync state (key depends on provider type)
        sync_key = "sync_state" if provider.name == "imap" else "history_id"
        if verbose:
            print("[verbose] Getting sync state...", flush=True)
        sync_state = self.db.get_sync_state(account, sync_key)
        if verbose:
            print(f"[verbose] Sync state: {sync_state}", flush=True)

        # Get new message IDs (with optional date filter)
        print("Checking for new emails...", flush=True)
        if verbose:
            print("[verbose] Calling provider.get_new_message_ids()...", flush=True)
        try:
            new_ids, new_state = provider.get_new_message_ids(sync_state, since=since, until=until)
        except KeyboardInterrupt:
            print("\nBackup cancelled.")
            return {"success_count": 0, "error_count": 0, "interrupted": True, "failed_ids": []}
        if verbose:
            print(f"[verbose] Provider returned {len(new_ids)} message IDs", flush=True)

        # Filter out already downloaded
        new_ids = [mid for mid in new_ids if mid not in downloaded_ids]

        if not new_ids:
            print("\n✓ No new emails to download. Archive is up to date!")
            # Only update sync state if NOT using date filters (full sync)
            # Date-filtered runs are partial syncs, don't update history_id
            if not since and not until:
                if new_state:
                    self.db.set_sync_state(account, sync_key, new_state)
                elif sync_state is None:
                    # After full sync, get current state
                    current_state = provider.get_current_sync_state()
                    if current_state:
                        self.db.set_sync_state(account, sync_key, current_state)
            return {"success_count": 0, "error_count": 0, "interrupted": False, "failed_ids": []}

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
        from ownmail.providers.gmail import BATCH_SIZE, GmailProvider
        has_batch = isinstance(provider, GmailProvider)
        batch_size = BATCH_SIZE if has_batch else 1

        # Track failed message IDs for reporting
        failed_ids: list[str] = []

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

                # Download batch with error handling
                batch_results = {}
                if has_batch and len(batch_ids) > 1:
                    try:
                        batch_results = provider.download_messages_batch(batch_ids)
                    except Exception as e:
                        # Entire batch failed - mark all IDs as failed and continue
                        error_msg = str(e)
                        print(f"\n  Batch download failed: {error_msg}")
                        for msg_id in batch_ids:
                            batch_results[msg_id] = (None, [], error_msg)
                            failed_ids.append(msg_id)
                        error_count += len(batch_ids)
                        i += len(batch_ids)
                        continue
                else:
                    # Fallback to sequential for single items or non-batch providers
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
                        if msg_id not in failed_ids:
                            failed_ids.append(msg_id)
                        error_count += 1
                        continue

                    raw_data, labels, _ = result

                    # Save to file
                    filepath, email_date = self._save_email(
                        raw_data, msg_id, account, emails_dir
                    )

                    if filepath:
                        size_bytes = filepath.stat().st_size
                        size_str = self._format_size(size_bytes)

                        # Compute stable email_id from account + provider_id
                        email_id = ArchiveDatabase.make_email_id(account, msg_id)

                        # Mark as downloaded first (creates the row in emails table)
                        content_hash = hashlib.sha256(raw_data).hexdigest()
                        self.db.mark_downloaded(
                            email_id=email_id,
                            provider_id=msg_id,
                            filename=str(filepath.relative_to(self.archive_dir)),
                            content_hash=content_hash,
                            account=account,
                            conn=self._batch_conn,
                            email_date=email_date,
                        )

                        # Index the email (updates the row with parsed metadata + FTS)
                        self._index_email(email_id, filepath, raw_data,
                                          skip_delete=True)

                        # Store labels in email_labels table
                        if labels:
                            rowid_row = self._batch_conn.execute(
                                "SELECT rowid, email_date FROM emails WHERE email_id = ?",
                                (email_id,)
                            ).fetchone()
                            if rowid_row:
                                for label in labels:
                                    self._batch_conn.execute(
                                        "INSERT OR IGNORE INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                                        (rowid_row[0], label, rowid_row[1])
                                    )

                        # Set indexed_hash to mark as indexed
                        self._batch_conn.execute(
                            "UPDATE emails SET indexed_hash = ? WHERE email_id = ?",
                            (content_hash, email_id)
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

        # Update sync state only when ALL conditions are met:
        # 1. Not interrupted
        # 2. No date filters (full sync)
        # 3. No errors (all messages downloaded successfully)
        # This ensures history_id marks a complete sync point
        if not interrupted and not since and not until and error_count == 0:
            if new_state:
                self.db.set_sync_state(account, sync_key, new_state)
            else:
                current_state = provider.get_current_sync_state()
                if current_state:
                    self.db.set_sync_state(account, sync_key, current_state)

        return {
            "success_count": success_count,
            "error_count": error_count,
            "interrupted": interrupted,
            "failed_ids": failed_ids,
        }

    def _save_email(
        self,
        raw_data: bytes,
        msg_id: str,
        account: str,
        emails_dir: Path,
    ) -> tuple:
        """Save email to filesystem atomically.

        Returns:
            Tuple of (filepath, email_date_iso) or (None, None) on error
        """
        try:
            # Parse date for directory structure
            email_msg = email.message_from_bytes(raw_data)
            date_str = email_msg.get("Date", "")
            email_date_iso = None

            try:
                msg_date = parsedate_to_datetime(date_str)
                date_prefix = msg_date.strftime("%Y%m%d_%H%M%S")
                year_month = msg_date.strftime("%Y/%m")
                email_date_iso = msg_date.isoformat()
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

            return filepath, email_date_iso

        except Exception as e:
            print(f"\n  Error saving {msg_id}: {e}")
            return None, None

    def _index_email(
        self,
        email_id: str,
        filepath: Path,
        content: bytes = None,
        skip_delete: bool = False,
    ) -> bool:
        """Index an email for full-text search.

        Args:
            email_id: 24-char hex hash
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

            return True

        except Exception as e:
            print(f"\n  Error indexing {filepath}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def search(self, query: str, account: str = None, limit: int = 50, offset: int = 0, sort: str = "relevance") -> List:
        """Search emails.

        Args:
            query: Search query
            account: Filter to specific account (optional)
            limit: Maximum results
            offset: Number of results to skip (for pagination)
            sort: Sort order - 'relevance', 'date_desc', or 'date_asc'

        Returns:
            List of search results
        """
        return self.db.search(query, account=account, limit=limit, offset=offset, sort=sort)

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
