"""Maintenance commands for ownmail.

This module contains commands for archive maintenance:
- rebuild: Rebuild the search index and populate metadata
- verify: Verify archive integrity (files, hashes, database)
- sync_check: Compare local archive with server
- update_labels: Update labels from server or derive from IMAP folders
- relabel: Re-derive IMAP folder membership for already-archived messages
- reconcile: Move archived mail the current download filter would now reject
"""

import hashlib
import signal
import sqlite3
import sys
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from ownmail import reconcile, roles, sidecar
from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase, set_db_labels
from ownmail.parser import EmailParser


def cmd_rebuild(
    archive: EmailArchive,
    file_path: Path | None = None,
    pattern: str | None = None,
    force: bool = False,
    debug: bool = False,
    only: str | None = None,
) -> None:
    """Rebuild the search index and populate metadata.

    By default, only indexes emails that have changed (content_hash != indexed_hash).
    This makes rebuild resumable - if cancelled, just run again to continue.

    Args:
        archive: EmailArchive instance
        file_path: Index only this specific file
        pattern: Index only files matching this glob pattern (e.g., "2024/09/*")
        force: If True, rebuild all emails regardless of indexed_hash
        debug: If True, show timing info for each email
        only: If 'dates', only populate email_date; if 'index', only rebuild index;
            if 'sidecars', reconcile label sidecar files with the DB (sidecar wins)
    """
    # Dates-only mode: fast path that skips full reindexing
    if only == "dates":
        _populate_dates_only(archive, pattern, force, debug)
        return

    # Sidecars-only mode: reconcile label sidecar files with the DB, without
    # touching FTS/body content
    if only == "sidecars":
        _reconcile_label_sidecars(archive, pattern, debug)
        return

    print("\n" + "=" * 50)
    print("ownmail - Rebuild")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    # Single file mode
    if file_path:
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return

        # Find email_id for this file
        rel_path = None
        try:
            rel_path = file_path.relative_to(archive.archive_dir)
        except ValueError:
            # file_path might be absolute from different base
            pass

        if rel_path:
            with sqlite3.connect(db_path) as conn:
                result = conn.execute("SELECT email_id FROM emails WHERE filename = ?", (str(rel_path),)).fetchone()
                if result:
                    email_id = result[0]
                    print(f"Indexing: {file_path.name}")
                    if _index_single_email(archive, email_id, file_path, debug):
                        print("✓ Indexed successfully")
                    else:
                        print("✗ Failed to index")
                    return

        # If not in DB, use filename as email_id
        print(f"Indexing: {file_path.name}")
        if _index_single_email(archive, file_path.stem, file_path, debug):
            print("✓ Indexed successfully")
        else:
            print("✗ Failed to index")
        return

    # Build the pattern for matching
    like_pattern = None
    if pattern:
        like_pattern = "%" + pattern.replace("*", "%").replace("?", "_") + "%"

    # Get emails to index
    t0 = time.time()
    print("Finding emails to index...", end="", flush=True)
    with sqlite3.connect(db_path) as conn:
        if like_pattern:
            if force:
                # Force mode: select ALL matching emails regardless of indexed state
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                       FROM emails
                       WHERE filename LIKE ?""",
                    (like_pattern,),
                ).fetchall()
                print(f" {len(emails)} matching '{pattern}' (force) ({time.time() - t0:.1f}s)")
            else:
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                       FROM emails
                       WHERE filename LIKE ?
                       AND (indexed_hash IS NULL OR content_hash IS NULL OR indexed_hash != content_hash)""",
                    (like_pattern,),
                ).fetchall()
                total_matching = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE filename LIKE ?", (like_pattern,)
                ).fetchone()[0]
                print(f" {len(emails)} of {total_matching} matching '{pattern}' ({time.time() - t0:.1f}s)")
        else:
            if force:
                # Force mode: select ALL emails
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                       FROM emails"""
                ).fetchall()
                print(f" {len(emails)} emails (force) ({time.time() - t0:.1f}s)")
            else:
                emails = conn.execute(
                    """SELECT email_id, filename, content_hash, indexed_hash
                   FROM emails
                   WHERE indexed_hash IS NULL OR content_hash IS NULL OR indexed_hash != content_hash"""
                ).fetchall()
            total_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
            already_indexed = total_emails - len(emails)
            print(f" {len(emails)} emails ({time.time() - t0:.1f}s)")
            if already_indexed > 0:
                print(f"  (skipping {already_indexed} already-indexed)")

    if not emails:
        print("\nAll emails are already indexed. Use --force to rebuild everything.")
        return

    # For full rebuild with force mode, rebuild FTS table from scratch
    # This is necessary because contentless FTS5 can't delete without original content
    if force and not pattern and not file_path:
        print("Rebuilding FTS index...", end="", flush=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS emails_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE emails_fts USING fts5(
                    subject,
                    sender,
                    recipients,
                    body,
                    attachments,
                    content='',
                    tokenize='porter unicode61'
                )
            """)
            # Also clear indexed_hash so all emails get reindexed
            conn.execute("UPDATE emails SET indexed_hash = NULL, subject = NULL")
            conn.commit()
        print(" done")

    print(f"\nIndexing {len(emails)} emails...")
    print("(Press Ctrl-C to pause - progress is saved, run again to resume)\n")

    success_count = 0
    error_count = 0
    interrupted = False
    start_time = time.time()
    last_commit_count = 0
    COMMIT_INTERVAL = 50  # Commit every N emails

    def signal_handler(signum, frame):
        nonlocal interrupted
        interrupted = True
        print("\n\n⏸ Stopping after current email...")

    original_handler = signal.signal(signal.SIGINT, signal_handler)

    # Use a shared connection for batching (much faster on slow disks)
    batch_conn = sqlite3.connect(db_path)
    # WAL mode is faster for writes and crash-safe
    batch_conn.execute("PRAGMA journal_mode = WAL")
    batch_conn.execute("PRAGMA synchronous = NORMAL")

    try:
        for i, (msg_id, filename, _content_hash, _indexed_hash) in enumerate(emails, 1):
            if interrupted:
                break

            filepath = archive.archive_dir / filename
            short_name = Path(filename).name[:40]

            # Show what we're working on
            print(f"\r\033[K  [{i}/{len(emails)}] {short_name}", end="", flush=True)

            if not filepath.exists():
                print(f"\n  Missing file: {filename}")
                error_count += 1
                continue

            # Index the email (updates emails table, FTS synced via triggers)
            if _index_email_for_rebuild(archive, msg_id, filepath, batch_conn, debug):
                success_count += 1
            else:
                error_count += 1

            # Commit periodically to save progress
            if success_count - last_commit_count >= COMMIT_INTERVAL:
                batch_conn.commit()
                last_commit_count = success_count

            # Calculate and show progress stats after processing
            elapsed = time.time() - start_time
            rate = success_count / elapsed if elapsed > 0 else 0
            remaining = len(emails) - i
            eta = remaining / rate if rate > 0 else 0

            # Format ETA (show "..." for first few to get stable estimate)
            if i < 5:
                eta_str = "..."
            elif eta > 3600:
                eta_str = f"{eta / 3600:.1f}h"
            elif eta > 60:
                eta_str = f"{eta / 60:.0f}m"
            else:
                eta_str = f"{eta:.0f}s"

            # Update progress line
            print(f"\r\033[K  [{i}/{len(emails)}] {rate:.1f}/s | ETA {eta_str:>5} | {short_name}", end="", flush=True)
    finally:
        # Commit any remaining updates
        batch_conn.commit()
        batch_conn.close()
        signal.signal(signal.SIGINT, original_handler)

    elapsed_total = time.time() - start_time
    print("\n" + "-" * 50)
    if interrupted:
        remaining = len(emails) - success_count - error_count
        print("Rebuild Paused!")
        print(f"  Indexed: {success_count} emails in {elapsed_total:.1f}s")
        print(f"  Remaining: {remaining} emails")
        print("\n  Run 'ownmail rebuild' again to resume.")
    else:
        print("Rebuild Complete!")
        print(f"  Indexed: {success_count} emails in {elapsed_total:.1f}s")
    if error_count > 0:
        print(f"  Errors: {error_count}")
    print("-" * 50 + "\n")


