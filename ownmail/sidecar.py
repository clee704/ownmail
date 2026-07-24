"""Per-email sidecar metadata files for labels/tags.

Each .eml file gets a JSON sidecar with the same basename (.json instead
of .eml), holding its labels/tags. The sidecar is the source of truth -
the database's email_labels table (and any future notmuch tag index) is
a derived, rebuildable cache. If the database is lost, labels can be
recovered by re-reading the sidecars; if a sidecar and the database
disagree, the sidecar wins.

Writes are atomic (temp file in the same directory + os.rename) so a
crash never leaves a partially-written sidecar.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

SIDECAR_VERSION = 1


def sidecar_path(eml_path: Path) -> Path:
    """Return the sidecar path for a given .eml file (same basename, .json)."""
    return eml_path.with_suffix(".json")


def read_labels(eml_path: Path) -> list[str] | None:
    """Read labels from an email's sidecar file.

    Returns:
        List of labels (may be empty) if a sidecar exists, or None if
        there is no sidecar for this email yet.
    """
    path = sidecar_path(eml_path)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    labels = data.get("labels", [])
    return [str(label) for label in labels]


def write_labels(eml_path: Path, labels: list[str]) -> None:
    """Atomically write labels to an email's sidecar file.

    Args:
        eml_path: Path to the .eml file (sidecar is derived from this)
        labels: Labels/tags to store (order preserved, duplicates removed)
    """
    path = sidecar_path(eml_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Dedup while preserving order
    seen = set()
    deduped = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            deduped.append(label)

    data = {"version": SIDECAR_VERSION, "labels": deduped}

    fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.rename(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
