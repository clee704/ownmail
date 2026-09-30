"""Export owned archive bytes without changing mail or replacing an output file."""

import mailbox
import os
import shutil
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from ownmail.active_search import archive_links
from ownmail.query import parse_query


def _export_rows(archive, output: Path, query: str):
    """Validate the destination and select every matching owned archive row."""
    parsed = parse_query(query)
    if parsed.has_error():
        raise ValueError(f"Invalid search: {parsed.error}")
    if os.path.lexists(output):
        raise FileExistsError(f"Output already exists: {output}")

    # Ownership filters can inspect existing verified links, never cached bodies.
    active_ids = set()
    # SQL literals such as has:attachment consume no parameter; markers do.
    parameter_clauses = (clause for clause in parsed.where_clauses if clause.startswith("__") or "?" in clause)
    if any(
        clause in {"__STATE__", "__NOT_STATE__"} and value == "active"
        for clause, value in zip(parameter_clauses, parsed.params)
    ):
        active_ids = set(archive_links(archive).values())
    return archive.db.search(
        query, limit=-1, sort="date_asc", _active_ids=active_ids, _with_order=True, _raise_fts_errors=True
    )


def _publish_file(temporary: Path, output: Path) -> None:
    """Copy a completed export exclusively; remove only our failed new file."""
    # Exclusive creation also catches a destination appearing during export.
    # Copying the completed artifact works on filesystems without hard links.
    created = False
    try:
        with output.open("xb") as destination:
            created = True
            with temporary.open("rb") as source:
                shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
    except BaseException:
        if created:
            output.unlink()
        raise


def _read_source(root: Path, filename: str) -> bytes:
    """Read one regular archived file, refusing paths outside the archive."""
    source = (root / filename).resolve(strict=True)
    if not source.is_relative_to(root) or not source.is_file():
        raise OSError("Message file is outside the archive or is not a regular file")
    return source.read_bytes()


def export_mbox(archive, output: Path, query: str = "") -> tuple[int, list[tuple[str, str]]]:
    """Write matching owned messages to a new mbox; return count and skipped files.

    Selection retains ordinary archive search's Trash and unknown-date exclusions.
    Source read failures skip that message; caught output errors or Ctrl-C leave
    no new output, so the same command can be restarted without appending duplicates.
    """
    rows = _export_rows(archive, output, query)
    root = archive.archive_dir.resolve()
    exported = 0
    skipped = []
    with TemporaryDirectory(prefix=".ownmail-export-", dir=output.parent) as directory:
        temporary = Path(directory) / "messages.mbox"
        with closing(mailbox.mbox(temporary)) as box:
            for email_id, filename, *_ in rows:
                try:
                    raw = _read_source(root, filename)
                except (OSError, RuntimeError) as error:
                    skipped.append((email_id, str(error)))
                    continue
                # Bytes avoid reserializing headers, MIME parts and attachments.
                # mailbox handles envelope lines and escapes body lines starting From.
                box.add(raw)
                exported += 1

        _publish_file(temporary, output)
    return exported, skipped
