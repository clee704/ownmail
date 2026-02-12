"""Command-line interface for ownmail."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ownmail import __version__
from ownmail.archive import EmailArchive
from ownmail.config import (
    get_archive_root,
    get_source_by_name,
    get_sources,
    load_config,
    parse_secret_ref,
    validate_config,
)
from ownmail.keychain import KeychainStorage
from ownmail.providers.gmail import GmailProvider

# Default locations
SCRIPT_DIR = Path(__file__).parent.absolute()
DEFAULT_ARCHIVE_DIR = SCRIPT_DIR.parent / "archive"

# Template for new config.yaml with commented options
_CONFIG_TEMPLATE = """\
# ownmail configuration
# See README.md for all options.

{archive_root}
# Store the database separately from the archive (optional).
# Useful when archiving to a slow/external drive but wanting fast search.
# db_dir: /path/to/fast/local/storage

sources:
{sources}

# Web UI settings (used by 'ownmail serve')
# web:
#   port: 8080              # Default: 8080
#   page_size: 50            # Emails per search page (default: 50)
#   block_images: true       # Block external images by default (default: true)
#   trusted_senders:         # Always load images from these senders
#     - sender@example.com
"""


def cmd_setup(
    keychain: KeychainStorage,
    config: dict,
    config_path: Optional[Path],
    source_name: str = None,
    method: Optional[str] = None,
) -> None:
    """Set up email source credentials.

    Supports two methods:
    - imap (default): App Password via IMAP. Simple setup, works with Gmail and others.
    - oauth: Gmail API with OAuth. More complex setup, but scoped to read-only.
    """
    print("\n" + "=" * 50)
    print("ownmail - Setup")
    print("=" * 50 + "\n")

    # If --method not specified, ask user
    if not method:
        print("Choose a setup method:\n")
        print("  [1] IMAP with App Password (recommended)")
        print("      Works with Gmail, Outlook, Fastmail, and any IMAP server.")
        print("      For Gmail: generate an App Password in your Google Account.")
        print()
        print("  [2] Gmail API with OAuth")
        print("      Faster (batch downloads), read-only scope, native Gmail labels.")
        print("      Requires creating a Google Cloud project (~15 min one-time setup).")
        print()

        choice = input("Your choice [1]: ").strip()
        if choice == "2":
            method = "oauth"
        else:
            method = "imap"

    if method == "imap":
        _setup_imap(keychain, config, config_path, source_name)
    else:
        _setup_oauth(keychain, config, config_path, source_name)


def _update_or_create_config(
    config: dict,
    config_path: Optional[Path],
    source_name: str,
    source_snippet: str,
) -> None:
    """Update existing config or create a new one with the source.

    Args:
        config: Current loaded config dict
        config_path: Path to existing config file, or None
        source_name: Name of the source being added
        source_snippet: YAML snippet for the source (indented, starts with '  - name:')
    """
    from ownmail.yaml_util import load_yaml, save_yaml

    existing_source = get_source_by_name(config, source_name)

    if existing_source:
        print(f"\n✓ Source '{source_name}' already exists in config.")
        return

    if config_path and config_path.exists():
        # Load config with ruamel.yaml to preserve formatting/comments
        data = load_yaml(config_path)
        if "sources" not in data:
            data["sources"] = []

        # Parse the source snippet into a dict
        from io import StringIO
        parsed = load_yaml(StringIO(f"sources:\n{source_snippet}"))
        new_source = parsed["sources"][0]

        data["sources"].append(new_source)

        print(f"\n  Adding source to {config_path}...")
        save_yaml(data, config_path)
        print(f"✓ Added source '{source_name}' to {config_path}")
    else:
        # Create new config file — ask for archive root
        default_archive = Path.cwd() / "archive"
        archive_input = input(
            f"\nWhere to store emails [{default_archive}]: "
        ).strip()
        if archive_input:
            archive_path = Path(archive_input).resolve()
        else:
            archive_path = default_archive.resolve()

        archive_root_line = f"archive_root: {archive_path}"

        new_path = config_path or (Path.cwd() / "config.yaml")
        content = _CONFIG_TEMPLATE.format(
            archive_root=archive_root_line,
            sources=source_snippet,
        )
        new_path.write_text(content)
        print(f"\n✓ Created {new_path}")


def _setup_imap(
    keychain: KeychainStorage,
    config: dict,
    config_path: Optional[Path],
    source_name: str = None,
) -> None:
    """Set up IMAP with App Password."""
    print("─" * 50)
    print("IMAP Setup")
    print("─" * 50 + "\n")

    # Get email address
    account_email = input("Email address: ").strip()
    if not account_email:
        print("❌ Error: Email address required")
        sys.exit(1)

    # Detect Gmail
    is_gmail = account_email.endswith("@gmail.com") or account_email.endswith("@googlemail.com")

    if is_gmail:
        host = "imap.gmail.com"
        print(f"\n  Detected Gmail — using {host}")
        print()
        print("  To create a Gmail App Password:")
        print("  1. Go to https://myaccount.google.com/apppasswords")
        print("     (2-Step Verification must be enabled first)")
        print("  2. Enter a name (e.g., 'ownmail') and click Create")
        print("  3. Copy the 16-character password shown")
        print()
        print("  If you see 'The setting you are looking for is not available':")
        print("  → Enable 2-Step Verification first, then try again")
        print("  → For Google Workspace accounts, your admin may have disabled")
        print("    App Passwords — use 'ownmail setup --method oauth' instead")
        print()
    else:
        host = input("IMAP server hostname: ").strip()
        if not host:
            print("❌ Error: IMAP hostname required")
            sys.exit(1)
        print()

    # Get password
    import getpass

    password = getpass.getpass("App Password (hidden): ").strip()
    if not password:
        print("❌ Error: Password required")
        sys.exit(1)

    # Test connection
    print("\nTesting connection...", end="", flush=True)
    import imaplib

    try:
        conn = imaplib.IMAP4_SSL(host, 993)
        conn.login(account_email, password)
        conn.logout()
        print(" ✓ Connected successfully!")
    except imaplib.IMAP4.error as e:
        error_msg = str(e)
        print(" ✗ Failed!")
        if is_gmail:
            print("\n  Possible causes:")
            print("  • App Password is incorrect (check for typos, remove spaces)")
            print("  • 2-Step Verification is not enabled")
            print("  • IMAP is disabled in Gmail settings (Settings → See all settings → Forwarding and POP/IMAP)")
        else:
            print(f"\n  Error: {error_msg}")
        sys.exit(1)
    except Exception as e:
        print(f" ✗ Failed: {e}")
        sys.exit(1)

    # Save password to keychain
    keychain.save_imap_password(account_email, password)
    print(f"✓ Password saved to system keychain for {account_email}")

    # Get source name
    if not source_name:
        default_name = account_email
        source_name = input(f"\nSource name [{default_name}]: ").strip() or default_name

    # Generate config snippet
    source_snippet = f"""\
  - name: {source_name}
    type: imap
    host: {host}
    account: {account_email}
    auth:
      secret_ref: keychain:imap-password/{account_email}
