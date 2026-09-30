"""Export owned archive bytes without changing mail or replacing an output file."""

import mailbox
import os
import shutil
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from ownmail.active_search import archive_links
from ownmail.query import parse_query


def export_mbox(archive, output: Path, query: str = "") -> tuple[int, list[tuple[str, str]]]:
    """Write matching owned messages to a new mbox; return count and skipped files.

    Selection retains ordinary archive search's Trash and unknown-date exclusions.
    Source read failures skip that message; caught output errors or Ctrl-C leave
    no new output, so the same command can be restarted without appending duplicates.
    """
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
    rows = archive.db.search(
        query, limit=-1, sort="date_asc", _active_ids=active_ids, _with_order=True, _raise_fts_errors=True
    )
    root = archive.archive_dir.resolve()
    exported = 0
    skipped = []
    with TemporaryDirectory(prefix=".ownmail-export-", dir=output.parent) as directory:
        temporary = Path(directory) / "messages.mbox"
        with closing(mailbox.mbox(temporary)) as box:
            for email_id, filename, *_ in rows:
                try:
                    source = (root / filename).resolve(strict=True)
                    if not source.is_relative_to(root) or not source.is_file():
                        raise OSError("Message file is outside the archive or is not a regular file")
                    raw = source.read_bytes()
                except (OSError, RuntimeError) as error:
                    skipped.append((email_id, str(error)))
                    continue
                # Bytes avoid reserializing headers, MIME parts and attachments.
                # mailbox handles envelope lines and escapes body lines starting From.
                box.add(raw)
                exported += 1

        # Exclusive creation also catches a destination appearing during export.
        # Copying the completed mailbox works on filesystems without hard links.
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
    return exported, skipped
