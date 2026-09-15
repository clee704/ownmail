"""Preview or trash verified server copies without changing the owned archive."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ownmail import roles
from ownmail.cleanup_verify import CleanupHold, iter_candidate_ids, verify_local
from ownmail.live import LiveLookupError


def _remote_copy(provider, owned):
    """Require fresh message and thread observations in the verified account."""
    current = provider.read_live_message(owned.provider_id)
    if current is None:
        raise CleanupHold("Server copy is absent")
    if current.message_id != owned.provider_id or current.identity_token != owned.identity:
        raise CleanupHold("Server message identity does not match the owned copy")
    if current.state != "eligible" or current.roles.intersection({roles.INBOX, roles.DRAFTS, roles.TRASH, roles.SPAM}):
        raise CleanupHold("Server message is Active, discarded, or unconfirmed")
    if not isinstance(current.raw, bytes) or hashlib.sha256(current.raw).hexdigest() != owned.content_hash:
        raise CleanupHold("Server contents do not match the owned copy")
    if not isinstance(current.thread_id, str) or not current.thread_id:
        raise CleanupHold("Server thread identity is unavailable")

    started = datetime.now(timezone.utc)
    protection = provider.check_thread_protection(owned.provider_id)
    if (
        protection.source_name != owned.source_name
        or protection.account != owned.account
        or protection.message_id != owned.provider_id
        or protection.thread_id != current.thread_id
    ):
        raise CleanupHold("Thread observation does not match this source, account, and message")
    if not protection.allows_cleanup:
        raise CleanupHold(protection.reason or "Thread activity is present or unconfirmed")
    if (
        not isinstance(protection.checked_at, datetime)
        or protection.checked_at.tzinfo is None
        or protection.checked_at < started
        or protection.checked_at > datetime.now(timezone.utc)
    ):
        raise CleanupHold("Thread observation is stale or invalid")
    return current


def _same_owned_copy(first, current):
    # Local label edits remain authoritative and do not change message identity.
    return all(
        getattr(first, field) == getattr(current, field)
        for field in ("email_id", "filename", "source_name", "account", "provider_id", "identity", "content_hash")
    )


def run_cleanup(archive_root: Path, source: dict, provider, *, apply=False, report=None, db_path: Path | None = None):
    """Sweep owned records, using server state to resume without a writable journal.

    Every request stands alone. A retry rechecks the server and skips copies
    already in Trash; an uncertain response never authorizes a blind retry.
    """
    summary = {"checked": 0, "eligible": 0, "held": 0, "trashed": 0, "errors": 0, "interrupted": False}

    def emit(email_id, status, reason=None):
        if report:
            report(
                {
                    "email_id": email_id,
                    "status": status,
                    "reason": reason,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    try:
        candidates = iter(iter_candidate_ids(archive_root, source, db_path=db_path))
        while True:
            try:
                email_id = next(candidates)
            except StopIteration:
                break
            summary["checked"] += 1
            mutation_started = False
            stop = False
            try:
                if source.get("type") != "gmail_api":
                    raise CleanupHold("IMAP cleanup is held because complete thread visibility is unavailable")
                if provider.source_name != source["name"] or provider.account != source["account"]:
                    raise CleanupHold("Provider does not match the configured source and account")
                owned = verify_local(archive_root, source, email_id, db_path=db_path)
                try:
                    provider.verify_cleanup_account()
                except LiveLookupError:
                    stop = True
                    raise
                current = _remote_copy(provider, owned)
                final = verify_local(archive_root, source, email_id, db_path=db_path)
                if not _same_owned_copy(owned, final):
                    raise CleanupHold("Owned copy changed during verification")
                summary["eligible"] += 1
                status, reason = "eligible", None
                if apply:
                    mutation_started = True
                    result = provider.trash_message(owned.provider_id, current.thread_id)
                    if (
                        result.source_name != owned.source_name
                        or result.account != owned.account
                        or result.message_id != owned.provider_id
                        or result.thread_id != current.thread_id
                        or result.status not in {"trashed", "uncertain", "denied"}
                    ):
                        status, reason = "uncertain", "Trash response did not confirm the expected server copy"
                    else:
                        status, reason = result.status, result.reason
                    if status == "trashed":
                        summary["trashed"] += 1
                    else:
                        summary["errors"] += 1
                        stop = status == "denied"
            except CleanupHold as error:
                summary["held"] += 1
                status, reason = "held", str(error)
            except LiveLookupError:
                summary["errors"] += 1
                status, reason = "error", "Current server account or message state could not be verified"
            except KeyboardInterrupt:
                summary["interrupted"] = True
                summary["errors"] += 1
                status = "uncertain" if mutation_started else "error"
                reason = "Interrupted; retry will recheck the owned copy and current server state"
                stop = True
            except Exception:
                summary["errors"] += 1
                status = "uncertain" if mutation_started else "error"
                reason = "Cleanup request outcome is unconfirmed" if mutation_started else "Cleanup verification failed"
            emit(email_id, status, reason)
            if stop:
                break
    except KeyboardInterrupt:
        summary["interrupted"] = True
    except Exception:
        summary["errors"] += 1
        emit(None, "error", "Archived candidates could not be read; the index may need rebuilding")
    return summary
