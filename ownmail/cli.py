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


def cmd_setup(keychain: KeychainStorage, source_name: str = None, credentials_file: Optional[Path] = None) -> None:
    """Set up OAuth credentials for a source."""
    print("\n" + "=" * 50)
    print("ownmail - Setup")
    print("=" * 50 + "\n")

    # Determine keychain key name
    if source_name:
        keychain_key = f"{source_name}_token"
    else:
        keychain_key = "default_gmail_token"
        print("Tip: Use --source <name> to set up a specific source from config.yaml")
        print()

    if credentials_file:
        # Import from file
        if not credentials_file.exists():
            print(f"❌ Error: File not found: {credentials_file}")
            sys.exit(1)

        with open(credentials_file) as f:
            credentials_json = f.read()

        keychain.save_client_credentials("gmail", credentials_json)
        print("✓ OAuth credentials imported from file")
        print(f"\n  You can now delete: {credentials_file}")
    else:
        # Interactive paste
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

        print("\n✓ OAuth credentials saved to system keychain")

    print(f"\nKeychain key: {keychain_key}")
    print("\nAdd this to your config.yaml:")
    print(f"""
sources:
  - name: {source_name or 'gmail_personal'}
    type: gmail_api
    account: your@gmail.com
    auth:
      secret_ref: keychain:{keychain_key}
""")
    print("Then run 'ownmail backup' to start backing up your emails.")


def cmd_backup(archive: EmailArchive, config: dict, source_name: Optional[str] = None) -> None:
    """Run backup for one or all sources."""
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
            provider = GmailProvider(
                account=account,
                keychain=keychain,
                include_labels=source.get("include_labels", True),
            )

            # Authenticate
            provider.authenticate()

            # Get stats before backup
            stats = archive.db.get_stats(account)
            print(f"Archive location: {archive.archive_dir}")
            print(f"Previously backed up: {stats['total_emails']} emails")

            # Run backup
            result = archive.backup(provider)

            # Print summary
            total = stats["total_emails"] + result["success_count"]
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
            print(f"  Total archived: {total} emails")
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
    subparsers.add_parser(
        "backup",
        help="Download new emails",
        description="Download new emails and index them for search.",
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

    # Determine archive_root
    if args.archive_root:
        archive_root = args.archive_root
    else:
        archive_root = get_archive_root(config, DEFAULT_ARCHIVE_DIR)

    try:
        if args.command == "setup":
            keychain = KeychainStorage()
            cmd_setup(keychain, args.source, args.credentials_file)

        elif args.command == "sources":
            if args.sources_cmd == "list":
                cmd_sources_list(config)
            else:
                sources_parser.print_help()

        else:
            archive = EmailArchive(archive_root, config)

            if args.command == "backup":
                cmd_backup(archive, config, args.source)
            elif args.command == "search":
                cmd_search(archive, args.query, args.source, args.limit)
            elif args.command == "stats":
                cmd_stats(archive, config, args.source)

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise  # For debugging during development
        # sys.exit(1)


if __name__ == "__main__":
    main()
