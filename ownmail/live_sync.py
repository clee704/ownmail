"""Refresh server-owned mail and capture completed copies without replacing owned files."""

import email
import hashlib
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone

from ownmail import sidecar
from ownmail.active_search import capture_id, owned_match
from ownmail.database import ArchiveDatabase
from ownmail.live import LiveSnapshot


def capture_provenance(archive, path, raw, metadata):
    """Validate durable capture identity before rebuilding its derived index."""
    capture = metadata.get("capture") if metadata else None
    if capture is None and not re.fullmatch(r"capture-[0-9a-f]{24}_[0-9a-f]{16}\.eml", path.name):
        return None
    if not isinstance(capture, dict) or any(
        not isinstance(capture.get(field), str) or not capture[field]
        for field in ("source_name", "account", "provider_id", "identity", "content_hash")
    ):
        raise ValueError("Capture metadata is incomplete")
    root = archive.archive_dir.resolve()
    source_root = archive.get_emails_dir(capture["source_name"]).resolve()
    if (
        not source_root.is_relative_to(root)
        or not path.resolve().is_relative_to(source_root)
        or capture["content_hash"] != hashlib.sha256(raw).hexdigest()
        or capture.get("labels_complete") is not True
        or not isinstance(metadata.get("labels"), list)
        or any(not isinstance(label, str) or not label for label in metadata["labels"])
    ):
        raise ValueError("Capture metadata does not match this owned file")
    captured_at = metadata.get("captured_at")
    if not isinstance(captured_at, str):
        raise ValueError("Capture time is unavailable")
    date = datetime.fromisoformat(captured_at)
    if date.tzinfo is None:
        raise ValueError("Capture time must include its timezone")
    provider_id = capture_id(capture["source_name"], capture["account"], capture["identity"])
    if path.name != f"capture-{provider_id[5:29]}_{capture['content_hash'][:16]}.eml":
        raise ValueError("Capture identity does not match its filename")
    return provider_id, capture["account"], captured_at


def _entry(provider, message) -> dict:
    return {
        "source_name": provider.source_name,
        "account": provider.account,
        "provider_id": message.message_id,
        "identity": message.identity_token,
        "content_hash": hashlib.sha256(message.raw).hexdigest(),
    }


def _capture(archive, provider, message) -> bool:
    """Save complete file metadata before creating a rebuildable index record."""
    entry = _entry(provider, message)
    if owned_match(archive, entry):
        return False
    provider_id = capture_id(provider.source_name, provider.account, message.identity_token)
    email_id = ArchiveDatabase.make_email_id(provider.account, provider_id)
    if archive.db.get_email_by_id(email_id):
        # Missing or changed owned content needs operator repair, never replacement.
        raise ValueError("An owned copy already exists but could not be verified")
    parsed_message = email.message_from_bytes(message.raw)
    date = archive._parse_email_datetime(parsed_message)
    source = archive.get_emails_dir(provider.source_name)
    directory = source / (date.strftime("%Y/%m") if date else "unknown")
    if not directory.resolve().is_relative_to(archive.archive_dir.resolve()):
        raise ValueError("Capture source must stay within the archive")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"capture-{provider_id[5:29]}_{entry['content_hash'][:16]}.eml"
    if not path.exists():
        fd, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(message.raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path)
        finally:
            os.unlink(temporary)
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["content_hash"]:
        raise ValueError("Existing capture file does not match the observed message")
    metadata_path = sidecar.sidecar_path(path)
    if metadata_path.is_symlink():
        raise ValueError("Capture metadata must be a regular file")
    if metadata_path.exists():
        metadata = sidecar.read_metadata(path)
        if (
            metadata_path.is_symlink()
            or not metadata
            or metadata.get("capture") != {**entry, "labels_complete": True}
            or not isinstance(metadata.get("labels"), list)
        ):
            raise ValueError("Existing capture metadata could not be verified")
    else:
        metadata = {
            "version": sidecar.SIDECAR_VERSION,
            "labels": list(message.labels),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "capture": {**entry, "labels_complete": True},
        }
        sidecar.write_metadata(path, metadata)
    _, _, captured_at = capture_provenance(archive, path, message.raw, metadata)
    with sqlite3.connect(archive.db.db_path) as conn:
        outcome = archive._register_and_index(
            path, message.raw, provider_id, provider.account, conn, fallback_date=captured_at
        )
    return outcome == "imported"


def _within_dates(archive, raw, since, until) -> bool:
    if not since and not until:
        return True
    date = archive._parse_email_datetime(email.message_from_bytes(raw))
    if date is None:
        return False
    day = date.strftime("%Y-%m-%d")
    return (not since or day >= since) and (not until or day < until)


def _known_owned(archive, provider, message) -> bool:
    """Avoid refetching finished contents already owned under a stable identity."""
    provider_id = capture_id(provider.source_name, provider.account, message.identity_token)
    with sqlite3.connect(archive.db.db_path) as conn:
        hashes = conn.execute(
            "SELECT content_hash FROM emails WHERE account = ? AND provider_id IN (?, ?)",
            (provider.account, provider_id, message.message_id),
        ).fetchall()
    return any(
        owned_match(
            archive,
            {
                "source_name": provider.source_name,
                "account": provider.account,
                "provider_id": message.message_id,
                "identity": message.identity_token,
                "content_hash": value[0],
            },
        )
        for value in hashes
    )


