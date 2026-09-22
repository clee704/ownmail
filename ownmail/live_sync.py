"""Refresh server-owned mail and capture completed copies without replacing owned files."""

import email
import hashlib
import os
import re
import sqlite3
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone

from ownmail import sidecar
from ownmail.active_search import OwnedLookup, capture_id, owned_match
from ownmail.database import ArchiveDatabase
from ownmail.live import LiveLookupError, LiveMessage, LiveSnapshot


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


def _capture(archive, provider, message, lookup) -> bool:
    """Save complete file metadata before creating a rebuildable index record."""
    entry = _entry(provider, message)
    if owned_match(archive, entry, lookup=lookup):
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
    lookup.add(email_id)
    return outcome == "imported"


def _within_dates(archive, raw, since, until) -> bool:
    if not since and not until:
        return True
    date = archive._parse_email_datetime(email.message_from_bytes(raw))
    if date is None:
        return False
    day = date.strftime("%Y-%m-%d")
    return (not since or day >= since) and (not until or day < until)


def _known_owned(archive, provider, message, lookup) -> bool:
    """Recognize verified owned copies without following later server changes."""
    return (
        owned_match(
            archive,
            {
                "source_name": provider.source_name,
                "account": provider.account,
                "provider_id": message.message_id,
                "identity": message.identity_token,
                "content_hash": None,
            },
            lookup=lookup,
        )
        is not None
    )


def _prune_owned_cache(archive, cache, entries, lookup):
    """Retire old live duplicates using local evidence, even when the server fails."""
    for identity, entry in list(entries.items()):
        if owned_match(archive, entry, lookup=lookup):
            cache.remove(entry["id"])
            del entries[identity]


def _batch_size(provider) -> int:
    size = getattr(provider, "live_batch_size", 1)
    return size if type(size) is int and 1 <= size <= 500 else 1


def _read_messages(provider, message_ids):
    """Yield bounded read results without losing successful earlier batches."""
    size = _batch_size(provider)
    reader = getattr(provider, "read_live_messages", None)
    for start in range(0, len(message_ids), size):
        batch = message_ids[start : start + size]
        if not callable(reader):
            for message_id in batch:
                try:
                    value = provider.read_live_message(message_id)
                except Exception as error:
                    value = error
                yield message_id, value
            continue
        try:
            results = reader(batch)
            if not isinstance(results, dict) or results.keys() - set(batch):
                raise LiveLookupError("Server returned an unscoped content batch")
        except Exception as error:
            results = dict.fromkeys(batch, error)
        for message_id in batch:
            value = results.get(message_id, LiveLookupError("Server omitted a content batch result"))
            if value is not None and not isinstance(value, (LiveMessage, Exception)):
                value = LiveLookupError("Server returned an invalid content batch result")
            yield message_id, value


