"""Pure JSON formatting for CLI search's existing rows and Active metadata.

Success has ``results`` and ``pagination``; errors have ``error.code`` and
``error.message``. Each result retains its stable ID, nullable indexed headers,
attachment flag, archive ownership and nullable Active freshness. File paths and
internal cache metadata are omitted. Active presence describes a cached server
copy; ``complete`` and ``reason`` retain the existing freshness qualification.

Pages default to the CLI's 50 rows and cap at the web UI's maximum of 500.
Offsets range from 0 to 2147483647, keeping pagination values safely bounded.
Snippets are at most 200 Unicode characters, including any truncation ellipsis.
The caller supplies the already-offset page plus one lookahead row, in existing
search order. No total count is implied. These functions perform no I/O; data
acquisition, stdout/stderr and exit status remain the command's responsibility.
"""

import json

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_OFFSET = 2**31 - 1
MAX_SNIPPET_LENGTH = 200


def validate_search_pagination(limit: int, offset: int) -> None:
    """Reject invalid page values before the caller acquires search data."""
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer from 1 to {MAX_LIMIT}")
    if type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
        raise ValueError(f"offset must be a nonnegative integer at most {MAX_OFFSET}")


def search_results_json(
    rows: list[tuple], active_infos: dict[str, dict], *, limit: int = DEFAULT_LIMIT, offset: int = 0
) -> str:
    """Serialize a page from EmailArchive.search and its matching active_infos.

    The existing seven-field tuple is (ID, filename, subject, sender, date,
    snippet, attachment flag). Missing Active metadata for a cached-only ID is
    an acquisition error, rather than evidence that the message is archived.
    """
    validate_search_pagination(limit, offset)
    results = []
    for message_id, _filename, subject, sender, date, snippet, attachments in rows[:limit]:
        info = active_infos.get(message_id)
        if info is None and message_id.startswith("active-"):
            raise ValueError("Active status is unavailable for a cached search result")
        snippet = snippet or ""
        if len(snippet) > MAX_SNIPPET_LENGTH:
            snippet = snippet[: MAX_SNIPPET_LENGTH - 1] + "…"
        results.append(
            {
                "id": message_id,
                "sender": sender,
                "subject": subject,
                "date": date,
                "snippet": snippet,
                "has_attachments": bool(attachments),
                "archived": bool(info["archived"]) if info is not None else True,
                "active": {
                    "complete": info["complete"],
                    "checked_at": info.get("checked_at"),
                    "content_at": info.get("content_at"),
                    "reason": info.get("reason"),
                    "refresh_error": info.get("refresh_error"),
                }
                if info is not None
                else None,
            }
        )
    has_more = len(rows) > limit
    return json.dumps(
        {
            "results": results,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": offset + limit if has_more else None,
            },
        },
        ensure_ascii=False,
    )


def search_error_json(code: str, message: str) -> str:
    """Serialize a defined command error without writing to either stream.

    Codes distinguish invalid_query, invalid_pagination, unavailable prerequisites
    and search_failed; the command maps these errors to nonzero exit status.
    """
    return json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False)
