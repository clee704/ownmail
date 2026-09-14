"""Email archive orchestrator.

This module coordinates between providers, database, and filesystem
to backup, index, and search emails.
"""

import email
import hashlib
import os
import signal
import sqlite3
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parseaddr
from email.utils import parsedate_to_datetime as _parsedate_to_datetime
from pathlib import Path
from typing import Any

from ownmail import roles, sidecar
from ownmail.config import get_db_dir
from ownmail.database import ArchiveDatabase
from ownmail.download_progress import DownloadProgress
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
        config: dict[str, Any] = None,
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
        self._batch_conn: sqlite3.Connection | None = None

    def get_emails_dir(self, source_name: str) -> Path:
        """Get emails directory for a source.

        Args:
            source_name: Source name from config.

        Returns:
            Path to emails directory
        """
        return self.archive_dir / "sources" / source_name

    def _local_label_metadata(self, email_id: str) -> tuple[Path, dict]:
        """Read owned metadata without replacing an unreadable sidecar."""
        row = self.db.get_email_by_id(email_id)
        if not row or not isinstance(row[1], str):
            raise FileNotFoundError("Archived message file is unavailable.")
        filepath = self.archive_dir / row[1]
        try:
            resolved = filepath.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise FileNotFoundError("Archived message file is unavailable.") from error
        archive_root = self.archive_dir.resolve()
        if (
            not resolved.is_relative_to(archive_root)
            or not resolved.is_file()
            or not filepath.parent.resolve().is_relative_to(archive_root)
        ):
            raise FileNotFoundError("Archived message file is unavailable.")

        # Scan and rebuild associate metadata with the tracked path, including aliases.
        metadata_path = sidecar.sidecar_path(filepath)
        try:
            metadata_stat = metadata_path.lstat()
        except FileNotFoundError:
            metadata = {"version": sidecar.SIDECAR_VERSION, "labels": self.db.get_labels_for_email(email_id)}
        else:
            if not stat.S_ISREG(metadata_stat.st_mode):
                raise ValueError("Label metadata must be a regular file in the archive.")
            metadata = sidecar.read_metadata(filepath)
            if metadata is None or not isinstance(metadata.get("labels"), list):
                raise ValueError("Label metadata is unreadable or malformed.")
        if any(not isinstance(label, str) or not label.strip() for label in metadata["labels"]):
            raise ValueError("Label metadata is unreadable or malformed.")
        return filepath, metadata

    def get_local_labels(self, email_id: str) -> list[str]:
        """Return an owned message's exact labels, preferring its sidecar."""
        _filepath, metadata = self._local_label_metadata(email_id)
        return list(dict.fromkeys(metadata["labels"]))

    def set_local_labels(self, email_id: str, labels: list[str]) -> bool:
        """Save owned labels; return False if their index needs rebuilding."""
        if not isinstance(labels, list) or any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError("Labels must be a list of nonblank strings.")
        if any(label in roles.EPHEMERAL_LABELS for label in labels):
            raise ValueError("The label 'UNREAD' is not supported.")

        filepath, metadata = self._local_label_metadata(email_id)
        metadata["labels"] = list(dict.fromkeys(labels))
        sidecar.write_metadata(filepath, metadata)
        try:
            self.db.set_labels_for_email(email_id, metadata["labels"])
        except sqlite3.Error:
            return False
        return True

    @property
    def trash_dir(self) -> Path:
        """Get the trash directory path."""
        return self.archive_dir / "trash"

    # -------------------------------------------------------------------------
    # Trash operations
    # -------------------------------------------------------------------------

    def trash_email(self, email_id: str) -> bool:
        """Move an email to trash.

        Moves the .eml file to trash/ and updates the database.

        Returns:
            True if successful, False if email not found
        """
        # Build trash filename from email_id
        trash_filename = f"trash/{email_id}.eml"
        original_filename = self.db.trash_email(email_id, trash_filename)
        if not original_filename:
            return False

        # Move file (and its label sidecar, if any - they travel together)
        src = self.archive_dir / original_filename
        dst = self.archive_dir / trash_filename
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            src.rename(dst)
        src_sidecar = sidecar.sidecar_path(src)
        if src_sidecar.exists():
            src_sidecar.rename(sidecar.sidecar_path(dst))
        return True

    def restore_email(self, email_id: str) -> bool:
        """Restore an email from trash.

        Moves the .eml file back to its original location.

        Returns:
            True if successful, False if email not found/not trashed
        """
        result = self.db.restore_email(email_id)
        if not result:
            return False

        current_filename, original_filename = result
        src = self.archive_dir / current_filename
        dst = self.archive_dir / original_filename
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            src.rename(dst)
        src_sidecar = sidecar.sidecar_path(src)
        if src_sidecar.exists():
            src_sidecar.rename(sidecar.sidecar_path(dst))
        return True

    def permanently_delete_emails(self, email_ids: list[str]) -> int:
        """Permanently delete emails (files + DB records).

        Returns:
            Number of emails deleted
        """
        # Delete files first (and their label sidecars, if any)
        for eid in email_ids:
            info = self.db.get_email_by_id(eid)
            if info:
                filepath = self.archive_dir / info[1]  # filename
                if filepath.exists():
                    filepath.unlink()
                sidecar_file = sidecar.sidecar_path(filepath)
                if sidecar_file.exists():
                    sidecar_file.unlink()

        return self.db.permanently_delete_emails(email_ids)

    def empty_trash(self, expired_only: bool = False, days: int = 30) -> int:
        """Empty the trash.

        Args:
            expired_only: If True, only delete emails trashed > N days ago
            days: Expiry threshold (default 30)

        Returns:
            Number of emails deleted
        """
        if expired_only:
            rows = self.db.get_expired_trash(days=days)
        else:
            rows = self.db.get_trashed_emails(limit=100000, offset=0)

        if not rows:
            return 0

        email_ids = [row[0] for row in rows]
        # Delete files (and their label sidecars, if any)
        for row in rows:
            filename = row[1]
            filepath = self.archive_dir / filename
            if filepath.exists():
                filepath.unlink()
            sidecar_file = sidecar.sidecar_path(filepath)
            if sidecar_file.exists():
                sidecar_file.unlink()

        count = self.db.permanently_delete_emails(email_ids)

        # Clean up empty trash directory
        if self.trash_dir.exists() and not any(self.trash_dir.iterdir()):
            self.trash_dir.rmdir()

        return count

    def auto_expire_trash(self, days: int = 30) -> int:
        """Delete emails that have been in trash longer than N days.

        Returns:
            Number of emails expired
        """
        return self.empty_trash(expired_only=True, days=days)

    # -------------------------------------------------------------------------
    # Backup
    # -------------------------------------------------------------------------

    def backup(
        self,
        provider: EmailProvider,
        since: str | None = None,
        until: str | None = None,
        verbose: bool = False,
        progress: DownloadProgress | None = None,
    ) -> dict:
        """Backup emails from a provider.

        Args:
            provider: Authenticated email provider
            since: Only backup emails after this date (YYYY-MM-DD)
            until: Only backup emails before this date (YYYY-MM-DD)
            verbose: Show detailed progress output
            progress: Optional reporter for web download status

        Returns:
            Dictionary with success_count, error_count, interrupted
        """
        account = provider.account
        if progress:
            progress.set_phase("checking", provider.source_name)
        emails_dir = self.get_emails_dir(provider.source_name)
        emails_dir.mkdir(parents=True, exist_ok=True)

        # Get downloaded IDs for this account
        if verbose:
            print("[verbose] Loading downloaded IDs from database...", flush=True)
        downloaded_ids = self.db.get_downloaded_ids(account)
        # Also load content hashes for content-based dedup
        # (handles provider_id format changes, e.g. INBOX:uid → [Gmail]/All Mail:uid)
        downloaded_hashes = self.db.get_downloaded_content_hashes(account)
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
            if progress:
                progress.fail("interrupted")
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
        # Use download_batch_size property (int) as the signal — avoids
        # false positives from MagicMock which creates attributes on access.
        batch_size = getattr(provider, "download_batch_size", None)
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 1
        has_batch = batch_size > 1 and hasattr(provider, "download_messages_batch")

        # Track failed message IDs for reporting
        failed_ids: list[str] = []

        if progress:
            progress.set_phase("downloading")
        try:
            i = 0
            while i < len(new_ids) and not interrupted:
                # Get batch of IDs to download
                batch_ids = new_ids[i : i + batch_size]

                # Show progress
                if success_count > 0 and last_rate > 0:
                    print(
                        f"\r\033[K  [{i + 1}/{len(new_ids)}] {last_rate:.1f}/s | ETA {last_eta_str:>5} | downloading batch...",
                        end="",
                        flush=True,
                    )
                else:
                    print(f"\r\033[K  [{i + 1}/{len(new_ids)}] downloading...", end="", flush=True)

                # Download batch with error handling
                batch_results = {}
                batch_errors = {}
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
                        if progress:
                            progress.fail_exception(e, errors=len(batch_ids))
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
                            batch_errors[msg_id] = e

                # Process batch results
                for j, msg_id in enumerate(batch_ids):
                    if interrupted:
                        break

                    current_idx = i + j + 1
                    result = batch_results.get(msg_id)

                    if result is None or result[0] is None:
                        error_msg = result[2] if result else "Unknown error"
                        # Treat 404 (message deleted/trashed) as a soft skip
                        if "404" in str(error_msg) and "not found" in str(error_msg).lower():
                            print(
                                f"\r\033[K  [{current_idx}/{len(new_ids)}] skipped {msg_id} (deleted from server)",
                                end="",
                                flush=True,
                            )
                            if progress:
                                progress.advance(skipped=1)
                            continue
                        print(f"\n  Error downloading {msg_id}: {error_msg}")
                        if msg_id not in failed_ids:
                            failed_ids.append(msg_id)
                        error_count += 1
                        if progress:
                            if msg_id in batch_errors:
                                progress.fail_exception(batch_errors[msg_id], errors=1)
                            else:
                                progress.fail("download", errors=1)
                        continue

                    raw_data, labels, _ = result

                    # Content-based dedup: skip if we already have this exact email
                    # (handles provider_id format changes across scan methods)
                    content_hash = hashlib.sha256(raw_data).hexdigest()
                    if content_hash in downloaded_hashes:
                        success_count += 1
                        if progress:
                            progress.advance(skipped=1)
                        i_skipped = i + j + 1
                        if success_count > 0:
                            elapsed = time.time() - start_time
                            last_rate = success_count / elapsed if elapsed > 0 else 0
                        print(
                            f"\r\033[K  [{i_skipped}/{len(new_ids)}] {last_rate:.1f}/s | skipped (already downloaded)",
                            end="",
                            flush=True,
                        )
                        continue

                    # Save to file
                    filepath, email_date = self._save_email(raw_data, msg_id, account, emails_dir)

                    if filepath:
                        size_bytes = filepath.stat().st_size
                        size_str = self._format_size(size_bytes)

                        # Compute stable email_id from account + provider_id
                        email_id = ArchiveDatabase.make_email_id(account, msg_id)

                        # Mark as downloaded first (creates the row in emails table)
                        self.db.mark_downloaded(
                            email_id=email_id,
                            provider_id=msg_id,
                            filename=str(filepath.relative_to(self.archive_dir)),
                            content_hash=content_hash,
                            account=account,
                            conn=self._batch_conn,
                            email_date=email_date,
                        )

                        # Index the current capture's labels, even after an interrupted download.
                        sidecar.write_labels(filepath, labels or [])

                        # Index the email (updates the row with parsed metadata + FTS)
                        indexed = self._index_email(email_id, filepath, raw_data, skip_delete=True)

                        # Store labels even when parsing failed.
                        if labels:
                            rowid_row = self._batch_conn.execute(
                                "SELECT rowid, email_date FROM emails WHERE email_id = ?", (email_id,)
                            ).fetchone()
                            if rowid_row:
                                for label in labels:
                                    self._batch_conn.execute(
                                        "INSERT OR IGNORE INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                                        (rowid_row[0], label, rowid_row[1]),
                                    )

                        # Set indexed_hash to mark as indexed
                        self._batch_conn.execute(
                            "UPDATE emails SET indexed_hash = ? WHERE email_id = ?", (content_hash, email_id)
                        )

                        success_count += 1
                        downloaded_hashes.add(content_hash)

                        # Commit periodically
                        if success_count - last_commit_count >= COMMIT_INTERVAL:
                            self._batch_conn.commit()
                            last_commit_count = success_count

                        if progress:
                            if indexed:
                                progress.advance(downloaded=1)
                            else:
                                progress.fail("message_index", errors=1)

                        # Update progress stats
                        elapsed = time.time() - start_time
                        last_rate = success_count / elapsed if elapsed > 0 else 0
                        remaining = len(new_ids) - current_idx
                        eta = remaining / last_rate if last_rate > 0 else 0
                        last_eta_str = self._format_eta(eta, current_idx)

                        print(
                            f"\r\033[K  [{current_idx}/{len(new_ids)}] {last_rate:.1f}/s | ETA {last_eta_str:>5} | {size_str:>7}",
                            end="",
                            flush=True,
                        )
                    else:
                        error_count += 1
                        if progress:
                            progress.fail("storage", errors=1)

                i += len(batch_ids)

        except Exception as error:
            if progress:
                progress.fail_exception(error, context="archive", errors=1)
            raise
        finally:
            self._batch_conn.commit()
            self._batch_conn.close()
            self._batch_conn = None
            signal.signal(signal.SIGINT, original_handler)

        if interrupted and progress:
            progress.fail("interrupted")

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

    # -------------------------------------------------------------------------
    # Import / Scan (externally-sourced .eml files)
    # -------------------------------------------------------------------------

    @staticmethod
    def _local_provider_id(email_msg, raw_data: bytes) -> str:
        """Derive a provider_id for an externally-sourced .eml file.

        Uses the Message-ID header when present, falling back to a content
        hash. The 'local:' prefix keeps these ids from ever colliding with
        gmail/imap provider ids.
        """
        message_id = (email_msg.get("Message-ID") or "").strip()
        if message_id:
            return f"local:{message_id}"
        return f"local:sha256:{hashlib.sha256(raw_data).hexdigest()}"

    @staticmethod
    def _derive_account_from_from_header(email_msg) -> str:
        """Default account for an imported email: the address in its own From header."""
        _, addr = parseaddr(email_msg.get("From", ""))
        return addr.lower() if addr else "unknown"

    @staticmethod
    def _is_already_tracked(conn: sqlite3.Connection, provider_id: str, account: str) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM emails WHERE provider_id = ? AND account = ?",
                (provider_id, account),
            ).fetchone()
            is not None
        )

    def _register_and_index(
        self,
        filepath: Path,
        raw_data: bytes,
        provider_id: str,
        account: str,
        conn: sqlite3.Connection,
    ) -> str:
        """Register a file already at its final archive location and index it.

        Returns:
            "imported" or "duplicate"
        """
        if self._is_already_tracked(conn, provider_id, account):
            return "duplicate"

        content_hash = hashlib.sha256(raw_data).hexdigest()
        email_msg = email.message_from_bytes(raw_data)
        msg_date_utc = self._parse_email_datetime(email_msg)
        email_date = msg_date_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00") if msg_date_utc else None

        email_id = ArchiveDatabase.make_email_id(account, provider_id)

        self.db.mark_downloaded(
            email_id=email_id,
            provider_id=provider_id,
            filename=str(filepath.relative_to(self.archive_dir)),
            content_hash=content_hash,
            account=account,
            conn=conn,
            email_date=email_date,
        )

        parsed = EmailParser.parse_file(content=raw_data)
        self.db.index_email(
            email_id=email_id,
            subject=parsed["subject"],
            sender=parsed["sender"],
            recipients=parsed["recipients"],
            date_str=parsed["date_str"],
            body=parsed["body"],
            attachments=parsed["attachments"],
            labels=sidecar.read_labels(filepath),
            conn=conn,
            skip_delete=True,
            email_date=email_date,
        )
        conn.execute(
            "UPDATE emails SET indexed_hash = ? WHERE email_id = ?",
            (content_hash, email_id),
        )
        return "imported"

    def import_email(
        self,
        filepath: Path,
        account: str | None = None,
        move: bool = False,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        """Import a single external .eml file into the archive.

        Copies (or moves) the file into the standard archive layout, derives
        a provider_id as local:{Message-ID} (falling back to
        local:sha256:{content_hash} when Message-ID is missing), and
        registers + indexes it in the database.

        Args:
            filepath: Path to the source .eml file
            account: Account to associate the email with. Defaults to the
                address in the email's own From header.
            move: Delete the source file after a successful import (default: copy)
            conn: Optional shared connection for batching

        Returns:
            "imported", "duplicate", or "error"
        """
        try:
            raw_data = filepath.read_bytes()
        except OSError as e:
            print(f"\n  Error reading {filepath}: {e}")
            return "error"

        email_msg = email.message_from_bytes(raw_data)
        provider_id = self._local_provider_id(email_msg, raw_data)
        if not account:
            account = self._derive_account_from_from_header(email_msg)

        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db.db_path)

        try:
            if self._is_already_tracked(conn, provider_id, account):
                return "duplicate"

            emails_dir = self.get_emails_dir("local")
            emails_dir.mkdir(parents=True, exist_ok=True)
            dest_filepath, _ = self._save_email(raw_data, provider_id, account, emails_dir)
            if not dest_filepath:
                return "error"

            metadata = sidecar.read_metadata(filepath)
            if metadata is not None:
                sidecar.write_metadata(dest_filepath, metadata)

            result = self._register_and_index(dest_filepath, raw_data, provider_id, account, conn)

            if result == "imported" and move:
                try:
                    filepath.unlink()
                except OSError:
                    pass

            return result
        except Exception as e:
            print(f"\n  Error importing {filepath}: {e}")
            return "error"
        finally:
            if should_close:
                conn.commit()
                conn.close()

    def register_scanned_email(
        self,
        filepath: Path,
        account: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> str:
        """Register an .eml file already sitting in the archive dir, in place.

        No file is moved or copied - the file is indexed where it sits.

        Args:
            filepath: Path to the (already archived) .eml file
            account: Account to associate the email with. Defaults to the
                address in the email's own From header.
            conn: Optional shared connection for batching

        Returns:
            "imported", "duplicate", or "error"
        """
        try:
            raw_data = filepath.read_bytes()
        except OSError as e:
            print(f"\n  Error reading {filepath}: {e}")
            return "error"

        email_msg = email.message_from_bytes(raw_data)
        provider_id = self._local_provider_id(email_msg, raw_data)
        if not account:
            account = self._derive_account_from_from_header(email_msg)

        should_close = conn is None
        if conn is None:
            conn = sqlite3.connect(self.db.db_path)

        try:
            return self._register_and_index(filepath, raw_data, provider_id, account, conn)
        except Exception as e:
            print(f"\n  Error registering {filepath}: {e}")
            return "error"
        finally:
            if should_close:
                conn.commit()
                conn.close()

    @staticmethod
    def _empty_batch_result() -> dict:
        return {"imported_count": 0, "duplicate_count": 0, "error_count": 0, "interrupted": False}

    def _run_batch(self, files: list[Path], process_fn, noun: str, count_label: str) -> dict:
        """Shared progress/Ctrl-C/batch-commit loop for import_path and scan_archive.

        Args:
            files: Files to process, in order
            process_fn: Callable(filepath, conn) -> "imported" | "duplicate" | "error"
            noun: Operation name for the summary header (e.g. "Import", "Scan")
            count_label: Label for the success count line (e.g. "Imported", "Registered")
        """
        result = self._empty_batch_result()
        print("(Press Ctrl-C to stop - progress is saved, you can resume anytime)\n")

        interrupted = False
        start_time = time.time()
        last_commit_count = 0
        COMMIT_INTERVAL = 10

        def signal_handler(signum, frame):
            nonlocal interrupted
            if interrupted:
                print("\n\nForce quit.")
                sys.exit(1)
            interrupted = True
            print("\n\n⏸ Stopping after current email... (Ctrl-C again to force quit)")

        original_handler = signal.signal(signal.SIGINT, signal_handler)

        conn = sqlite3.connect(self.db.db_path)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

        try:
            for i, filepath in enumerate(files, 1):
                if interrupted:
                    break

                print(f"\r\033[K  [{i}/{len(files)}] {filepath.name[:40]}", end="", flush=True)

                status = process_fn(filepath, conn)
                result[f"{status}_count"] += 1

                processed = result["imported_count"] + result["duplicate_count"] + result["error_count"]
                if processed - last_commit_count >= COMMIT_INTERVAL:
                    conn.commit()
                    last_commit_count = processed
        finally:
            conn.commit()
            conn.close()
            signal.signal(signal.SIGINT, original_handler)

        result["interrupted"] = interrupted
        elapsed = time.time() - start_time
        print("\n" + "-" * 50)
        print(f"{noun} {'Paused' if interrupted else 'Complete'}!")
        print(f"  {count_label}: {result['imported_count']} in {elapsed:.1f}s")
        if result["duplicate_count"]:
            print(f"  Skipped (duplicate): {result['duplicate_count']}")
        if result["error_count"]:
            print(f"  Errors: {result['error_count']}")
        if result["interrupted"]:
            print(f"\n  Run 'ownmail {noun.lower()}' again to resume.")
        print("-" * 50 + "\n")

        return result

    def import_path(
        self,
        path: Path,
        account: str | None = None,
        move: bool = False,
        dry_run: bool = False,
    ) -> dict:
        """Import .eml file(s) from an external path into the archive.

        Args:
            path: A single .eml file, or a directory to scan recursively
            account: Associate all imported emails with this account. If not
                given, each email's own From header address is used.
            move: Delete source files after a successful import (default: copy)
            dry_run: List what would be imported without doing it

        Returns:
            Dict with imported_count, duplicate_count, error_count, interrupted
        """
        if path.is_file():
            files = [path] if path.suffix.lower() == ".eml" else []
        else:
            files = sorted(path.rglob("*.eml"))

        if not files:
            print(f"No .eml files found under {path}")
            return self._empty_batch_result()

        print(f"Found {len(files)} .eml file(s)")
        if dry_run:
            for f in files:
                print(f"  would import: {f}")
            return self._empty_batch_result()

        return self._run_batch(
            files,
            lambda filepath, conn: self.import_email(filepath, account=account, move=move, conn=conn),
            noun="Import",
            count_label="Imported",
        )

    def scan_archive(
        self,
        account: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Register .eml files present in the archive dir but untracked by the DB.

        Files are registered in place - nothing is moved or copied.

        Args:
            account: Associate all registered emails with this account. If
                not given, each email's own From header address is used.
            dry_run: List what would be registered without doing it

        Returns:
            Dict with imported_count, duplicate_count, error_count, interrupted
        """
        tracked = self.db.get_tracked_filenames()
        files = [
            f for f in sorted(self.archive_dir.rglob("*.eml")) if str(f.relative_to(self.archive_dir)) not in tracked
        ]

        if not files:
            print("No untracked .eml files found.")
            return self._empty_batch_result()

        print(f"Found {len(files)} untracked .eml file(s)")
        if dry_run:
            for f in files:
                print(f"  would register: {f}")
            return self._empty_batch_result()

        return self._run_batch(
            files,
            lambda filepath, conn: self.register_scanned_email(filepath, account=account, conn=conn),
            noun="Scan",
            count_label="Registered",
        )

    @staticmethod
    def _parse_email_datetime(email_msg) -> datetime | None:
        """Parse an email's date, in UTC, using the same robust logic as
        EmailParser (Korean weekday prefixes, numeric months, Received-header
        fallback, etc.).

        Returns:
            A UTC datetime, or None if the date couldn't be parsed.
        """
        date_str = email_msg.get("Date", "")
        if not date_str:
            date_str = EmailParser._extract_date_from_received(email_msg)
        date_str = EmailParser._normalize_date(date_str)
        try:
            return _parsedate_to_datetime(date_str).astimezone(timezone.utc)
        except Exception:
            return None

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
            email_msg = email.message_from_bytes(raw_data)
            msg_date_utc = self._parse_email_datetime(email_msg)
            email_date_iso = None

            if msg_date_utc:
                date_prefix = msg_date_utc.strftime("%Y%m%d_%H%M%S")
                year_month = msg_date_utc.strftime("%Y/%m")
                email_date_iso = msg_date_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            else:
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
                labels=sidecar.read_labels(filepath),
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

    def search(
        self, query: str, account: str = None, limit: int = 50, offset: int = 0, sort: str = "relevance", tz=None
    ) -> list:
        """Search emails.

        Args:
            query: Search query
            account: Filter to specific account (optional)
            limit: Maximum results
            offset: Number of results to skip (for pagination)
            sort: Sort order - 'relevance', 'date_desc', or 'date_asc'
            tz: Optional ZoneInfo timezone for date filter interpretation

        Returns:
            List of search results
        """
        return self.db.search(query, account=account, limit=limit, offset=offset, sort=sort, tz=tz)

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
            return f"{eta_seconds / 3600:.1f}h"
        elif eta_seconds > 60:
            return f"{eta_seconds / 60:.0f}m"
        else:
            return f"{eta_seconds:.0f}s"
