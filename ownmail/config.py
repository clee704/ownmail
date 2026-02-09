"""Configuration loading and validation."""

from pathlib import Path
from typing import Any, Dict, List, Optional

# Optional YAML support
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

DEFAULT_CONFIG_FILENAME = "config.yaml"


def load_config(config_path: Optional[Path] = None, script_dir: Path = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Search order:
    1. Explicit --config path
    2. ./config.yaml (current working directory)
    3. Script directory config.yaml

    Args:
        config_path: Explicit path to config file
        script_dir: Script directory for fallback search

    Returns:
        Configuration dictionary (empty if no config found)
    """
    search_paths = []

    if config_path:
        search_paths.append(config_path)
    else:
        # Check current working directory first
        search_paths.append(Path.cwd() / DEFAULT_CONFIG_FILENAME)
        # Then script directory
        if script_dir:
            search_paths.append(script_dir / DEFAULT_CONFIG_FILENAME)

    for path in search_paths:
        if path.exists():
            if not HAS_YAML:
                print(f"Found config file {path} but PyYAML is not installed.")
                print("Install with: pip install pyyaml")
                print("Continuing without config file...\n")
                return {}

            with open(path) as f:
                config = yaml.safe_load(f) or {}
                print(f"Loaded config from: {path}")
                return config

    return {}


def get_archive_root(config: Dict[str, Any], default: Path = None) -> Path:
    """Get archive root directory from config.

    Args:
        config: Configuration dictionary
        default: Default if not specified in config

    Returns:
        Archive root directory path
    """
    # Support both new "archive_root" and legacy "archive_dir"
    if "archive_root" in config:
        return Path(config["archive_root"])
    if "archive_dir" in config:
        return Path(config["archive_dir"])
    return default or Path.cwd() / "archive"


def get_sources(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get list of source configurations.

    Args:
        config: Full configuration dictionary

    Returns:
        List of source configuration dictionaries
    """
    return config.get("sources", [])


def get_source_by_name(config: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """Get a specific source by name.

    Args:
        config: Full configuration dictionary
        name: Source name (e.g., 'gmail_personal')

    Returns:
        Source configuration, or None if not found
    """
    for source in get_sources(config):
        if source.get("name") == name:
            return source
    return None


def get_source_by_account(config: Dict[str, Any], account: str) -> Optional[Dict[str, Any]]:
    """Get a specific source by account email.

    Args:
        config: Full configuration dictionary
        account: Email address

    Returns:
        Source configuration, or None if not found
    """
    for source in get_sources(config):
        if source.get("account") == account:
            return source
    return None


def parse_secret_ref(secret_ref: str) -> Dict[str, str]:
    """Parse a secret reference string.

    Formats:
        keychain:<key_name>  -> {"type": "keychain", "key": "<key_name>"}

    Args:
        secret_ref: Secret reference string (e.g., "keychain:gmail_personal_token")

    Returns:
        Dictionary with type and key
    """
    if ":" not in secret_ref:
        raise ValueError(f"Invalid secret_ref format: {secret_ref}")

    ref_type, ref_key = secret_ref.split(":", 1)

    if ref_type == "keychain":
        return {"type": "keychain", "key": ref_key}
    else:
        raise ValueError(f"Unsupported secret_ref type: {ref_type}")


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Validate configuration and return list of errors.

    Args:
        config: Configuration dictionary

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Validate sources
    sources = get_sources(config)
    seen_names = set()

    for i, source in enumerate(sources):
        # Required fields
        if "name" not in source:
            errors.append(f"Source {i+1}: missing 'name' field")
            continue

        name = source["name"]
        if name in seen_names:
            errors.append(f"Duplicate source name: {name}")
        seen_names.add(name)

        if "type" not in source:
            errors.append(f"Source '{name}': missing 'type' field")

        source_type = source.get("type", "")
        if source_type not in ("gmail_api", "imap"):
            errors.append(f"Source '{name}': unknown type '{source_type}'")

        if "account" not in source:
            errors.append(f"Source '{name}': missing 'account' field")

        # Auth validation
        auth = source.get("auth", {})
        if "secret_ref" not in auth:
            errors.append(f"Source '{name}': missing 'auth.secret_ref'")
        else:
            try:
                parse_secret_ref(auth["secret_ref"])
            except ValueError as e:
                errors.append(f"Source '{name}': {e}")

        # IMAP requires host
        if source_type == "imap":
            if "host" not in source:
                errors.append(f"Source '{name}': IMAP requires 'host' field")

    return errors

