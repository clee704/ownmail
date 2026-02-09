"""Command-line interface for ownmail."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ownmail import __version__
from ownmail.archive import EmailArchive
from ownmail.config import get_archive_dir, load_config
from ownmail.keychain import KeychainStorage
from ownmail.providers.gmail import GmailProvider

# Default locations
SCRIPT_DIR = Path(__file__).parent.absolute()
DEFAULT_ARCHIVE_DIR = SCRIPT_DIR.parent / "archive"


def cmd_setup(keychain: KeychainStorage, credentials_file: Optional[Path] = None) -> None:
    """Set up OAuth credentials."""
    print("\n" + "=" * 50)
    print("ownmail - Setup")
    print("=" * 50 + "\n")

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

    print("\nSetup complete! Run 'ownmail backup' to start backing up your emails.")


def cmd_backup(archive: EmailArchive, account: Optional[str] = None) -> None:
    """Run backup for one or all accounts."""
    print("\n" + "=" * 50)
    print("ownmail - Backup")
    print("=" * 50 + "\n")

    # For now, we support single Gmail account (v0.1 compatibility)
    # Multi-account will be added when config support is complete

    keychain = archive.keychain

    # Determine account email
    if not account:
        # Try to get from stored token
        # For v0.1 compatibility, check legacy token first
        legacy_token = keychain.load_legacy_token()
        if legacy_token:
            # We don't know the email from legacy token, prompt user
            print("Note: Migrating from single-account mode.")
            print("Please enter your Gmail address for this archive:")
            account = input("Email: ").strip()
            if not account:
                print("❌ Error: Email address required")
                sys.exit(1)
        else:
            print("❌ Error: No account configured. Run 'ownmail setup' first.")
            sys.exit(1)

    # Check for Gmail credentials
    client_creds = keychain.load_client_credentials("gmail")
    if not client_creds:
        # Try legacy location
        client_creds = keychain.load_legacy_client_credentials()
        if client_creds:
            # Migrate to new location
            keychain.save_client_credentials("gmail", client_creds)
        else:
            print("❌ Error: No OAuth credentials found. Run 'ownmail setup' first.")
            sys.exit(1)

    # Create provider
    provider = GmailProvider(
        account=account,
        keychain=keychain,
        include_labels=True,  # TODO: get from config
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


def cmd_search(archive: EmailArchive, query: str, account: Optional[str] = None, limit: int = 50) -> None:
    """Search archived emails."""
    print(f"\nSearching for: {query}\n")

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


def cmd_stats(archive: EmailArchive, account: Optional[str] = None) -> None:
    """Show archive statistics."""
    print("\n" + "=" * 50)
    print("ownmail - Statistics")
    print("=" * 50 + "\n")

    stats = archive.db.get_stats(account)

    print(f"Archive location: {archive.archive_dir}")
    print(f"Total emails: {stats['total_emails']}")
    print(f"Indexed for search: {stats['indexed_emails']}")

    if stats["oldest_backup"]:
        print(f"Oldest backup: {stats['oldest_backup']}")
    if stats["newest_backup"]:
        print(f"Newest backup: {stats['newest_backup']}")

    # Show per-account breakdown if multiple accounts
    accounts = archive.db.get_accounts()
    if len(accounts) > 1:
        print("\nPer-account breakdown:")
        counts = archive.db.get_email_count_by_account()
        for acct, count in counts.items():
            print(f"  {acct}: {count} emails")


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
  %(prog)s search "invoice from:amazon"   Search emails
  %(prog)s stats                           Show statistics
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
        "--archive-dir",
        type=Path,
        help="Directory to store emails and database",
    )

    parser.add_argument(
        "--account",
        type=str,
        help="Email account to operate on (default: all accounts)",
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

    # accounts command (new for v0.2)
    accounts_parser = subparsers.add_parser(
        "accounts",
        help="Manage email accounts",
    )
    accounts_sub = accounts_parser.add_subparsers(dest="accounts_cmd")
    accounts_sub.add_parser("list", help="List configured accounts")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    config = load_config(args.config, SCRIPT_DIR)

    # Determine archive_dir
    if args.archive_dir:
        archive_dir = args.archive_dir
    else:
        archive_dir = get_archive_dir(config, DEFAULT_ARCHIVE_DIR)

    try:
        if args.command == "setup":
            keychain = KeychainStorage()
            cmd_setup(keychain, args.credentials_file)

        elif args.command == "accounts":
            if args.accounts_cmd == "list":
                archive = EmailArchive(archive_dir, config)
                accounts = archive.db.get_accounts()
                if accounts:
                    print("\nConfigured accounts:")
                    for acct in accounts:
                        print(f"  - {acct}")
                else:
                    print("\nNo accounts configured yet.")
                    print("Run 'ownmail backup' to set up your first account.")
            else:
                accounts_parser.print_help()

        else:
            archive = EmailArchive(archive_dir, config)

            if args.command == "backup":
                cmd_backup(archive, args.account)
            elif args.command == "search":
                cmd_search(archive, args.query, args.account, args.limit)
            elif args.command == "stats":
                cmd_stats(archive, args.account)

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise  # For debugging during development
        # sys.exit(1)


if __name__ == "__main__":
    main()
