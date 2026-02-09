"""YAML utilities using ruamel.yaml for comment-preserving round-trip editing."""

from io import StringIO
from pathlib import Path
from typing import Any, Dict, Union

from ruamel.yaml import YAML


def _make_yaml() -> YAML:
    """Create a configured YAML instance for round-trip operations."""
    yml = YAML()
    yml.preserve_quotes = True
    return yml


def load_yaml(source: Union[str, Path, StringIO]) -> Dict[str, Any]:
    """Load YAML from a file path or string content.

    Args:
        source: File path (str or Path) or StringIO with YAML content

    Returns:
        Parsed dictionary (empty dict if content is empty/None)
    """
    yml = _make_yaml()
    if isinstance(source, StringIO):
        return yml.load(source) or {}
    path = Path(source)
    with open(path) as f:
        return yml.load(f) or {}


def save_yaml(data: Dict[str, Any], dest: Union[str, Path]) -> None:
    """Save data to a YAML file, preserving comments and formatting.

    Args:
        data: Dictionary to write (may be a ruamel CommentedMap for round-trip)
        dest: File path to write to
    """
    yml = _make_yaml()
    path = Path(dest)
    with open(path, "w") as f:
        yml.dump(data, f)