def _populate_dates_only(
    archive: EmailArchive,
    pattern: str | None = None,
    force: bool = False,
    debug: bool = False,
) -> None:
    """Populate email_date for emails that are missing it.

    This is a fast path that avoids full reindexing. It reads the date_str
    from the database (or parses the .eml file if date_str is NULL) and
    converts it to a UTC ISO timestamp.

    Args:
        archive: EmailArchive instance
        pattern: Only process files matching this glob pattern
        force: If True, repopulate all dates (not just NULL ones)
        debug: If True, show per-email details
    """
    print("\n" + "=" * 50)
    print("ownmail - Populate Dates")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    # Build query
    like_pattern = None
    if pattern:
        like_pattern = "%" + pattern.replace("*", "%").replace("?", "_") + "%"

    t0 = time.time()
    print("Finding emails...", end="", flush=True)
    with sqlite3.connect(db_path) as conn:
        if like_pattern:
            if force:
                emails = conn.execute(
                    "SELECT email_id, filename, date_str FROM emails WHERE filename LIKE ?", (like_pattern,)
                ).fetchall()
            else:
                emails = conn.execute(
                    "SELECT email_id, filename, date_str FROM emails WHERE email_date IS NULL AND filename LIKE ?",
                    (like_pattern,),
                ).fetchall()
        else:
            if force:
                emails = conn.execute("SELECT email_id, filename, date_str FROM emails").fetchall()
            else:
                emails = conn.execute(
                    "SELECT email_id, filename, date_str FROM emails WHERE email_date IS NULL"
                ).fetchall()
        print(f" {len(emails)} emails ({time.time() - t0:.1f}s)")

    if not emails:
        print("\nAll emails already have dates." + (" Use --force to repopulate." if not force else ""))
        return

    print(f"\nPopulating dates for {len(emails)} emails...")

    success_count = 0
    skipped = 0
    interrupted = False
    start_time = time.time()

    def signal_handler(signum, frame):
        nonlocal interrupted
        interrupted = True
        print("\n\n⏸ Stopping after current email...")

    original_handler = signal.signal(signal.SIGINT, signal_handler)

    batch_conn = sqlite3.connect(db_path)
    batch_conn.execute("PRAGMA journal_mode = WAL")
    batch_conn.execute("PRAGMA synchronous = NORMAL")

    try:
        for i, (email_id, filename, date_str) in enumerate(emails, 1):
            if interrupted:
                break

            # Try to get date from existing date_str first (fast)
            email_date_iso = None
            if date_str:
                try:
                    msg_date = parsedate_to_datetime(date_str)
                    msg_date_utc = msg_date.astimezone(timezone.utc)
                    email_date_iso = msg_date_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                except Exception:
                    pass

            # If no date_str or parsing failed, try parsing the .eml file
            if not email_date_iso:
                filepath = archive.archive_dir / filename
                if filepath.exists():
                    try:
                        parsed = EmailParser.parse_file(filepath=filepath)
                        if parsed["date_str"]:
                            msg_date = parsedate_to_datetime(parsed["date_str"])
                            msg_date_utc = msg_date.astimezone(timezone.utc)
                            email_date_iso = msg_date_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                    except Exception:
                        pass

            if email_date_iso:
                if force:
                    batch_conn.execute(
                        "UPDATE emails SET email_date = ? WHERE email_id = ?", (email_date_iso, email_id)
                    )
                else:
                    batch_conn.execute(
                        "UPDATE emails SET email_date = COALESCE(email_date, ?) WHERE email_id = ?",
                        (email_date_iso, email_id),
                    )
                success_count += 1
            else:
                skipped += 1
                if debug:
                    print(f"\n  No date for: {filename}")

            # Commit every 200 emails
            if (success_count + skipped) % 200 == 0:
                batch_conn.commit()

            if i % 100 == 0 or i == len(emails):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                print(f"\r\033[K  [{i}/{len(emails)}] {rate:.0f}/s", end="", flush=True)
    finally:
        batch_conn.commit()
        batch_conn.close()
        signal.signal(signal.SIGINT, original_handler)

    elapsed_total = time.time() - start_time
    print("\n" + "-" * 50)
    if interrupted:
        print("Populate Dates Paused!")
        print("\n  Run 'ownmail rebuild --only dates' again to resume.")
    else:
        print("Populate Dates Complete!")
    print(f"  Updated: {success_count} emails in {elapsed_total:.1f}s")
    if skipped:
        print(f"  Skipped (no parseable date): {skipped}")
    print("-" * 50 + "\n")


def _reconcile_label_sidecars(
    archive: EmailArchive,
    pattern: str | None = None,
    debug: bool = False,
) -> None:
    """Reconcile per-email label sidecar files with the email_labels table.

    Sidecar files are the source of truth for labels/tags. For each email:
    - If a sidecar already exists, its labels overwrite whatever is in the
      DB (sidecar wins on divergence).
    - If no sidecar exists yet (e.g. an archive downloaded before sidecars
      existed), one is created from the email's current DB labels
      (one-time migration/backfill).
    - Labels recording ephemeral client state (``UNREAD``, left by Gmail
      syncs from before ownmail stopped capturing read/unread) are dropped
      from both, so old archives converge on what a fresh sync produces.

    This makes the DB a fully rebuildable cache of the sidecar files: if
    the DB were lost, `rebuild --only sidecars` on a fresh DB (after a
    plain `rebuild`) would restore all label state from disk.
    """
    print("\n" + "=" * 50)
    print("ownmail - Reconcile Label Sidecars")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    like_pattern = None
    if pattern:
        like_pattern = "%" + pattern.replace("*", "%").replace("?", "_") + "%"

    t0 = time.time()
    print("Finding emails...", end="", flush=True)
    with sqlite3.connect(db_path) as conn:
        if like_pattern:
            emails = conn.execute(
                "SELECT rowid, email_id, filename, email_date FROM emails WHERE filename LIKE ?", (like_pattern,)
            ).fetchall()
        else:
            emails = conn.execute("SELECT rowid, email_id, filename, email_date FROM emails").fetchall()
    print(f" {len(emails)} emails ({time.time() - t0:.1f}s)")

    if not emails:
        print("\nNo emails to reconcile.")
        return

    backfilled = 0
    reconciled = 0
    purged = 0
    unchanged = 0
    missing_files = 0
    start_time = time.time()

    conn = sqlite3.connect(db_path)
    try:
        for i, (rowid, _email_id, filename, email_date) in enumerate(emails, 1):
            filepath = archive.archive_dir / filename
            if not filepath.exists():
                missing_files += 1
                continue

            db_labels = [
                row[0]
                for row in conn.execute(
                    "SELECT label FROM email_labels WHERE email_rowid = ? ORDER BY label", (rowid,)
                ).fetchall()
            ]

            sidecar_labels = sidecar.read_labels(filepath)
            changed = False

            if sidecar_labels is None:
                # No sidecar yet - back-fill it from current DB state.
                sidecar_labels = [lbl for lbl in db_labels if lbl not in roles.EPHEMERAL_LABELS]
                sidecar.write_labels(filepath, sidecar_labels)
                backfilled += 1
                changed = True
                if debug:
                    print(f"\n  Backfilled sidecar for {filename}: {sidecar_labels}")
            else:
                kept = [lbl for lbl in sidecar_labels if lbl not in roles.EPHEMERAL_LABELS]
                if kept != sidecar_labels:
                    # Read/unread is no longer archived - drop it from the sidecar.
                    sidecar.write_labels(filepath, kept)
                    if debug:
                        print(f"\n  Purged ephemeral labels from {filename}: {sidecar_labels} -> {kept}")
                    sidecar_labels = kept
                    purged += 1
                    changed = True

            if sorted(sidecar_labels) != sorted(db_labels):
                # Sidecar wins - rewrite the DB to match it.
                set_db_labels(conn, rowid, sidecar_labels, email_date)
                reconciled += 1
                changed = True
                if debug:
                    print(f"\n  Reconciled {filename}: DB {db_labels} -> sidecar {sidecar_labels}")

            if not changed:
                unchanged += 1

            if i % 200 == 0:
                conn.commit()

            if i % 100 == 0 or i == len(emails):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                print(f"\r\033[K  [{i}/{len(emails)}] {rate:.0f}/s", end="", flush=True)
    finally:
        conn.commit()
        conn.close()

    elapsed_total = time.time() - start_time
    print("\n" + "-" * 50)
    print("Reconcile Complete!")
    print(f"  Backfilled (new sidecar written): {backfilled}")
    print(f"  Purged (ephemeral labels dropped): {purged}")
    print(f"  Reconciled (DB updated from sidecar): {reconciled}")
    print(f"  Unchanged: {unchanged}")
    if missing_files:
        print(f"  Skipped (file missing on disk): {missing_files}")
    print(f"  Done in {elapsed_total:.1f}s")
    print("-" * 50 + "\n")


