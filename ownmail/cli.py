"""Command-line interface for ownmail."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ownmail import __version__
from ownmail.archive import EmailArchive
from ownmail.config import get_archive_root, get_source_by_name, get_sources, load_config, parse_secret_ref
from ownmail.keychain import KeychainStorage
from ownmail.providers.gmail import GmailProvider

# Default locations
SCRIPT_DIR = Path(__file__).parent.absolute()
DEFAULT_ARCHIVE_DIR = SCRIPT_DIR.parent / "archive"


def cmd_setup(
    keychain: KeychainStorage,
    config: dict,
    config_path: Optional[Path],
    source_name: str = None,
    credentials_file: Optional[Path] = None,
) -> None:
    """Set up OAuth credentials for a source."""
    print("\n" + "=" * 50)
    print("ownmail - Setup")
    print("=" * 50 + "\n")

    # Check if client credentials already exist
    has_client_creds = keychain.has_client_credentials("gmail")

    if not has_client_creds:
        # First time setup - need client credentials
        print("First-time setup: OAuth client credentials needed.\n")

        if credentials_file:
            if not credentials_file.exists():
                print(f"❌ Error: File not found: {credentials_file}")
                sys.exit(1)

            with open(credentials_file) as f:
                credentials_json = f.read()
        else:
            print("Paste your OAuth client credentials JSON below.")
            print("(The JSON from Google Cloud Console → Credentials → Download)")
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
        if credentials_file:
            print(f"  You can now delete: {credentials_file}")
        print()

    # Now set up an account
    print("Add a Gmail account to backup:\n")

    # Get email address first
    account_email = input("Gmail address: ").strip()
    if not account_email:
        print("❌ Error: Email address required")
        sys.exit(1)

    # Get source name (use email prefix as default)
    if not source_name:
        # Use part before @ as default name, replacing dots/plus with underscore
        email_prefix = account_email.split("@")[0]
        default_name = email_prefix.replace(".", "_").replace("+", "_")
        source_name = input(f"Source name [{default_name}]: ").strip() or default_name

    # The keychain key for this account's token
    token_key = f"oauth-token/{account_email}"

    # Check if token already exists
    existing_token = keychain.load_gmail_token(account_email)
    if existing_token:
        print(f"\n✓ OAuth token already exists for {account_email}")
    else:
        # Need to authenticate
        print(f"\nAuthenticating {account_email}...")
        print("A browser window will open for you to authorize access.\n")

        from ownmail.providers.gmail import GmailProvider

        provider = GmailProvider(account=account_email, keychain=keychain)
        provider.authenticate()

    # Generate config snippet
    config_snippet = f"""
  - name: {source_name}
    type: gmail_api
    account: {account_email}
    auth:
      secret_ref: keychain:{token_key}
    include_labels: true
