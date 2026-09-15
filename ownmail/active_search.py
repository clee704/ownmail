"""Consolidate disposable live copies with independently owned messages."""

import hashlib
import sqlite3

from ownmail import sidecar
from ownmail.query import parse_query


def capture_id(source_name: str, account: str, identity: str) -> str:
    """Namespace new captures without changing the existing archive schema."""
    import json

    return "live:" + hashlib.sha256(json.dumps([source_name, account, identity]).encode()).hexdigest()


def owned_match(archive, entry: dict, *, include_trash: bool = True) -> tuple | None:
    """Match verified owned content by scoped identity or exact bytes."""
    source_root = archive.get_emails_dir(entry["source_name"]).resolve()
    archive_root = archive.archive_dir.resolve()
    if not source_root.is_relative_to(archive_root):
        return None
    with sqlite3.connect(archive.db.db_path) as conn:
        candidates = conn.execute(
            "SELECT email_id, filename, downloaded_at, content_hash, account, trashed_at, original_filename, provider_id "
            "FROM emails WHERE account = ? AND (content_hash = ? OR provider_id IN (?, ?))",
            (
                entry["account"],
                entry["content_hash"],
                capture_id(entry["source_name"], entry["account"], entry["identity"]),
                entry["provider_id"],
            ),
        ).fetchall()
    matches = []
    identity_matches = []
    for candidate in candidates:
        if candidate[5] and not include_trash:
            continue
        path = archive.archive_dir / candidate[1]
        try:
            resolved = path.resolve(strict=True)
            metadata = sidecar.read_metadata(path)
            provenance = metadata.get("capture", {}) if metadata else {}
            if not isinstance(provenance, dict):
                provenance = {}
            original_source = (archive.archive_dir / candidate[6]).resolve() if candidate[6] else None
            same_source = resolved.is_relative_to(source_root) or (
                candidate[5]
                and (
                    (original_source is not None and original_source.is_relative_to(source_root))
                    or (
                        provenance.get("source_name") == entry["source_name"]
                        and provenance.get("account") == entry["account"]
                    )
                )
            )
            if (
                not resolved.is_relative_to(archive_root)
                or not same_source
                or not resolved.is_file()
                or hashlib.sha256(resolved.read_bytes()).hexdigest() != candidate[3]
            ):
                continue
        except (OSError, RuntimeError):
            continue
        same_identity = (
            provenance.get("source_name") == entry["source_name"]
            and provenance.get("account") == entry["account"]
            and provenance.get("identity") == entry["identity"]
            and provenance.get("content_hash") == candidate[3]
        ) or (entry["identity"] == "gmail:" + entry["provider_id"] and candidate[7] == entry["provider_id"])
        if same_identity:
            identity_matches.append(candidate[:6])
        elif candidate[3] == entry["content_hash"]:
            matches.append(candidate[:6])
    preferred = identity_matches or matches
    return preferred[0] if len(preferred) == 1 else None


def archive_links(archive) -> dict[str, str]:
    """Map cached IDs to verified owned copies visible in ordinary results."""
    cache = archive.active_cache()
    if cache is None:
        return {}
    links = {}
    for entry in cache.list_entries():
        owned = owned_match(archive, entry, include_trash=False)
        if owned:
            links[entry["id"]] = owned[0]
    return links


def active_info(archive, email_id: str) -> dict | None:
    """Read freshness from the cache independently of the archive's labels."""
    return active_infos(archive).get(email_id)


def active_infos(archive) -> dict[str, dict]:
    """Build reading metadata once for a page of results."""
    cache = archive.active_cache()
    if cache is None:
        return {}
    links = archive_links(archive)
    result = {}
    for entry in cache.list_entries():
        try:
            status = cache.source_status(entry["source_name"], entry["account"]) or {}
        except (OSError, ValueError):
            status = {"complete": False, "error": "Refresh metadata is unavailable"}
        info = {
            "active": True,
            "cache_id": entry["id"],
            "archive_id": links.get(entry["id"]),
            "archived": entry["id"] in links,
            "source_name": entry["source_name"],
            "checked_at": entry["checked_at"],
            "content_at": entry["content_at"],
            "complete": status.get("complete", False),
            "reason": status.get("error") or ("Message state is unconfirmed" if entry["state"] == "unknown" else None),
        }
        result[entry["id"]] = info
        if info["archive_id"]:
            result[info["archive_id"]] = info
    return result


def search(archive, query: str, *, account=None, limit=50, offset=0, sort="relevance", tz=None, include_unknown=False):
    """Search both indexes, merge verified matches, then apply pagination."""
    cache = archive.active_cache()
    options = {"account": account, "limit": limit, "offset": offset, "sort": sort, "tz": tz}
    if include_unknown:
        options["include_unknown"] = True
    if cache is None:
        return archive.db.search(query, **options)
    parsed = parse_query(query, tz=tz)
    if parsed.has_error():
        return []
    links = archive_links(archive)
    options.update(limit=-1 if limit < 0 else max(0, offset) + limit + len(links), offset=0, _with_order=True)
    archived = archive.db.search(query, _active_ids=set(links.values()), **options)
    live = cache.db.search(query, _active_ids=None, _archived_ids=set(links), **options)
    rows = {row[0]: row for row in archived}
    with sqlite3.connect(archive.db.db_path) as conn:
        for row in live:
            archive_id = links.get(row[0])
            if archive_id:
                if archive_id in rows:
                    continue
                owned = conn.execute(
                    "SELECT email_id, filename, subject, sender, date_str, snippet, has_attachments "
                    "FROM emails WHERE email_id = ? AND trashed_at IS NULL",
                    (archive_id,),
                ).fetchone()
                if owned:
                    rows[archive_id] = (*owned, row[-1])
                    continue
            try:
                path = cache.path(row[0])
            except (OSError, ValueError):
                continue
            rows[row[0]] = (row[0], str(path), *row[2:])
    relevance = sort == "relevance" and parsed.has_fts()
    ordered = sorted(
        rows.values(),
        key=lambda row: (row[-1] or (0 if relevance else ""), row[0]),
        reverse=not relevance and sort != "date_asc",
    )
    end = None if limit < 0 else max(0, offset) + limit
    return [row[:-1] for row in ordered[max(0, offset) : end]]