def _index_single_email(
    archive: EmailArchive,
    email_id: str,
    filepath: Path,
    debug: bool = False,
) -> bool:
    """Index a single email file."""
    try:
        parsed = EmailParser.parse_file(filepath=filepath)

        # Compute email_date from parsed date_str
        email_date_iso = None
        date_str = parsed["date_str"]
        if date_str:
            try:
                msg_date = parsedate_to_datetime(date_str)
                msg_date_utc = msg_date.astimezone(timezone.utc)
                email_date_iso = msg_date_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            except Exception:
                pass

        archive.db.index_email(
            email_id=email_id,
            subject=parsed["subject"],
            sender=parsed["sender"],
            recipients=parsed["recipients"],
            date_str=parsed["date_str"],
            body=parsed["body"],
            attachments=parsed["attachments"],
            labels=sidecar.read_labels(filepath),
            email_date=email_date_iso,
        )
        return True
    except Exception as e:
        print(f"\n  Error indexing {filepath.name}: {e}")
        return False


def _index_email_for_rebuild(
    archive: EmailArchive,
    email_id: str,
    filepath: Path,
    conn: sqlite3.Connection,
    debug: bool = False,
) -> bool:
    """Index email during rebuild (uses batch connection)."""
    try:
        # Read file once for both parsing and hashing
        with open(filepath, "rb") as f:
            content = f.read()

        content_hash = hashlib.sha256(content).hexdigest()
        parsed = EmailParser.parse_file(content=content)

        # Create snippet from body
        body = parsed["body"]
        snippet = body[:200] + "..." if len(body) > 200 else body

        labels_list = sidecar.read_labels(filepath)
        if labels_list is None:
            existing_labels_rows = conn.execute(
                "SELECT el.label FROM email_labels el JOIN emails e ON e.rowid = el.email_rowid WHERE e.email_id = ?",
                (email_id,),
            ).fetchall()
            labels_list = [row[0] for row in existing_labels_rows]
        recipients = parsed["recipients"]

        # recipient_emails normalized table is populated below

        # Check if has attachments
        attachments = parsed["attachments"]
        has_attachments = 1 if attachments else 0

        # Compute email_date from parsed date_str
        email_date_iso = None
        date_str = parsed["date_str"]
        if date_str:
            try:
                msg_date = parsedate_to_datetime(date_str)
                msg_date_utc = msg_date.astimezone(timezone.utc)
                email_date_iso = msg_date_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            except Exception:
                pass

        # Update metadata in emails table and get rowid in one query
        row = conn.execute(
            """
            UPDATE emails SET
                subject = ?,
                sender = ?,
                recipients = ?,
                date_str = ?,
                snippet = ?,
                indexed_hash = ?,
                content_hash = COALESCE(content_hash, ?),
                has_attachments = ?,
                email_date = COALESCE(email_date, ?)
            WHERE email_id = ?
            RETURNING rowid
            """,
            (
                parsed["subject"],
                parsed["sender"],
                recipients,
                parsed["date_str"],
                snippet,
                content_hash,
                content_hash,
                has_attachments,
                email_date_iso,
                email_id,
            ),
        ).fetchone()

        # Insert into FTS and normalized tables
        if row:
            rowid = row[0]

            conn.execute(
                """
                INSERT INTO emails_fts (rowid, subject, sender, recipients, body, attachments)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (rowid, parsed["subject"], parsed["sender"], recipients, parsed["body"], attachments),
            )

            # Populate email_recipients normalized table
            conn.execute("DELETE FROM email_recipients WHERE email_rowid = ?", (rowid,))
            if recipients:
                normalized = ArchiveDatabase._normalize_recipients(recipients)
                if normalized:
                    for email_addr in normalized.strip(",").split(","):
                        email_addr = email_addr.strip()
                        if email_addr:
                            conn.execute(
                                "INSERT OR IGNORE INTO email_recipients (email_rowid, recipient_email) VALUES (?, ?)",
                                (rowid, email_addr),
                            )

            # Populate email_labels normalized table
            # Get email_date from emails table for the covering index
            email_date_row = conn.execute("SELECT email_date FROM emails WHERE rowid = ?", (rowid,)).fetchone()
            email_date = email_date_row[0] if email_date_row else None

            set_db_labels(conn, rowid, labels_list, email_date)

        return True
    except Exception as e:
        print(f"\n  Error indexing {filepath.name}: {e}")
        return False


def _verify_single_file(args: tuple) -> tuple:
    """Verify a single file's hash. Returns (status, filename).

    Status: 'ok', 'missing', 'corrupted', 'no_hash'
    """
    archive_dir, filename, stored_hash = args

    filepath = archive_dir / filename

    if not filepath.exists():
        return ("missing", filename)

    if not stored_hash:
        return ("no_hash", filename)

    # Compute current hash
    with open(filepath, "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()

    if current_hash == stored_hash:
        return ("ok", filename)
    else:
        return ("corrupted", filename)


def _find_trash_labelled(db_path: Path) -> list[tuple[str, str, int]]:
    """Find archived emails carrying a label that means trash or spam.

    These are emails downloaded before ownmail could recognize the source
    folder as trash/spam — a server naming its trash anything other than
    '[Gmail]/Trash' used to sync straight into the archive.

    Resolution is by name only: the SPECIAL-USE flags that identified the
    folder at sync time aren't kept in the archive. That makes this a report
    and not a fix — a user label genuinely named 'Archive' or 'Junk' looks
    identical here.

    Emails already in ownmail's local trash are skipped; they've been dealt
    with.

    Returns:
        List of (label, account, count), largest first
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT el.label, e.account, COUNT(*)
            FROM email_labels el
            JOIN emails e ON e.rowid = el.email_rowid
            WHERE e.trashed_at IS NULL
            GROUP BY el.label, e.account
            """
        ).fetchall()

    hits = [
        (label, account or "(unknown)", count)
        for label, account, count in rows
        if roles.role_for_label(label) in (roles.TRASH, roles.SPAM)
    ]
    return sorted(hits, key=lambda row: row[2], reverse=True)


def cmd_verify(archive: EmailArchive, fix: bool = False, verbose: bool = False) -> None:
    """Verify archive integrity: files, hashes, and database health.

    Checks:
    - File integrity (missing files, hash mismatches)
    - Moved/renamed files (missing + orphaned with matching hash)
    - Orphaned files (on disk but not indexed)
    - Database health (missing metadata, FTS sync, stale hashes)
    - System labels (emails wrongly archived from a trash/spam folder)

    With --fix:
    - Updates DB paths for moved/renamed files
    - Removes DB rows for files that no longer exist on disk
    - Rebuilds FTS index when out of sync
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print("\n" + "=" * 50)
    print("ownmail - Verify")
    print("=" * 50 + "\n")

    total_start = time.time()
    issues_found = 0
    issues_fixed = 0

    db_path = archive.db.db_path

    # ── Phase 1: File integrity ──────────────────────────────────────────

    with sqlite3.connect(db_path) as conn:
        emails = conn.execute("SELECT email_id, filename, content_hash FROM emails").fetchall()

    total = len(emails)
    ok_count = 0
    missing_count = 0
    corrupted_count = 0
    no_hash_count = 0
    corrupted_files = []
    missing_files = []
    missing_email_ids = []
    missing_hashes = {}  # content_hash -> (filename, email_id)
    indexed_files = set()

    if total == 0:
        print("No emails in database.\n")
    else:
        print(f"1. Verifying {total} files...\n")

        work_items = []
        email_id_by_filename = {}
        hash_by_filename = {}
        for email_id, filename, stored_hash in emails:
            indexed_files.add(filename)
            email_id_by_filename[filename] = email_id
            hash_by_filename[filename] = stored_hash
            work_items.append((archive.archive_dir, filename, stored_hash))

        completed = 0
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(_verify_single_file, item): item for item in work_items}

            for future in as_completed(futures):
                completed += 1
                print(f"  [{completed}/{total}] Verifying...\033[K", end="\r")

                status, filename = future.result()
                if status == "ok":
                    ok_count += 1
                elif status == "missing":
                    missing_count += 1
                    missing_files.append(filename)
                    eid = email_id_by_filename[filename]
                    missing_email_ids.append(eid)
                    stored_hash = hash_by_filename[filename]
                    if stored_hash:
                        missing_hashes[stored_hash] = (filename, eid)
                elif status == "corrupted":
                    corrupted_count += 1
                    corrupted_files.append(filename)
                elif status == "no_hash":
                    no_hash_count += 1

        # Orphaned files
        print("\n  Scanning for orphaned files...\033[K", end="\r")
        orphaned_files = []
        for subdir in ["emails", "sources"]:
            check_dir = archive.archive_dir / subdir
            if check_dir.exists():
                for eml_file in check_dir.rglob("*.eml"):
                    rel_path = str(eml_file.relative_to(archive.archive_dir))
                    if rel_path not in indexed_files:
                        orphaned_files.append(rel_path)

        # Detect moved/renamed files by matching hashes
        moved_files = []  # (old_path, new_path, email_id)
        if missing_hashes and orphaned_files:
            remaining_orphans = []
            for orphan_path in orphaned_files:
                orphan_full = archive.archive_dir / orphan_path
                try:
                    with open(orphan_full, "rb") as f:
                        orphan_hash = hashlib.sha256(f.read()).hexdigest()
                except OSError:
                    remaining_orphans.append(orphan_path)
                    continue

                if orphan_hash in missing_hashes:
                    old_path, eid = missing_hashes.pop(orphan_hash)
                    moved_files.append((old_path, orphan_path, eid))
                    missing_files.remove(old_path)
                    missing_email_ids.remove(eid)
                    missing_count -= 1
                else:
                    remaining_orphans.append(orphan_path)
            orphaned_files = remaining_orphans

        # Report file results
        print(f"\n  ✓ OK: {ok_count}")
        if no_hash_count > 0:
            issues_found += 1
            print(f"  ? No hash stored: {no_hash_count}")
        if moved_files:
            issues_found += 1
            moved_labels = [f"{old} → {new}" for old, new, _ in moved_files]
            _print_file_list(moved_labels, "⟳ Moved/renamed", verbose)
            if fix:
                with sqlite3.connect(db_path) as conn:
                    for _old_path, new_path, eid in moved_files:
                        conn.execute(
                            "UPDATE emails SET filename = ? WHERE email_id = ?",
                            (new_path, eid),
                        )
                    conn.commit()
                issues_fixed += 1
                print(f"    → Updated {len(moved_files)} DB paths")
        if missing_count > 0:
            issues_found += 1
            _print_file_list(missing_files, "✗ Missing from disk", verbose)
            if fix:
                with sqlite3.connect(db_path) as conn:
                    # Collect affected accounts before deleting
                    affected_accounts = set()
                    for eid in missing_email_ids:
                        row = conn.execute("SELECT account FROM emails WHERE email_id = ?", (eid,)).fetchone()
                        if row and row[0]:
                            affected_accounts.add(row[0])
                        conn.execute("DELETE FROM emails WHERE email_id = ?", (eid,))
                    # Also reset sync state in the same transaction
                    for account in affected_accounts:
                        conn.execute(
                            "DELETE FROM sync_state WHERE key LIKE ?",
                            (f"{account}/%",),
                        )
                    conn.commit()
                issues_fixed += 1
                print(f"    → Removed {missing_count} stale DB entries")
                if affected_accounts:
                    # Verify sync state was actually cleared
                    with sqlite3.connect(db_path) as verify_conn:
                        for account in affected_accounts:
                            remaining = verify_conn.execute(
                                "SELECT COUNT(*) FROM sync_state WHERE key LIKE ?",
                                (f"{account}/%",),
                            ).fetchone()[0]
                            if remaining > 0:
                                # Force delete with a fresh connection
                                verify_conn.execute(
                                    "DELETE FROM sync_state WHERE key LIKE ?",
                                    (f"{account}/%",),
                                )
                                verify_conn.commit()
                    print(
                        f"    → Reset sync state for {len(affected_accounts)} account(s) (next backup will do a full sync)"
                    )
        if len(orphaned_files) > 0:
            issues_found += 1
            _print_file_list(orphaned_files, "? On disk but not indexed", verbose)
        if corrupted_count > 0:
            issues_found += 1
            _print_file_list(corrupted_files, "✗ CORRUPTED (hash mismatch)", verbose)

    # ── Phase 2: Database health ─────────────────────────────────────────

    print("\n2. Checking database...\n")

    with sqlite3.connect(db_path) as conn:
        # Missing metadata
        missing_metadata = conn.execute("SELECT COUNT(*) FROM emails WHERE subject IS NULL").fetchone()[0]

        if missing_metadata > 0:
            issues_found += 1
            print(f"  ✗ {missing_metadata} emails missing metadata (not indexed)")
        else:
            print("  ✓ All emails have metadata")

        # Hash mismatches (indexed_hash vs content_hash)
        hash_mismatches = conn.execute("""
            SELECT COUNT(*) FROM emails
            WHERE content_hash IS NOT NULL
              AND indexed_hash IS NOT NULL
              AND content_hash != indexed_hash
        """).fetchone()[0]

        if hash_mismatches > 0:
            issues_found += 1
            print(f"  ✗ {hash_mismatches} emails with stale index")
        else:
            print("  ✓ All indexed emails up to date")

        # Missing hashes
        null_content_hash = conn.execute("SELECT COUNT(*) FROM emails WHERE content_hash IS NULL").fetchone()[0]

        if null_content_hash > 0:
            issues_found += 1
            print(f"  ? {null_content_hash} emails without content hash")
        else:
            print("  ✓ All emails have hashes")

        # Duplicate content (same content_hash, different email_id)
        dup_rows = conn.execute("""
            SELECT content_hash, COUNT(*) as cnt
            FROM emails
            WHERE content_hash IS NOT NULL
            GROUP BY content_hash
            HAVING cnt > 1
        """).fetchall()
        dup_count = sum(cnt - 1 for _, cnt in dup_rows)

        if dup_count > 0:
            issues_found += 1
            print(f"  ✗ {dup_count} duplicate emails ({len(dup_rows)} unique messages duplicated)")
            if verbose:
                for content_hash, _cnt in dup_rows[:10]:
                    rows = conn.execute(
                        "SELECT email_id, provider_id, filename FROM emails WHERE content_hash = ?", (content_hash,)
                    ).fetchall()
                    for eid, pid, fn in rows:
                        print(f"      {eid} | {pid} | {fn}")
                if len(dup_rows) > 10:
                    print(f"      ... and {len(dup_rows) - 10} more groups")
            if fix:
                removed_count = 0
                removed_files = 0
                for content_hash, _cnt in dup_rows:
                    # Get all rows for this content_hash, keep the one with highest rowid (newest)
                    rows = conn.execute(
                        "SELECT rowid, email_id, filename FROM emails WHERE content_hash = ? ORDER BY rowid DESC",
                        (content_hash,),
                    ).fetchall()
                    # Keep the first (newest), delete the rest
                    for rowid, _email_id, filename in rows[1:]:
                        # Delete labels
                        conn.execute("DELETE FROM email_labels WHERE email_rowid = ?", (rowid,))
                        # Delete recipients
                        conn.execute("DELETE FROM email_recipients WHERE email_rowid = ?", (rowid,))
                        # Delete the email row
                        conn.execute("DELETE FROM emails WHERE rowid = ?", (rowid,))
                        # Delete the orphaned .eml file
                        eml_path = archive.archive_dir / filename
                        if eml_path.exists():
                            eml_path.unlink()
                            removed_files += 1
                        removed_count += 1
                # Rebuild FTS since we can't delete from contentless FTS5
                conn.execute("DROP TABLE IF EXISTS emails_fts")
                conn.execute("""
                    CREATE VIRTUAL TABLE emails_fts USING fts5(
                        subject, sender, recipients, body, attachments,
                        content='', tokenize='porter unicode61'
                    )
                """)
                # Clear indexed_hash so 'rebuild' will re-parse .eml files
                # and restore full body text in FTS
                conn.execute("UPDATE emails SET indexed_hash = NULL WHERE subject IS NOT NULL")
                conn.commit()
                issues_fixed += 1
                print(f"    → Removed {removed_count} duplicate DB entries and {removed_files} orphaned files")
                print("    → Run 'ownmail rebuild' to restore search index")
        else:
            print("  ✓ No duplicate emails")

    # ── Phase 3: System labels ───────────────────────────────────────────

    print("\n3. Checking system labels...\n")

    polluted = _find_trash_labelled(db_path)
    polluted_total = sum(count for _, _, count in polluted)

    if polluted:
        issues_found += 1
        print(f"  ✗ {polluted_total} emails carry a trash/spam label")
        for label, account, count in polluted:
            print(f"      {label} ({account}): {count}")
        print("\n    Archived before ownmail could tell the folder was trash/spam.")
        print("    Nothing is changed automatically — the match is by folder name,")
        print("    so check them before deleting anything.")
        print("    'ownmail reconcile' reports the same mail against the current")
        print("    download filter and can move it to the bin, reversibly.")
    else:
        print("  ✓ No emails labelled trash/spam")

    # ── Summary ──────────────────────────────────────────────────────────

    total_time = time.time() - total_start

    print("\n" + "-" * 50)
    if issues_found == 0:
        print("All checks passed!")
        print(f"  ✓ {ok_count} files verified, database healthy")
    else:
        print(f"Verify complete — {issues_found} issue(s) found")
        if fix:
            fixed_remaining = issues_found - issues_fixed
            if issues_fixed > 0:
                print(f"  Fixed: {issues_fixed}")
            if fixed_remaining > 0:
                print(f"  Remaining: {fixed_remaining}")
                # Actionable suggestions for unfixed issues
                suggestions = []
                if moved_files:
                    suggestions.append("  • 'ownmail verify --fix' to update paths for moved files")
                if missing_metadata > 0 or hash_mismatches > 0:
                    suggestions.append("  • 'ownmail rebuild' to populate metadata / update stale index")
                if len(orphaned_files) > 0:
                    suggestions.append("  • 'ownmail rebuild' to index orphaned files")
                if corrupted_count > 0:
                    suggestions.append("  • Delete corrupted files, then 'ownmail backup' to re-download")
                if dup_count > 0:
                    suggestions.append("  • 'ownmail verify --fix' to remove duplicate emails")
                if polluted:
                    suggestions.append("  • 'ownmail reconcile' to review and bin trash/spam-labelled emails")
                for s in suggestions:
                    print(s)
        else:
            # Suggestions for all issues
            suggestions = []
            if moved_files:
                suggestions.append("  • 'ownmail verify --fix' to update paths for moved files")
            if missing_count > 0:
                suggestions.append("  • 'ownmail verify --fix' to remove stale DB entries for missing files")
            if len(orphaned_files) > 0:
                suggestions.append("  • 'ownmail rebuild' to index orphaned files")
            if corrupted_count > 0:
                suggestions.append("  • Delete corrupted files, then 'ownmail backup' to re-download")
            if missing_metadata > 0 or hash_mismatches > 0:
                suggestions.append("  • 'ownmail rebuild' to populate metadata / update stale index")
            if dup_count > 0:
                suggestions.append("  • 'ownmail verify --fix' to remove duplicate emails")
            if polluted:
                suggestions.append("  • 'ownmail reconcile' to review and bin trash/spam-labelled emails")
            if suggestions:
                print("\n  To fix:")
                for s in suggestions:
                    print(s)

    print(f"\n  Time: {total_time:.1f}s")
    print("-" * 50 + "\n")