"""

    _update_or_create_config(config, config_path, source_name, source_snippet)

    print("\n✓ Setup complete!")
    print(f"  Run 'ownmail download --source {source_name}' to start downloading.")


def _setup_oauth(
    keychain: KeychainStorage,
    config: dict,
    config_path: Optional[Path],
    source_name: str = None,
) -> None:
    """Set up Gmail API with OAuth (advanced)."""
    print("─" * 50)
    print("Gmail API + OAuth Setup")
    print("─" * 50 + "\n")

    print("This method uses the Gmail API with OAuth, which provides:")
    print("  • Read-only scope (narrower than App Password)")
    print("  • Faster batch downloads via Gmail API")
    print("  • Native Gmail labels (not just folder mapping)")
    print()
    print("Requirements:")
    print("  1. A Google Cloud project with the Gmail API enabled")
    print("  2. OAuth 2.0 desktop credentials (JSON file)")
    print()
    print("Steps to create credentials:")
    print("  1. Go to https://console.cloud.google.com/")
    print("  2. Create a new project (or select existing)")
    print("  3. APIs & Services → Library → search 'Gmail API' → Enable")
    print("  4. APIs & Services → Credentials → Create Credentials → OAuth client ID")
    print("  5. Application type: Desktop app → Create")
    print("  6. Download the JSON file")
    print()

    # Check if client credentials already exist
    has_client_creds = keychain.has_client_credentials("gmail")

    if not has_client_creds:
        # Ask user how to provide credentials
        try:
            file_path = input("Path to credentials JSON file (or press Enter to paste): ").strip()
        except EOFError:
            print("\n❌ Error: No input received")
            sys.exit(1)

        if file_path:
            creds_path = Path(file_path)
            if not creds_path.exists():
                print(f"❌ Error: File not found: {creds_path}")
                sys.exit(1)

            with open(creds_path) as f:
                credentials_json = f.read()

            print(f"  You can now delete: {creds_path}")
        else:
            print("\nPaste your OAuth client credentials JSON below.")
            print("(The JSON from step 6 above)")
            print("\nPaste the entire JSON content, then press Enter twice:\n")

            lines = []
            empty_count = 0
            while empty_count < 2:
                try:
                    line = input()
                    if line == "":
                        empty_count += 1
                    else:
                        empty_count = 0
                        lines.append(line)
                except EOFError:
                    break

            if not lines:
                print("❌ Error: No input received")
                sys.exit(1)

            credentials_json = "\n".join(lines)

        try:
            keychain.save_client_credentials("gmail", credentials_json)
        except ValueError as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

        print("✓ OAuth client credentials saved to keychain")
        print()

    # Now set up an account
    print("Add a Gmail account to download:\n")

    account_email = input("Gmail address: ").strip()
    if not account_email:
        print("❌ Error: Email address required")
        sys.exit(1)

    if not source_name:
        default_name = account_email
        source_name = input(f"Source name [{default_name}]: ").strip() or default_name

    token_key = f"oauth-token/{account_email}"

    existing_token = keychain.load_gmail_token(account_email)
    if existing_token:
        print(f"\n✓ OAuth token already exists for {account_email}")
    else:
        print(f"\nAuthenticating {account_email}...")
        print("A browser window will open for you to authorize access.\n")

        from ownmail.providers.gmail import GmailProvider

        provider = GmailProvider(account=account_email, keychain=keychain)
        provider.authenticate()

    source_snippet = f"""\
  - name: {source_name}
    type: gmail_api
    account: {account_email}
    auth:
      secret_ref: keychain:{token_key}
    include_labels: true
