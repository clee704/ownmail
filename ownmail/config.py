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


def get_accounts(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get list of account configurations.

    Args:
        config: Full configuration dictionary

    Returns:
        List of account configuration dictionaries
    """
    return config.get("accounts", [])


def get_provider_defaults(config: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """Get default settings for a provider.

    Args:
        config: Full configuration dictionary
        provider: Provider name (e.g., 'gmail', 'imap')

    Returns:
        Provider default settings
    """
    providers = config.get("providers", {})
    return providers.get(provider, {})


def get_account_config(
    config: Dict[str, Any],
    account: str
) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific account.

    Merges provider defaults with account-specific overrides.

    Args:
        config: Full configuration dictionary
        account: Account email address

    Returns:
        Merged account configuration, or None if not found
    """
    for acct in get_accounts(config):
        if acct.get("address") == account:
            # Get provider defaults
            provider = acct.get("provider", "gmail")
            defaults = get_provider_defaults(config, provider)

            # Merge: account config overrides provider defaults
            merged = {**defaults, **acct}
            return merged

    return None


def get_archive_dir(config: Dict[str, Any], default: Path = None) -> Path:
    """Get archive directory from config.

    Args:
        config: Configuration dictionary
        default: Default if not specified in config

    Returns:
        Archive directory path
    """
    if "archive_dir" in config:
        return Path(config["archive_dir"])
    return default or Path.cwd() / "archive"


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Validate configuration and return list of errors.

    Args:
        config: Configuration dictionary

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Validate accounts
    accounts = get_accounts(config)
    seen_addresses = set()

    for i, acct in enumerate(accounts):
        if "address" not in acct:
            errors.append(f"Account {i+1}: missing 'address' field")
            continue

        address = acct["address"]
        if address in seen_addresses:
            errors.append(f"Duplicate account: {address}")
        seen_addresses.add(address)

        provider = acct.get("provider", "gmail")
        if provider not in ("gmail", "imap", "outlook"):
            errors.append(f"Account {address}: unknown provider '{provider}'")

        # IMAP requires server
        if provider == "imap":
            if "imap_server" not in acct:
                errors.append(f"Account {address}: IMAP requires 'imap_server'")

    return errors