def cmd_sync_check(
    archive: EmailArchive,
    source_name: str = None,
    verbose: bool = False,
) -> None:
    """Compare local archive with server.

    Supports both Gmail API and IMAP sources. When no --source is specified,
    checks the first configured source.
    """
    print("\n" + "=" * 50)
    print("ownmail - Sync Check")
    print("=" * 50 + "\n")

    from ownmail.config import get_source_by_name, get_sources

    config = archive.config
    sources = get_sources(config)

    if not sources:
        print("No sources configured. Run 'ownmail setup' first.")
        return

    # Find the source to check
    source = None
    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Source '{source_name}' not found")
            return
    else:
        source = sources[0]

    source_type = source.get("type")
    account = source["account"]
    print(f"Source: {source['name']} ({account})")

    # Create and authenticate provider
    if source_type == "gmail_api":
        from ownmail.providers.gmail import GmailProvider

        provider = GmailProvider(
            account=account,
            keychain=archive.keychain,
            source_name=source["name"],
            exclude_roles=source.get("exclude_roles"),
        )
    elif source_type == "imap":
        from ownmail.providers.imap import ImapProvider

        provider = ImapProvider(
            account=account,
            keychain=archive.keychain,
            host=source.get("host", "imap.gmail.com"),
            port=source.get("port", 993),
            exclude_folders=source.get("exclude_folders"),
            source_name=source["name"],
            exclude_roles=source.get("exclude_roles"),
        )
    else:
        print(f"❌ sync-check is not supported for source type '{source_type}'")
        return

    provider.authenticate()

    # Get all message IDs from server
    print("Fetching message IDs from server...")
    server_ids = set(provider.get_all_message_ids())

    # Close IMAP connection if applicable
    if hasattr(provider, "close"):
        provider.close()

    # Get all local message IDs for this account
    local_ids = archive.db.get_downloaded_ids(account)

    print(f"\nServer: {len(server_ids)} emails")
    print(f"Local:  {len(local_ids)} emails\n")

    # Find differences
    on_server_not_local = server_ids - local_ids
    on_local_not_server = local_ids - server_ids
    in_sync = server_ids & local_ids

    print("-" * 50)
    print("Sync Check Complete!")
    print(f"  ✓ In sync: {len(in_sync)}")

    # Display differences
    if on_server_not_local:
        print(f"  ↓ On server but not local: {len(on_server_not_local)}")
        show_count = len(on_server_not_local) if verbose else min(len(on_server_not_local), 5)
        for msg_id in list(on_server_not_local)[:show_count]:
            print(f"      {msg_id}")
        if not verbose and len(on_server_not_local) > 5:
            print(f"      ... and {len(on_server_not_local) - 5} more (use --verbose to show all)")
        print("\n  Run 'backup' to download these emails.")

    if on_local_not_server:
        # Get filenames for these
        with sqlite3.connect(archive.db.db_path) as conn:
            local_only_files = []
            for msg_id in on_local_not_server:
                result = conn.execute(
                    "SELECT filename FROM emails WHERE provider_id = ? AND account = ?", (msg_id, account)
                ).fetchone()
                if result:
                    local_only_files.append(f"{result[0]} ({msg_id})")
                else:
                    local_only_files.append(msg_id)

        print(f"  ✗ On local but not on server (deleted from server?): {len(on_local_not_server)}")
        show_count = len(local_only_files) if verbose else min(len(local_only_files), 5)
        for f in local_only_files[:show_count]:
            print(f"      {f}")
        if not verbose and len(local_only_files) > 5:
            print(f"      ... and {len(local_only_files) - 5} more (use --verbose to show all)")

    if not on_server_not_local and not on_local_not_server:
        print("\n  ✓ Local archive is fully in sync with server!")
    print("-" * 50 + "\n")