"""

    _update_or_create_config(config, config_path, source_name, source_snippet)

    print("\n✓ Setup complete!")
    print(f"  Run 'ownmail download --source {source_name}' to start downloading.")


def cmd_download(
    archive: EmailArchive,
    config: dict,
    source_name: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    verbose: bool = False,
) -> None:
    """Run download for one or all sources.

    Args:
        archive: EmailArchive instance
        config: Configuration dictionary
        source_name: Specific source to download (None = all)
        since: Only download emails after this date (YYYY-MM-DD)
        until: Only download emails before this date (YYYY-MM-DD)
        verbose: Show detailed progress output
    """
    print("\n" + "=" * 50)
    print("ownmail - Download")
    print("=" * 50 + "\n")

    sources = get_sources(config)
    keychain = archive.keychain

    if not sources:
        # No sources configured - use legacy single-account mode
        print("No sources configured in config.yaml.")
        print("Run 'ownmail setup' first, then add sources to config.yaml")
        sys.exit(1)

    # Filter to specific source if requested
    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Error: Source '{source_name}' not found in config")
            sys.exit(1)
        sources = [source]


    for source in sources:
        name = source["name"]
        source_type = source["type"]
        account = source["account"]

        print(f"Source: {name} ({account})")

        if source_type == "gmail_api":
            # Parse auth
            auth = source.get("auth", {})
            secret_ref = auth.get("secret_ref", "")

            if not secret_ref:
                print(f"❌ Error: Source '{name}' missing auth.secret_ref")
                continue

            try:
                parse_secret_ref(secret_ref)  # Validate format
            except ValueError as e:
                print(f"❌ Error: {e}")
                continue

            # Create provider
            if verbose:
                print("[verbose] Creating Gmail provider...", flush=True)
            provider = GmailProvider(
                account=account,
                keychain=keychain,
                include_labels=source.get("include_labels", True),
                source_name=name,
            )

            # Authenticate
            if verbose:
                print("[verbose] Authenticating...", flush=True)
            provider.authenticate()

            # Get email count (fast query)
            if verbose:
                print("[verbose] Getting email count...", flush=True)
            email_count = archive.db.get_email_count(account)
            print(f"Archive location: {archive.archive_dir}", flush=True)
            print(f"Previously downloaded: {email_count:,} emails", flush=True)

            # Show date filter if specified
            if since or until:
                date_range = []
                if since:
                    date_range.append(f"from {since}")
                if until:
                    date_range.append(f"until {until}")
                print(f"Date filter: {' '.join(date_range)}", flush=True)

            # Run download
            if verbose:
                print("[verbose] Starting download...", flush=True)
            result = archive.backup(provider, since=since, until=until, verbose=verbose)

            # Print summary
            total = email_count + result["success_count"]
            print("\n" + "-" * 50)
            if result["interrupted"]:
                print("Download Paused!")
                print(f"  Downloaded: {result['success_count']} emails")
                print("\n  Run 'download' again to resume.")
            else:
                print("Download Complete!")
                print(f"  Downloaded: {result['success_count']} emails")
            if result["error_count"] > 0:
                print(f"  Errors: {result['error_count']}")
            print(f"  Total archived: {total:,} emails")
            print("-" * 50 + "\n")

        elif source_type == "imap":
            from ownmail.providers.imap import ImapProvider

            host = source.get("host", "imap.gmail.com")
            port = source.get("port", 993)
            exclude_folders = source.get("exclude_folders")

            provider = ImapProvider(
                account=account,
                keychain=keychain,
                host=host,
                port=port,
                exclude_folders=exclude_folders,
                source_name=name,
            )

            provider.authenticate()

            email_count = archive.db.get_email_count(account)
            print(f"Archive location: {archive.archive_dir}", flush=True)
            print(f"Previously downloaded: {email_count:,} emails", flush=True)

            if since or until:
                date_range = []
                if since:
                    date_range.append(f"from {since}")
                if until:
                    date_range.append(f"until {until}")
                print(f"Date filter: {' '.join(date_range)}", flush=True)

            result = archive.backup(provider, since=since, until=until, verbose=verbose)

            total = email_count + result["success_count"]
            print("\n" + "-" * 50)
            if result["interrupted"]:
                print("Download Paused!")
                print(f"  Downloaded: {result['success_count']} emails")
                print("\n  Run 'download' again to resume.")
            else:
                print("Download Complete!")
                print(f"  Downloaded: {result['success_count']} emails")
            if result["error_count"] > 0:
                print(f"  Errors: {result['error_count']}")
            print(f"  Total archived: {total:,} emails")
            print("-" * 50 + "\n")

            # Close IMAP connection
            provider.close()

        else:
            print(f"  Unknown source type: {source_type}")
            continue


def cmd_search(archive: EmailArchive, query: str, limit: int = 50) -> None:
    """Search archived emails."""
    print(f"\nSearching for: {query}\n")

    results = archive.search(query, limit=limit)

    if not results:
        print("No results found.")
        return

    print(f"Found {len(results)} results:\n")

    for _msg_id, filename, subject, sender, date_str, snippet in results:
        print(f"  {date_str}")
        print(f"  From: {sender}")
        print(f"  Subject: {subject}")
        print(f"  {snippet}")
        print(f"  File: {filename}")
        print()


def cmd_stats(archive: EmailArchive, config: dict, source_name: Optional[str] = None) -> None:
    """Show archive statistics."""
    print("\n" + "=" * 50)
    print("ownmail - Statistics")
    print("=" * 50 + "\n")

    print(f"Archive location: {archive.archive_dir}")

    # Show per-source stats
    sources = get_sources(config)
    if sources:
        for source in sources:
            name = source["name"]
            account = source["account"]
            stats = archive.db.get_stats(account)
            print(f"\n{name} ({account}):")
            print(f"  Total emails: {stats['total_emails']}")
            if stats["oldest_backup"]:
                print(f"  Oldest backup: {stats['oldest_backup']}")
            if stats["newest_backup"]:
                print(f"  Newest backup: {stats['newest_backup']}")
    else:
        stats = archive.db.get_stats()
        print(f"Total emails: {stats['total_emails']}")
        print(f"Indexed for search: {stats['indexed_emails']}")


def cmd_sources_list(config: dict) -> None:
    """List configured sources."""
    sources = get_sources(config)

    if not sources:
        print("\nNo sources configured.")
        print("Run 'ownmail setup' and add sources to config.yaml")
        return

    print("\nConfigured sources:")
    for source in sources:
        name = source.get("name", "(unnamed)")
        source_type = source.get("type", "?")
        account = source.get("account", "?")
        print(f"  - {name}: {source_type} ({account})")


def cmd_reset_sync(
    archive: EmailArchive,
    config: dict,
    source_name: Optional[str] = None
) -> None:
    """Reset sync state to force a full re-sync.

    Args:
        archive: EmailArchive instance
        config: Configuration dictionary
        source_name: Specific source to reset (None = all)
    """
    print("\n" + "=" * 50)
    print("ownmail - Reset Sync State")
    print("=" * 50 + "\n")

    sources = get_sources(config)

    if source_name:
        source = get_source_by_name(config, source_name)
        if not source:
            print(f"❌ Error: Source '{source_name}' not found in config")
            sys.exit(1)
        sources = [source]

    if not sources:
        print("No sources configured.")
        return

    for source in sources:
        account = source["account"]
        source_type = source.get("type", "gmail_api")
        sync_key = "sync_state" if source_type == "imap" else "history_id"
        archive.db.delete_sync_state(account, sync_key)
        print(f"✓ Reset sync state for {account}")

    print("Next download will do a full sync (checking all messages).")
    print("Already downloaded emails will be skipped.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="ownmail",
        description="ownmail - Own your mail. Download and search your emails locally.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Version: {__version__}

Examples:
  %(prog)s setup                           First-time credential setup
  %(prog)s download                        Download new emails
  %(prog)s download --source gmail_personal  Download specific source
  %(prog)s search "invoice from:amazon"   Search emails
  %(prog)s stats                           Show statistics
  %(prog)s sources list                    List configured sources
        """,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file (default: ./config.yaml)",
    )

    parser.add_argument(
        "--archive-root",
        type=Path,
        dest="archive_root",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed progress output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Helper: add global options to a subparser so they work in any position
    def _add_global_opts(sub):
        sub.add_argument("-v", "--verbose", action="store_true", help=argparse.SUPPRESS)

    # setup command
    setup_parser = subparsers.add_parser(
        "setup",
        help="Set up email source credentials",
        description="Set up credentials for downloading emails. Supports IMAP with App Passwords (recommended) or Gmail API with OAuth.",
    )
    setup_parser.add_argument(
        "--method",
        choices=["imap", "oauth"],
        help="Setup method: 'imap' (App Password, default) or 'oauth' (Gmail API)",
    )
    _add_global_opts(setup_parser)

    # download command
    download_parser = subparsers.add_parser(
        "download",
        help="Download new emails",
        description="Download new emails and index them for search.",
    )
    download_parser.add_argument("--source", type=str, help="Source name to operate on (default: all sources)")
    download_parser.add_argument(
        "--since",
        type=str,
        help="Only download emails after this date (YYYY-MM-DD)",
    )
    download_parser.add_argument(
        "--until",
        type=str,
        help="Only download emails before this date (YYYY-MM-DD)",
    )
    _add_global_opts(download_parser)

    # search command
    search_parser = subparsers.add_parser(
        "search",
        help="Search archived emails",
        description="Full-text search across all downloaded emails.",
    )
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=50, help="Maximum results")
    _add_global_opts(search_parser)

    # stats command
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show archive statistics",
    )
    stats_parser.add_argument("--source", type=str, help="Source name to show stats for (default: all sources)")
    _add_global_opts(stats_parser)

    # rebuild command
    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Rebuild the search index and populate metadata",
        description="Rebuild the full-text search index from email files.",
    )
    rebuild_parser.add_argument("--file", type=Path, help="Index only this specific .eml file")
    rebuild_parser.add_argument("--pattern", type=str, help="Index only files whose path matches this pattern (e.g., '2024/09/*')")
    rebuild_parser.add_argument("--force", "-f", action="store_true", help="Rebuild all, even if indexed")
    rebuild_parser.add_argument("--debug", action="store_true", help="Show timing debug info")
    rebuild_parser.add_argument("--index-only", action="store_true", help="Only rebuild the search index (skip date population)")
    rebuild_parser.add_argument("--date-only", action="store_true", help="Only populate email dates (skip indexing)")
    _add_global_opts(rebuild_parser)

    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify archive integrity (files, hashes, database)",
        description="Check file integrity, detect orphans, and validate database health.",
    )
    verify_parser.add_argument("--fix", action="store_true", help="Fix issues (remove stale DB entries, rebuild FTS)")
    _add_global_opts(verify_parser)

    # sync-check command
    sync_check_parser = subparsers.add_parser(
        "sync-check",
        help="Compare local archive with server to find missing emails",
        description="Compare your local archive with what's on the server. Shows emails that exist on the server but haven't been downloaded yet, and local emails that were deleted from the server.",
    )
    sync_check_parser.add_argument("--source", type=str, help="Source name to check (default: all sources)")
    _add_global_opts(sync_check_parser)

    # reset-sync command
    reset_sync_parser = subparsers.add_parser(
        "reset-sync",
        help="Reset sync state to force full re-download",
        description="Clear the sync state for all sources, forcing the next download to do a full sync.",
    )
    reset_sync_parser.add_argument("--source", type=str, help="Source name to reset (default: all sources)")
    _add_global_opts(reset_sync_parser)

    # update-labels command
    update_labels_parser = subparsers.add_parser(
        "update-labels",
        help="Fetch current labels from server for existing emails",
        description="Fetch current Gmail labels from the server and update the database for already-downloaded emails.",
    )
    update_labels_parser.add_argument("--source", type=str, help="Source name to update (default: all sources)")
    _add_global_opts(update_labels_parser)

    # list-unknown command
    unknown_parser = subparsers.add_parser(
        "list-unknown",
        help="List emails with unparseable dates",
        description="Show emails that couldn't have their date extracted.",
    )
    _add_global_opts(unknown_parser)

    # serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start web interface",
        description="Start a local web server to browse and search emails.",
    )
    serve_parser.add_argument("--archive-dir", type=Path, help=argparse.SUPPRESS)
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    serve_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    serve_parser.add_argument("--block-images", action="store_true", help=argparse.SUPPRESS)
    _add_global_opts(serve_parser)

    # sources command
    sources_parser = subparsers.add_parser(
        "sources",
        help="Manage email sources",
    )
    sources_sub = sources_parser.add_subparsers(dest="sources_cmd")
    sources_sub.add_parser("list", help="List configured sources")
    _add_global_opts(sources_parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    config = load_config(args.config, SCRIPT_DIR)

    # Validate config (skip for setup, which may create it)
    if args.command != "setup":
        errors = validate_config(config)
        if errors:
            print("❌ Configuration errors:")
            for error in errors:
                print(f"   - {error}")
            sys.exit(1)

    # Determine config file path for potential updates
    config_path = args.config
    if not config_path:
        # Check default locations
        cwd_config = Path.cwd() / "config.yaml"
        if cwd_config.exists():
            config_path = cwd_config

    # Determine archive_root
    if args.archive_root:
        archive_root = args.archive_root
    else:
        archive_root = get_archive_root(config, DEFAULT_ARCHIVE_DIR)

    try:
        if args.command == "setup":
            keychain = KeychainStorage()
            cmd_setup(keychain, config, config_path, method=getattr(args, 'method', None))

        elif args.command == "sources":
            if args.sources_cmd == "list":
                cmd_sources_list(config)
            else:
                sources_parser.print_help()

        else:
            archive = EmailArchive(archive_root, config)

            if args.command == "download":
                cmd_download(archive, config, args.source, args.since, args.until, args.verbose)
            elif args.command == "search":
                cmd_search(archive, args.query, limit=args.limit)
            elif args.command == "stats":
                cmd_stats(archive, config, args.source)
            elif args.command == "rebuild":
                from ownmail.commands import cmd_rebuild
                only = None
                if args.date_only:
                    only = "dates"
                elif args.index_only:
                    only = "index"
                cmd_rebuild(archive, args.file, args.pattern, args.force, args.debug, only)
            elif args.command == "verify":
                from ownmail.commands import cmd_verify
                cmd_verify(archive, args.fix, args.verbose)
            elif args.command == "sync-check":
                from ownmail.commands import cmd_sync_check
                cmd_sync_check(archive, args.source, args.verbose)
            elif args.command == "reset-sync":
                cmd_reset_sync(archive, config, args.source)
            elif args.command == "update-labels":
                from ownmail.commands import cmd_update_labels
                cmd_update_labels(archive, args.source)
            elif args.command == "list-unknown":
                from ownmail.commands import cmd_list_unknown
                cmd_list_unknown(archive, args.verbose)
            elif args.command == "serve":
                try:
                    from ownmail.web import run_server
                except ImportError:
                    print("❌ Flask is required for the web interface.")
                    print("   Install with: pip install ownmail[web]")
                    sys.exit(1)
                # serve can use its own archive-dir or fall back to global
                serve_archive_root = args.archive_dir if args.archive_dir else archive_root
                serve_archive = EmailArchive(serve_archive_root, config)
                # Get web config from config.yaml, CLI args override
                web_config = config.get("web", {})
                block_images = args.block_images or web_config.get("block_images", True)
                page_size = web_config.get("page_size", 20)
                trusted_senders = web_config.get("trusted_senders", [])
                date_format = web_config.get("date_format")  # e.g., "%Y-%m-%d" or "%m/%d"
                detail_date_format = web_config.get("detail_date_format")
                auto_scale = web_config.get("auto_scale", True)
                brand_name = web_config.get("brand_name", "ownmail")
                display_timezone = web_config.get("timezone")
                run_server(
                    serve_archive,
                    args.host,
                    args.port,
                    args.debug,
                    args.verbose,
                    block_images,
                    page_size,
                    trusted_senders,
                    config_path,
                    date_format,
                    auto_scale,
                    brand_name,
                    display_timezone,
                    detail_date_format,
                )

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise  # For debugging during development
        # sys.exit(1)


if __name__ == "__main__":
    main()