"""

    # Check if we should update config file
    sources = get_sources(config)
    existing_source = get_source_by_name(config, source_name)

    if existing_source:
        print(f"\n✓ Source '{source_name}' already exists in config.")
        print("  No config changes needed.")
    else:
        print("\n" + "-" * 50)
        print("Add this to your config.yaml under 'sources:':")
        print(config_snippet)

        # Offer to append automatically
        if config_path and config_path.exists():
            add_to_config = input("Add to config.yaml automatically? [Y/n]: ").strip().lower()
            if add_to_config != "n":
                with open(config_path, "a") as f:
                    if not sources:
                        # No sources section yet
                        f.write("\nsources:\n")
                    f.write(config_snippet)
                print(f"✓ Added to {config_path}")

    print("\n✓ Setup complete!")
    print(f"  Run 'ownmail backup --source {source_name}' to start backing up.")


def cmd_backup(
    archive: EmailArchive,
    config: dict,
    source_name: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    verbose: bool = False,
) -> None:
    """Run backup for one or all sources.

    Args:
        archive: EmailArchive instance
        config: Configuration dictionary
        source_name: Specific source to backup (None = all)
        since: Only backup emails after this date (YYYY-MM-DD)
        until: Only backup emails before this date (YYYY-MM-DD)
        verbose: Show detailed progress output
    """
    print("\n" + "=" * 50)
    print("ownmail - Backup")
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
            print(f"Previously backed up: {email_count:,} emails", flush=True)

            # Show date filter if specified
            if since or until:
                date_range = []
                if since:
                    date_range.append(f"from {since}")
                if until:
                    date_range.append(f"until {until}")
                print(f"Date filter: {' '.join(date_range)}", flush=True)

            # Run backup
            if verbose:
                print("[verbose] Starting backup...", flush=True)
            result = archive.backup(provider, since=since, until=until, verbose=verbose)

            # Print summary
            total = email_count + result["success_count"]
            print("\n" + "-" * 50)
            if result["interrupted"]:
                print("Backup Paused!")
                print(f"  Downloaded: {result['success_count']} emails")
                print("\n  Run 'backup' again to resume.")
            else:
                print("Backup Complete!")
                print(f"  Downloaded: {result['success_count']} emails")
            if result["error_count"] > 0:
                print(f"  Errors: {result['error_count']}")
            print(f"  Total archived: {total:,} emails")
            print("-" * 50 + "\n")

        elif source_type == "imap":
            print("  IMAP support coming soon!")
            continue

        else:
            print(f"  Unknown source type: {source_type}")
            continue


def cmd_search(archive: EmailArchive, query: str, source_name: Optional[str] = None, limit: int = 50) -> None:
    """Search archived emails."""
    print(f"\nSearching for: {query}\n")

    # If source specified, get the account email for filtering
    account = None
    # TODO: filter by source name -> account

    results = archive.search(query, account=account, limit=limit)

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
        archive.db.delete_sync_state(account, "history_id")
        print(f"✓ Reset sync state for {account}")

    print("\nNext backup will do a full sync (checking all messages).")
    print("Already downloaded emails will be skipped.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="ownmail",
        description="ownmail - Own your mail. Backup and search your emails locally.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Version: {__version__}

Examples:
  %(prog)s setup                           First-time credential setup
  %(prog)s backup                          Download new emails
  %(prog)s backup --source gmail_personal  Backup specific source
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
        help="Directory to store emails and database",
    )

    parser.add_argument(
        "--source",
        type=str,
        help="Source name to operate on (default: all sources)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed progress output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup command
    setup_parser = subparsers.add_parser(
        "setup",
        help="Configure OAuth credentials",
        description="Set up Gmail API OAuth credentials for the first time.",
    )
    setup_parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Path to credentials JSON file",
    )

    # backup command
    backup_parser = subparsers.add_parser(
        "backup",
        help="Download new emails",
        description="Download new emails and index them for search.",
    )
    backup_parser.add_argument(
        "--since",
        type=str,
        help="Only backup emails after this date (YYYY-MM-DD)",
    )
    backup_parser.add_argument(
        "--until",
        type=str,
        help="Only backup emails before this date (YYYY-MM-DD)",
    )

    # search command
    search_parser = subparsers.add_parser(
        "search",
        help="Search archived emails",
        description="Full-text search across all downloaded emails.",
    )
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=50, help="Maximum results")

    # stats command
    subparsers.add_parser(
        "stats",
        help="Show archive statistics",
    )

    # reindex command
    reindex_parser = subparsers.add_parser(
        "reindex",
        help="Rebuild the search index",
        description="Rebuild the full-text search index from email files.",
    )
    reindex_parser.add_argument("--file", type=Path, help="Index only this specific .eml file")
    reindex_parser.add_argument("--pattern", type=str, help="Index only files matching pattern")
    reindex_parser.add_argument("--force", "-f", action="store_true", help="Reindex all, even if indexed")
    reindex_parser.add_argument("--debug", action="store_true", help="Show timing debug info")

    # verify command
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify integrity of downloaded emails",
        description="Verify that downloaded emails haven't been corrupted.",
    )
    verify_parser.add_argument("--verbose", "-v", action="store_true", help="Show full list of issues")

    # rehash command
    subparsers.add_parser(
        "rehash",
        help="Compute hashes for emails without them",
        description="Compute SHA256 content hashes for emails that don't have them.",
    )

    # sync-check command
    sync_check_parser = subparsers.add_parser(
        "sync-check",
        help="Compare local archive with server",
        description="Compare your local archive with what's on the server.",
    )
    sync_check_parser.add_argument("--verbose", "-v", action="store_true", help="Show full differences")

    # reset-sync command
    subparsers.add_parser(
        "reset-sync",
        help="Reset sync state to force full re-download",
        description="Clear the sync state for all sources, forcing the next backup to do a full sync.",
    )

    # db-check command
    db_check_parser = subparsers.add_parser(
        "db-check",
        help="Check database integrity",
        description="Check the database for integrity issues and optionally fix them.",
    )
    db_check_parser.add_argument("--fix", action="store_true", help="Fix fixable issues")
    db_check_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed issues")

    # add-labels command
    subparsers.add_parser(
        "add-labels",
        help="Add Gmail labels to existing emails",
        description="Fetch Gmail labels and add them to existing downloaded emails.",
    )

    # serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start web interface",
        description="Start a local web server to browse and search emails.",
    )
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    serve_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    # sources command
    sources_parser = subparsers.add_parser(
        "sources",
        help="Manage email sources",
    )
    sources_sub = sources_parser.add_subparsers(dest="sources_cmd")
    sources_sub.add_parser("list", help="List configured sources")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    config = load_config(args.config, SCRIPT_DIR)

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
            cmd_setup(keychain, config, config_path, args.source, args.credentials_file)

        elif args.command == "sources":
            if args.sources_cmd == "list":
                cmd_sources_list(config)
            else:
                sources_parser.print_help()

        else:
            archive = EmailArchive(archive_root, config)

            if args.command == "backup":
                cmd_backup(archive, config, args.source, args.since, args.until, args.verbose)
            elif args.command == "search":
                cmd_search(archive, args.query, args.source, args.limit)
            elif args.command == "stats":
                cmd_stats(archive, config, args.source)
            elif args.command == "reindex":
                from ownmail.commands import cmd_reindex
                cmd_reindex(archive, args.file, args.pattern, args.force, args.debug)
            elif args.command == "verify":
                from ownmail.commands import cmd_verify
                cmd_verify(archive, args.verbose)
            elif args.command == "rehash":
                from ownmail.commands import cmd_rehash
                cmd_rehash(archive)
            elif args.command == "sync-check":
                from ownmail.commands import cmd_sync_check
                cmd_sync_check(archive, args.source, args.verbose)
            elif args.command == "reset-sync":
                cmd_reset_sync(archive, config, args.source)
            elif args.command == "db-check":
                from ownmail.commands import cmd_db_check
                cmd_db_check(archive, args.fix, args.verbose)
            elif args.command == "add-labels":
                from ownmail.commands import cmd_add_labels
                cmd_add_labels(archive, args.source)
            elif args.command == "serve":
                try:
                    from ownmail.web import run_server
                except ImportError:
                    print("❌ Flask is required for the web interface.")
                    print("   Install with: pip install ownmail[web]")
                    sys.exit(1)
                run_server(archive, args.host, args.port, args.debug, args.verbose)

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise  # For debugging during development
        # sys.exit(1)


if __name__ == "__main__":
    main()