def cmd_update_labels(archive: EmailArchive, source_name: str = None) -> None:
    """Backfill labels for emails that have none.

    This is a backfill, not a re-snapshot: the query below selects only
    emails with no rows in ``email_labels``, so a message that already
    carries labels is never revisited. That is deliberate under doc-8 —
    capture transfers ownership, and re-reading label state from the server
    afterwards would let a non-authoritative source overwrite ownmail's own.

    Where a sidecar already exists it wins, and the DB is rebuilt from it
    rather than the file being overwritten. Only an email with labels
    nowhere — no DB rows, no sidecar — gets a derived value: the IMAP folder
    it was downloaded from, or a fresh fetch for Gmail.

    Labels are stored in the DB and in a per-email JSON sidecar file
    (source of truth) - never injected into the .eml itself, which stays
    pure RFC 5322 email exactly as received from the server.
    """
    print("\n" + "=" * 50)
    print("ownmail - Update Labels")
    print("=" * 50 + "\n")

    from ownmail.config import get_source_by_name, get_sources

    config = archive.config
    sources = get_sources(config)

    if not sources:
        print("No sources configured. Run 'ownmail setup' first.")
        return

    # Find the source to update
    source = None
    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Source '{source_name}' not found")
            return
    else:
        # Use the first source (any type)
        source = sources[0]

    source_type = source.get("type")
    account = source["account"]
    print(f"Source: {source['name']} ({account})")

    # Get all downloaded emails for this account that don't have labels yet
    with sqlite3.connect(archive.db.db_path) as conn:
        emails = conn.execute(
            """SELECT e.email_id, e.provider_id, e.filename FROM emails e
               WHERE (e.account = ? OR e.account IS NULL)
               AND NOT EXISTS (
                   SELECT 1 FROM email_labels el WHERE el.email_rowid = e.rowid
               )""",
            (account,),
        ).fetchall()

    if not emails:
        print("No emails need labels.")
        return

    if source_type == "gmail_api":
        _update_labels_gmail(archive, account, emails)
    elif source_type == "imap":
        _update_labels_imap(archive, account, emails)
    else:
        print(f"update-labels is not supported for source type '{source_type}'")