def sync_live(archive, provider, *, since=None, until=None, progress=None) -> dict:
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
    from ownmail.config import active_scope_signature

    provider_type = "imap" if getattr(provider, "name", None) == "imap" else "gmail_api"
    scope_key = "_active_exclude_folders" if provider_type == "imap" else "_active_exclude_labels"
    exclusions = getattr(provider, scope_key, ())
    signature = active_scope_signature(
        provider_type, exclusions if isinstance(exclusions, (list, tuple, set, frozenset)) else ()
    )
    prior_status = cache.source_status(provider.source_name, provider.account)
    capture_signature = (
        prior_status.get("capture_scope_signature", prior_status.get("active_scope_signature"))
        if prior_status
        else signature
    )
    capture_state = (prior_status or {}).get("capture_state")
    checked_at = datetime.now(timezone.utc).isoformat()
    cache.set_source_status(
        provider.source_name,
        provider.account,
        complete=False,
        error="Refresh in progress",
        checked_at=checked_at,
        active_scope_signature=signature,
        capture_scope_signature=capture_signature,
        capture_state=capture_state,
    )
    previous = {entry["identity"]: entry for entry in cache.list_entries(provider.source_name, provider.account)}
    reasons = []
    capture_pending = False
    checked = 0
    last_report = time.monotonic()

    def scan_progress(count):
        nonlocal checked, last_report
        checked = count
        if progress:
            progress.set_scan_progress(count)
        now = time.monotonic()
        if now - last_report >= 1:
            print(f"  Scanning live mail: {checked} messages checked...", flush=True)
            last_report = now

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

    def refresh_messages(messages, lookup):
        pending = []

        def read_pending():
            for listed, (_, value) in zip(pending, _read_messages(provider, [item.message_id for item in pending])):
                yield listed, value
            if pending and progress:
                # Publish completed saves before the next network batch can block.
                progress.flush()
            pending.clear()

        for listed in messages:
            if _known_owned(archive, provider, listed, lookup):
                if progress:
                    progress.advance(skipped=1)
                continue
            if not listed.download_allowed:
                reasons.append("Some folders are excluded from downloads")
                continue
            if not listed.active_allowed and listed.state in {"active", "unknown"}:
                try:
                    defer_capture(listed)
                except Exception as error:
                    failure(listed.message_id, error)
                    continue
                if progress:
                    progress.advance(skipped=1)
                continue
            prior = previous.get(listed.identity_token)
            if (
                prior
                and listed.state in {"active", "unknown"}
                and isinstance(listed.content_revision, str)
                and listed.content_revision
                and listed.content_revision == prior.get("content_revision")
                and listed.message_id == prior["provider_id"]
            ):
                try:
                    raw = cache.read(prior["id"])
                except (OSError, ValueError):
                    pass  # A damaged disposable copy must be downloaded again.
                else:
                    yield listed, replace(listed, raw=raw)
                    continue
            pending.append(listed)
            if len(pending) >= _batch_size(provider):
                yield from read_pending()
        yield from read_pending()

    def defer_capture(message):
        nonlocal capture_pending
        can_defer = getattr(provider, "can_defer_live_message", None)
        if callable(can_defer) and can_defer(message, snapshot.sync_state) is True:
            prior = previous.get(message.identity_token)
            if prior:
                cache.update_scope(prior["id"], list(message.active_scope))
        else:
            # Retain the cursor unless provider state already guarantees rediscovery.
            capture_pending = True

    def process_message(listed, message, lookup):
        if isinstance(message, Exception):
            raise message
        if message is None:
            if listed.identity_token in previous:
                cache.remove(previous[listed.identity_token]["id"])
                del previous[listed.identity_token]
            if progress:
                progress.advance(skipped=1)
            return
        if message.identity_token != listed.identity_token or message.message_id != listed.message_id:
            raise ValueError("Server identity changed during refresh")
        prior = previous.get(message.identity_token)
        if message.state == "discarded":
            if prior:
                cache.remove(prior["id"])
                del previous[message.identity_token]
            return
        if not message.download_allowed:
            reasons.append("Some folders are excluded from downloads")
            return
        if not message.active_allowed and message.state in {"active", "unknown"}:
            defer_capture(message)
            return
        if message.raw is None or not isinstance(message.raw, bytes):
            raise ValueError("Message content is unavailable")
        if message.state == "eligible" and _within_dates(archive, message.raw, since, until):
            captured = _capture(archive, provider, message, lookup)
            result["success_count"] += int(captured)
            # Ownership ends Active tracking even if the rest of the refresh fails.
            if prior:
                cache.remove(prior["id"])
                del previous[message.identity_token]
            if progress:
                progress.advance(downloaded=int(captured), skipped=int(not captured))
        elif message.active_allowed and message.state in {"active", "unknown", "eligible"}:
            if owned_match(archive, _entry(provider, message), lookup=lookup):
                if prior:
                    cache.remove(prior["id"])
                    del previous[message.identity_token]
                if progress:
                    progress.advance(skipped=1)
                return
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
                content_revision=message.content_revision,
                active_scope=list(message.active_scope),
            )
            result["active_refreshed"] += 1
            if message.state == "unknown":
                reasons.append(message.reason or "Some message states are unconfirmed")
            if progress:
                progress.advance(active_refreshed=1)

    try:
        print("Scanning live mail before capture...", flush=True)
        if progress:
            progress.set_scan_progress(0)
            progress.set_phase("scanning", provider.source_name)
        lookup = OwnedLookup(archive, provider.account)
        _prune_owned_cache(archive, cache, previous, lookup)
        incremental = getattr(provider, "incremental_live", False) is True
        options = {}
        if incremental:
            options = {
                "incremental": True,
                "sync_state": (None if since or until or capture_signature != signature else capture_state),
                "is_owned": lambda message: _known_owned(archive, provider, message, lookup),
            }
        snapshot = provider.list_live_messages(on_progress=scan_progress, **options)
        if not isinstance(snapshot, LiveSnapshot) or (snapshot.source_name, snapshot.account) != (
            provider.source_name,
            provider.account,
        ):
            raise ValueError("Provider cannot establish a scoped live view")
        print(f"Live scan {'complete' if snapshot.complete else 'incomplete'}: {checked} messages checked.", flush=True)
        if progress:
            progress.set_phase("refreshing")
        if not snapshot.complete:
            reasons.append(snapshot.reason or "Server listing was incomplete")
        observed = {listed.identity_token for listed in snapshot.messages}
        for listed, message in refresh_messages(snapshot.messages, lookup):
            try:
                process_message(listed, message, lookup)
            except Exception as error:
                failure(listed.message_id, error)
        # A scoped lookup can confirm changes even when the listing was incomplete.
        in_scope = getattr(provider, "live_entry_in_scope", lambda entry: True)
        missing = {
            entry["provider_id"]: entry
            for identity, entry in previous.items()
            if identity not in observed and in_scope(entry)
        }
        for message_id, message in _read_messages(provider, list(missing)):
            entry = missing[message_id]
            try:
                listed = LiveMessage(message_id, identity_token=entry["identity"])
                process_message(listed, message, lookup)
                if (
                    isinstance(message, LiveMessage)
                    and entry["identity"] in previous
                    and message.active_allowed
                    and message.state in {"active", "unknown"}
                ):
                    reasons.append("A cached message was absent from the server listing")
            except Exception as error:
                failure(entry["provider_id"], error)
        if snapshot.complete and not result["error_count"]:
            if incremental and snapshot.sync_state and not capture_pending and not since and not until:
                capture_state = snapshot.sync_state
                capture_signature = signature
    except KeyboardInterrupt:
        result["interrupted"] = True
        reasons.append("Refresh interrupted; completed saves are retained")
        if progress:
            progress.fail("interrupted")
    except Exception as error:
        failure("source", error)
    if capture_pending:
        reasons.append("Unfinished capture candidates outside Active tracking will be checked again")
    if since or until:
        reasons.append("Date-filtered capture; some messages may remain unarchived")
    result["active_complete"] = not reasons
    reason = "; ".join(dict.fromkeys(reasons)) or None
    cache.set_source_status(
        provider.source_name,
        provider.account,
        complete=result["active_complete"],
        error=reason,
        checked_at=checked_at,
        active_scope_signature=signature,
        capture_scope_signature=capture_signature,
        capture_state=capture_state,
    )
    if progress:
        progress.set_active_complete(result["active_complete"])
    print(
        f"Archived: {result['success_count']}; Active refreshed: {result['active_refreshed']}; "
        f"Active refresh {'complete' if result['active_complete'] else 'incomplete'}."
    )
    return result