def sync_live(archive, provider, *, active_downloads=True, since=None, until=None, progress=None) -> dict:
    """Refresh one source; only confirmed observations may remove cached copies."""
    cache = archive.active_cache(create=True)
    result = {
        "success_count": 0,
        "error_count": 0,
        "interrupted": False,
        "failed_ids": [],
        "active_refreshed": 0,
        "active_complete": False,
    }
    checked_at = datetime.now(timezone.utc).isoformat()
    cache.set_source_status(
        provider.source_name, provider.account, complete=False, error="Refresh in progress", checked_at=checked_at
    )
    if progress:
        progress.set_phase("refreshing", provider.source_name)
    previous = {entry["identity"]: entry for entry in cache.list_entries(provider.source_name, provider.account)}
    reasons = []
    removals = set()

    def failure(message_id, error):
        result["error_count"] += 1
        result["failed_ids"].append(message_id)
        reasons.append("Some server messages could not be refreshed or captured")
        print(f"Could not refresh or capture {message_id}; it remains retryable.")
        if progress:
            if isinstance(error, (sqlite3.Error, OSError)):
                progress.fail_exception(error, context="archive", errors=1)
            else:
                progress.fail("active_refresh", errors=1)

    try:
        snapshot = provider.list_live_messages()
        if not isinstance(snapshot, LiveSnapshot) or (snapshot.source_name, snapshot.account) != (
            provider.source_name,
            provider.account,
        ):
            raise ValueError("Provider cannot establish a scoped live view")
        if not snapshot.complete:
            reasons.append(snapshot.reason or "Server listing was incomplete")
        observed = set()
        for listed in snapshot.messages:
            observed.add(listed.identity_token)
            if not listed.download_allowed:
                reasons.append("Some folders are excluded from downloads")
                continue
            if not active_downloads and listed.state in {"active", "unknown"}:
                continue
            if (
                listed.state == "eligible"
                and listed.identity_token not in previous
                and _known_owned(archive, provider, listed)
            ):
                if progress:
                    progress.advance(skipped=1)
                continue
            try:
                message = provider.read_live_message(listed.message_id)
                if message is None:
                    if listed.identity_token in previous:
                        removals.add(previous[listed.identity_token]["id"])
                    if progress:
                        progress.advance(skipped=1)
                    continue
                if message.identity_token != listed.identity_token:
                    raise ValueError("Server identity changed during refresh")
                prior = previous.get(message.identity_token)
                if message.state == "discarded":
                    if prior:
                        removals.add(prior["id"])
                    continue
                if message.raw is None or not isinstance(message.raw, bytes):
                    raise ValueError("Message content is unavailable")
                if message.state == "eligible" and _within_dates(archive, message.raw, since, until):
                    captured = _capture(archive, provider, message)
                    result["success_count"] += int(captured)
                    if progress:
                        progress.advance(downloaded=int(captured), skipped=int(not captured))
                    if prior:
                        removals.add(prior["id"])
                elif active_downloads and message.state in {"active", "unknown", "eligible"}:
                    cache.put(
                        source_name=provider.source_name,
                        account=provider.account,
                        provider_id=message.message_id,
                        identity=message.identity_token,
                        roles=list(message.roles),
                        labels=list(message.labels),
                        raw=message.raw,
                        state="unknown" if message.state == "eligible" else message.state,
                        checked_at=checked_at,
                    )
                    result["active_refreshed"] += 1
                    if message.state == "unknown":
                        reasons.append(message.reason or "Some message states are unconfirmed")
                    if progress:
                        progress.advance(active_refreshed=1)
            except Exception as error:
                failure(listed.message_id, error)
        # Listing omission alone is insufficient evidence of deletion or a folder move.
        if snapshot.complete:
            for identity, entry in previous.items():
                if identity in observed:
                    continue
                try:
                    message = provider.read_live_message(entry["provider_id"])
                    if message is None or (message.identity_token == identity and message.state == "discarded"):
                        removals.add(entry["id"])
                    else:
                        reasons.append("A cached message was absent from the server listing")
                except Exception as error:
                    failure(entry["provider_id"], error)
        if snapshot.complete and not result["error_count"]:
            for cache_id in removals:
                cache.remove(cache_id)
    except KeyboardInterrupt:
        result["interrupted"] = True
        reasons.append("Refresh interrupted; completed saves are retained")
        if progress:
            progress.fail("interrupted")
    except Exception as error:
        failure("source", error)
    if not active_downloads:
        reasons.append("Active downloads are disabled for this source")
    if since or until:
        reasons.append("Date-filtered capture; some messages may remain unarchived")
    result["active_complete"] = not reasons
    reason = "; ".join(dict.fromkeys(reasons)) or None
    cache.set_source_status(
        provider.source_name, provider.account, complete=result["active_complete"], error=reason, checked_at=checked_at
    )
    if progress:
        progress.set_active_complete(result["active_complete"])
    print(
        f"Archived: {result['success_count']}; Active refreshed: {result['active_refreshed']}; "
        f"Active refresh {'complete' if result['active_complete'] else 'incomplete'}."
    )
    return result