def _update_labels_imap(archive: EmailArchive, account: str, emails: list) -> None:
    """Backfill labels for IMAP emails from the folder in their provider_id.

    IMAP provider_id format is "folder:uid", so the folder name is the only
    label derivable offline — no IMAP connection needed. That makes this a
    lossy source: a message the dedup scan found in several folders has one
    folder in its provider_id and the rest only in its sidecar. So an
    existing sidecar is restored, never overwritten; the folder name is used
    only when there is no sidecar at all and the label would otherwise be
    nothing.
    """
    print(f"Deriving labels from IMAP folder names for {len(emails)} emails...")

    success_count = 0
    restored_count = 0
    skip_count = 0

    with sqlite3.connect(archive.db.db_path) as conn:
        for email_id, provider_id, filename in emails:
            if ":" not in provider_id:
                skip_count += 1
                continue

            folder = provider_id.rsplit(":", 1)[0]
            if not folder:
                skip_count += 1
                continue

            row = conn.execute(
                "SELECT rowid, email_date FROM emails WHERE email_id = ?",
                (email_id,),
            ).fetchone()
            if not row:
                skip_count += 1
                continue
            rowid, email_date = row

            filepath = archive.archive_dir / filename
            sidecar_labels = sidecar.read_labels(filepath)
            if sidecar_labels is not None:
                # Files are the source of truth — rebuild the DB from disk
                # rather than flattening disk to one folder name.
                set_db_labels(conn, rowid, sidecar_labels, email_date)
                restored_count += 1
                continue

            set_db_labels(conn, rowid, [folder], email_date)
            sidecar.write_labels(filepath, [folder])
            success_count += 1

    print("\n" + "-" * 50)
    print("Update Labels Complete!")
    print(f"  Updated: {success_count} emails")
    if restored_count > 0:
        print(f"  Restored from sidecar: {restored_count}")
    if skip_count > 0:
        print(f"  Skipped: {skip_count}")
    print("-" * 50 + "\n")


def _update_labels_gmail(archive: EmailArchive, account: str, emails: list) -> None:
    """Backfill labels for Gmail API emails by fetching from the server.

    An existing sidecar wins and is restored to the DB without a fetch —
    the server is not authoritative for a message ownmail already captured.
    A failed fetch is counted as an error, not as "no labels": clearing
    label state on a rate-limited request would be silent data loss.
    """
    from ownmail.providers.gmail import GmailProvider

    print(f"Fetching labels for {len(emails)} emails...")
    print("(Press Ctrl-C to stop - progress is saved)\n")

    # Create and authenticate provider
    provider = GmailProvider(account=account, keychain=archive.keychain)
    provider.authenticate()

    success_count = 0
    restored_count = 0
    skip_count = 0
    error_count = 0
    interrupted = False

    def signal_handler(signum, frame):
        nonlocal interrupted
        if interrupted:
            print("\n\nForce quit.")
            sys.exit(1)
        interrupted = True
        print("\n\n⏸ Stopping after current email... (Ctrl-C again to force quit)")

    original_handler = signal.signal(signal.SIGINT, signal_handler)

    try:
        with sqlite3.connect(archive.db.db_path) as conn:
            for i, (email_id, provider_id, filename) in enumerate(emails, 1):
                if interrupted:
                    break

                print(f"  [{i}/{len(emails)}] Fetching labels...\033[K", end="\r")

                try:
                    filepath = archive.archive_dir / filename
                    sidecar_labels = sidecar.read_labels(filepath)

                    if sidecar_labels is None:
                        labels = provider.get_labels_for_message(provider_id)
                        if labels is None:
                            # The call failed. Leave the email alone so a
                            # later run retries it, rather than recording
                            # "no labels" and clearing it.
                            print(f"\n  Could not fetch labels for {provider_id}")
                            error_count += 1
                            continue
                    else:
                        # Already owned locally — the DB is what's stale here,
                        # so rebuild it from disk without asking the server.
                        labels = sidecar_labels

                    row = conn.execute(
                        "SELECT rowid, email_date FROM emails WHERE email_id = ?",
                        (email_id,),
                    ).fetchone()
                    if not row:
                        skip_count += 1
                        continue
                    rowid, email_date = row

                    set_db_labels(conn, rowid, labels, email_date)

                    if sidecar_labels is None:
                        sidecar.write_labels(filepath, labels)
                        success_count += 1
                    else:
                        restored_count += 1

                    # Commit periodically
                    if (success_count + restored_count) % 50 == 0:
                        conn.commit()

                except Exception as e:
                    print(f"\n  Error processing {provider_id}: {e}")
                    error_count += 1

    finally:
        signal.signal(signal.SIGINT, original_handler)

    print("\n" + "-" * 50)
    if interrupted:
        print("Update Labels Paused!")
    else:
        print("Update Labels Complete!")
    print(f"  Updated: {success_count} emails")
    if restored_count > 0:
        print(f"  Restored from sidecar: {restored_count}")
    print(f"  Skipped (not in index): {skip_count}")
    if error_count > 0:
        print(f"  Errors: {error_count}")
    print("-" * 50 + "\n")


