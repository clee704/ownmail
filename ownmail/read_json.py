"""Decode one selected local message using the existing read-only archive view."""

import json
from pathlib import Path

from ownmail.parser import EmailParser
from ownmail.search_json import message_status
from ownmail.search_readonly import SearchUnavailable

DEFAULT_BODY_LIMIT = 20000
MAX_BODY_LIMIT = 100000


class MessageParseError(Exception):
    """The local message could not be parsed for reading."""


def validate_body_limit(limit: int) -> None:
    """Bound returned text in Unicode characters before opening local data."""
    if type(limit) is not int or not 1 <= limit <= MAX_BODY_LIMIT:
        raise ValueError(f"body limit must be an integer from 1 to {MAX_BODY_LIMIT}")


def read_message_json(archive, message_id: str, *, body_limit: int = DEFAULT_BODY_LIMIT) -> str:
    """Return decoded content, exact filename boundaries and an original file URI.

    The caller owns the TASK111 acquisition context and its final consistency
    check; emit this result only after that context has closed successfully.
    """
    validate_body_limit(body_limit)
    row = archive.get_readable_email(message_id)
    if row is None:
        raise LookupError("Message ID was not found in the local archive or Active cache")
    if message_id.startswith("active-"):
        path = Path(row[1])
        raw = archive.active_cache().read(message_id)
    else:
        root = archive.archive_dir.resolve()
        try:
            path = (root / row[1]).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                raise SearchUnavailable("Message file is outside the archive or is not a regular file")
            raw = path.read_bytes()
        except RuntimeError as error:
            raise SearchUnavailable("Message file is unavailable") from error
    try:
        parsed = EmailParser.parse_file(content=raw, for_reading=True)
    except Exception as error:
        raise MessageParseError("Message content could not be parsed") from error
    body = parsed["body"]
    return json.dumps(
        {
            "id": message_id,
            "sender": parsed["sender"],
            "subject": parsed["subject"],
            "recipients": parsed["recipients"],
            "date": parsed["date_str"],
            "body": body[:body_limit],
            "body_limit": body_limit,
            "truncated": len(body) > body_limit,
            "attachment_names": parsed["attachment_names"],
            **message_status(message_id, archive.active_info(message_id)),
            "original": {"uri": path.resolve().as_uri(), "media_type": "message/rfc822"},
        },
        ensure_ascii=False,
    )