def _current_labels(conn, rowid: int, filepath: Path) -> list[str]:
    """An email's labels as they stand, sidecar first.

    Files are the source of truth (invariant #1), so the sidecar wins wherever
    it exists and the DB is only consulted for emails archived before sidecars.
    """
    labels = sidecar.read_labels(filepath)
    if labels is None:
        labels = [row[0] for row in conn.execute("SELECT label FROM email_labels WHERE email_rowid = ?", (rowid,))]
    return list(dict.fromkeys(labels))


def cmd_relabel(
    archive: EmailArchive,
    source_name: str | None = None,
    strategy: str = "union",
    apply: bool = False,
) -> None:
    """Re-derive IMAP folder membership for messages already in the archive.

    A message living in several folders should carry all of them as labels, and
    for archives captured before TASK-34 it does not — the scan flattened
    membership to the one folder the message was downloaded from. Nothing else
    repairs that: ``update-labels`` visits only emails with no labels at all,
    and ``download`` short-circuits on content hash before ever reconsidering
    them. The information is still on the server, and only until purge.

    This re-reads label state from the server after capture, which doc-8
    otherwise forbids. It is admissible because of *how* it writes, not because
    the archive is any less authoritative:

    - ``union`` (the default) only ever adds. It cannot overwrite what the
      archive holds, so the invariant that matters — server state never
      replaces local state — is intact. The cost is that a folder the user
      moved the message into *after* capture is indistinguishable from one the
      buggy scan missed, and gets adopted as an extra label.
    - ``server`` is a true re-snapshot and will drop labels the server no
      longer reports. That follows post-capture changes, which doc-8 calls a
      bug — it is offered because it is the only way to correct a wrong label
      rather than merely a missing one, and the operator is the one who knows
      whether they have reorganised since capture.

    Nothing is written without ``apply``; the default run reports the diff.

    With no ``source_name`` every IMAP source is repaired in turn. A named
    source that isn't IMAP is an error, since the user asked for it by name;
    the same source encountered while sweeping all of them is just skipped.
    """
    print("\n" + "=" * 50)
    print("ownmail - Relabel")
    print("=" * 50 + "\n")

    from ownmail.config import get_source_by_name, get_sources

    if source_name:
        source = get_source_by_name(archive.config, source_name)
        if not source:
            print(f"❌ Source '{source_name}' not found")
            return
        if source.get("type") != "imap":
            print(f"relabel is not supported for source type '{source.get('type')}' — IMAP folders only")
            return
        sources = [source]
    else:
        sources = [s for s in get_sources(archive.config) if s.get("type") == "imap"]
        if not sources:
            print("No IMAP sources configured — relabel repairs IMAP folder labels only.")
            return

    print(f"Strategy: {strategy}" + ("" if apply else "   (dry run — pass --apply to write)"))

    for source in sources:
        _relabel_source(archive, source, strategy, apply)


def _relabel_source(
    archive: EmailArchive,
    source: dict,
    strategy: str,
    apply: bool,
) -> None:
    """Rescan one IMAP source's folders and repair its archived labels."""
    account = source["account"]
    print(f"\nSource: {source['name']} ({account})")

    from ownmail.providers.imap import ImapProvider

    provider = ImapProvider(
        account=account,
        keychain=archive.keychain,
        host=source.get("host", "imap.gmail.com"),
        port=source.get("port", 993),
        exclude_folders=source.get("exclude_folders"),
        source_name=source["name"],
        exclude_roles=source.get("exclude_roles"),
    )
    provider.authenticate()

    try:
        membership = provider.scan_folder_membership()
    finally:
        provider.close()

    if membership is None:
        print(
            "\nThis source scans through Gmail's All Mail folder, which keys "
            "membership by Message-ID rather than by the folder:uid archived "
            "rows carry. relabel supports standard IMAP sources only."
        )
        return

    with sqlite3.connect(archive.db.db_path) as conn:
        emails = conn.execute(
            "SELECT rowid, provider_id, filename, email_date FROM emails WHERE account = ?",
            (account,),
        ).fetchall()

        if not emails:
            print("No archived emails for this source.")
            return

        print(f"\nComparing {len(emails)} archived emails against {len(membership)} scanned messages...")

        changed: list[tuple[str, list[str], list[str]]] = []
        matched = 0
        unmatched = 0
        interrupted = False

        def signal_handler(signum, frame):
            nonlocal interrupted
            if interrupted:
                print("\n\nForce quit.")
                sys.exit(1)
            interrupted = True
            print("\n\n⏸ Stopping after current email... (Ctrl-C again to force quit)")

        original_handler = signal.signal(signal.SIGINT, signal_handler)
        try:
            for rowid, provider_id, filename, email_date in emails:
                if interrupted:
                    break

                folders = membership.get(provider_id)
                if folders is None:
                    # Not on the server any more, or its UIDs were reissued.
                    unmatched += 1
                    continue

                matched += 1
                folders = list(dict.fromkeys(folders))
                filepath = archive.archive_dir / filename
                current = _current_labels(conn, rowid, filepath)

                if strategy == "server":
                    new_labels = folders
                else:
                    new_labels = current + [f for f in folders if f not in current]

                if set(new_labels) == set(current):
                    continue

                changed.append((filename, current, new_labels))

                if apply:
                    # Sidecar first — it is the source of truth, so an
                    # interrupt between the two writes leaves the repair on
                    # disk and only the rebuildable index behind.
                    sidecar.write_labels(filepath, new_labels)
                    set_db_labels(conn, rowid, new_labels, email_date)
                    if len(changed) % 500 == 0:
                        conn.commit()
                        print(f"  Rewritten {len(changed)}...\033[K", end="\r", flush=True)
        finally:
            signal.signal(signal.SIGINT, original_handler)

    added = sum(len(set(new) - set(old)) for _f, old, new in changed)
    removed = sum(len(set(old) - set(new)) for _f, old, new in changed)

    print("\n" + "-" * 50)
    if interrupted:
        print("Relabel Paused!")
    elif apply:
        print("Relabel Complete!")
    else:
        print("Relabel (dry run) — nothing written")
    print(f"  Matched on the server: {matched}")
    print(f"  {'Changed' if apply else 'Would change'}: {len(changed)} emails")
    if added:
        print(f"    Labels added: {added}")
    if removed:
        print(f"    Labels removed: {removed}")
    if unmatched:
        print(f"  Not found on the server: {unmatched} (left untouched)")

    for filename, old, new in changed[:10]:
        print(f"\n    {filename}")
        print(f"      before: {', '.join(old) or '(none)'}")
        print(f"      after:  {', '.join(new)}")
    if len(changed) > 10:
        print(f"\n    ... and {len(changed) - 10} more")

    if changed and not apply:
        print("\n  Re-run with --apply to write these changes.")
    print("-" * 50 + "\n")


def cmd_reconcile(
    archive: EmailArchive,
    apply: bool = False,
    verbose: bool = False,
) -> None:
    """Sweep the archive for mail the current download filter would reject.

    The filter only ever governed what came *in*. Anything already archived
    under an older filter — before role-based exclusion could recognize a
    trash folder, or before the operator narrowed ``exclude_roles`` — stays
    put until something goes looking for it. This is that something, and it is
    a standing capability rather than a migration because the filter is
    user-editable and will move again. See ``ownmail/reconcile.py``.

    Opt-in and separate from ``verify`` by design: verify reports the same
    mail (phase 3) and stops there, so no health check can move a message as a
    side effect. Nothing moves here either without ``apply``.

    Args:
        archive: EmailArchive instance
        apply: Move the swept messages to ownmail's bin (default: report only)
        verbose: List the affected message ids rather than just counts
    """
    print("\n" + "=" * 50)
    print("ownmail - Reconcile")
    print("=" * 50 + "\n")

    plan = reconcile.build_plan(archive.db.db_path, archive.config)

    if not plan.filters:
        print("No sources configured — reconcile compares the archive against")
        print("each source's download filter, so there is nothing to compare to.")
        return

    print("Download filter, per source:\n")
    for source_filter in plan.filters:
        print(f"  {source_filter.name} ({source_filter.account}): {source_filter.describe()}")

    if plan.unconfigured:
        total = sum(count for _, count in plan.unconfigured)
        print(f"\n  Skipped {total} archived emails belonging to no configured source:")
        for account, count in plan.unconfigured:
            print(f"      {account}: {count}")

    print(f"\n{'Moving' if apply else 'Would move'} to ownmail's bin: {len(plan.sweep)} emails")
    for label, account, count in reconcile.counts_by_label(plan.sweep):
        print(f"      {label} ({account}): {count}")
    if verbose:
        for candidate in plan.sweep:
            print(f"        {candidate.email_id}  {', '.join(candidate.rejected)}")

    if plan.reported:
        print(f"\nReported only — filed elsewhere too: {len(plan.reported)} emails")
        for label, account, count in reconcile.counts_by_label(plan.reported):
            print(f"      {label} ({account}): {count}")
        print("\n  These carry a real label alongside the rejected one, so the")
        print("  archive holds them for a reason the filter doesn't see. Left alone.")
        if verbose:
            for candidate in plan.reported:
                print(f"        {candidate.email_id}  {', '.join(candidate.rejected)} + {', '.join(candidate.kept)}")

    print("\n" + "-" * 50)
    if not plan.sweep:
        print("Nothing to move — the archive matches the current filter.")
        print("-" * 50 + "\n")
        return

    if not apply:
        print("Dry run — nothing moved.")
        print("  Re-run with --apply to move them to ownmail's bin, where they")
        print("  stay on disk and restorable until you empty it.")
        print("-" * 50 + "\n")
        return

    moved, missing = _move_to_bin(archive, plan.sweep)
    print(f"Moved to the bin: {moved} emails")
    if missing:
        print(f"  Not found: {missing} (already moved or deleted)")
    print("\n  Review them in the web UI's Trash, and restore anything that")
    print("  should have stayed. Emptying the bin is what makes it permanent.")
    print("-" * 50 + "\n")


def _move_to_bin(archive: EmailArchive, candidates: list) -> tuple[int, int]:
    """Move swept messages to ownmail's bin, one at a time.

    Each move is independent and self-contained, so an interrupt costs at most
    the message in flight and re-running picks up where it stopped — messages
    already in the bin aren't candidates any more.

    Returns:
        (moved, missing) counts
    """
    moved = 0
    missing = 0
    interrupted = False

    def signal_handler(signum, frame):
        nonlocal interrupted
        if interrupted:
            print("\n\nForce quit.")
            sys.exit(1)
        interrupted = True
        print("\n\n⏸ Stopping after current email... (Ctrl-C again to force quit)")

    original_handler = signal.signal(signal.SIGINT, signal_handler)
    try:
        for candidate in candidates:
            if interrupted:
                break
            if archive.trash_email(candidate.email_id):
                moved += 1
            else:
                missing += 1
            if moved % 500 == 0:
                print(f"  Moved {moved}...\033[K", end="\r", flush=True)
    finally:
        signal.signal(signal.SIGINT, original_handler)

    return moved, missing


def _print_file_list(files: list, label: str, verbose: bool, max_show: int = 5) -> None:
    """Helper to print a list of files with truncation unless verbose."""
    if not files:
        return
    print(f"  {label}: {len(files)}")
    show_count = len(files) if verbose else min(len(files), max_show)
    for f in files[:show_count]:
        print(f"      {f}")
    if not verbose and len(files) > max_show:
        print(f"      ... and {len(files) - max_show} more (use --verbose to show all)")


def cmd_list_unknown(
    archive: EmailArchive,
    verbose: bool = False,
) -> None:
    """List emails in the unknown/ folder (emails with unparseable dates).

    These emails couldn't have their date extracted during backup, so they
    were placed in the unknown/ folder. Use this command to identify them
    for manual inspection or reprocessing.

    Args:
        archive: EmailArchive instance
        verbose: Show full file paths and additional details
    """
    print("\n" + "=" * 50)
    print("ownmail - Unknown Emails")
    print("=" * 50 + "\n")

    db_path = archive.db.db_path

    with sqlite3.connect(db_path) as conn:
        results = conn.execute(
            """
            SELECT email_id, filename, account
            FROM emails
            WHERE email_date IS NULL
            ORDER BY account, filename
            """
        ).fetchall()

    if not results:
        print("✓ No emails with unparseable dates")
        return

    print(f"Found {len(results)} emails with unparseable dates:\n")

    # Group by account
    by_account = {}
    for email_id, filename, account in results:
        account = account or "(legacy)"
        if account not in by_account:
            by_account[account] = []
        by_account[account].append((email_id, filename))

    for account, emails in sorted(by_account.items()):
        print(f"  {account}: {len(emails)} emails")
        if verbose:
            for _email_id, filename in emails:
                print(f"    - {filename}")
                # Try to extract date from email file
                filepath = archive.archive_dir / filename
                if filepath.exists():
                    try:
                        import email

                        with open(filepath, "rb") as f:
                            msg = email.message_from_binary_file(f)
                        date_header = msg.get("Date", "")
                        subject = msg.get("Subject", "")[:50]
                        print(f"      Date header: {date_header}")
                        print(f"      Subject: {subject}...")
                    except Exception as e:
                        print(f"      Error reading: {e}")
        print()

    print("-" * 50)
    print("These emails have unparseable Date headers.")
    print("They are excluded from search results by default.")
    print("To include them, use: search --include-unknown")
    print("-" * 50 + "\n")


def cmd_import(
    archive: EmailArchive,
    path: Path,
    account: str | None = None,
    move: bool = False,
    dry_run: bool = False,
) -> None:
    """Import external .eml file(s) into the archive.

    Args:
        archive: EmailArchive instance
        path: File or directory of .eml files to import
        account: Associate all imported emails with this account
            (default: From header of each email)
        move: Delete source files after a successful import (default: copy)
        dry_run: Show what would be imported without doing it
    """
    print("\n" + "=" * 50)
    print("ownmail - Import")
    print("=" * 50 + "\n")

    if not path.exists():
        print(f"❌ Error: Path not found: {path}")
        sys.exit(1)

    archive.import_path(path, account=account, move=move, dry_run=dry_run)


def cmd_scan(
    archive: EmailArchive,
    account: str | None = None,
    dry_run: bool = False,
) -> None:
    """Register .eml files present in the archive dir but untracked in the DB.

    Args:
        archive: EmailArchive instance
        account: Associate registered emails with this account
            (default: From header of each email)
        dry_run: Show what would be registered without doing it
    """
    print("\n" + "=" * 50)
    print("ownmail - Scan")
    print("=" * 50 + "\n")

    archive.scan_archive(account=account, dry_run=dry_run)
