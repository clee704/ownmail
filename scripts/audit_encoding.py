#!/usr/bin/env python3
"""Audit email archive for encoding issues.

Scans all emails looking for:
- Unicode replacement characters (U+FFFD) indicating decode failures
- Raw MIME encoded-word sequences (=?...?=) that weren't decoded
- Mojibake patterns (high latin-1 chars suggesting wrong charset)

Usage:
    python scripts/audit_encoding.py [--limit N] [--verbose]
"""

import argparse
import re
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ownmail.archive import EmailArchive
from ownmail.config import load_config
from ownmail.parser import EmailParser
from ownmail.web import decode_header, _extract_attachment_filename


# Pattern for MIME encoded-word that wasn't decoded
MIME_ENCODED_RE = re.compile(r'=\?[^?]+\?[BbQq]\?[^?]+\?=')

# Pattern for potential mojibake (high latin-1 sequences)
# These are common EUC-KR byte patterns when misread as latin-1
MOJIBAKE_PATTERNS = [
    re.compile(r'[\xc0-\xff][\x80-\xff]{2,}'),  # Multiple high bytes in a row
]


def has_replacement_chars(text: str) -> bool:
    """Check if text contains Unicode replacement characters."""
    return '\ufffd' in text if text else False


def has_mime_encoded(text: str) -> bool:
    """Check if text contains undecoded MIME encoded-words."""
    return bool(MIME_ENCODED_RE.search(text)) if text else False


def has_mojibake(text: str) -> bool:
    """Check if text looks like mojibake (misinterpreted bytes)."""
    if not text:
        return False
    
    # Check if text can be encoded to latin-1 and has high bytes
    # (indicator of potential mojibake)
    try:
        encoded = text.encode('latin-1')
        high_bytes = sum(1 for b in encoded if b >= 0x80)
        # If more than 30% high bytes and no CJK characters, likely mojibake
        if high_bytes > len(encoded) * 0.3:
            # But check if it has actual CJK characters (then it's fine)
            cjk_chars = sum(1 for c in text if '\uAC00' <= c <= '\uD7AF'  # Hangul
                           or '\u4E00' <= c <= '\u9FFF'  # CJK
                           or '\u3040' <= c <= '\u30FF')  # Japanese
            if cjk_chars == 0:
                return True
    except UnicodeEncodeError:
        pass  # Can't encode to latin-1, not simple mojibake
    
    return False


def check_email(filepath: Path, verbose: bool = False) -> list[dict]:
    """Check a single email for encoding issues.
    
    Returns list of issues found.
    """
    issues = []
    
    try:
        # Parse email
        parsed = EmailParser.parse_file(filepath=filepath)
        
        # Check subject - apply same decode_header as web interface
        subject = parsed.get('subject', '')
        if subject and '=?' in subject:
            subject = decode_header(subject)
        
        if has_replacement_chars(subject):
            issues.append({'field': 'subject', 'type': 'replacement_char', 'value': subject[:100]})
        if has_mime_encoded(subject):
            issues.append({'field': 'subject', 'type': 'mime_encoded', 'value': subject[:100]})
        if has_mojibake(subject):
            issues.append({'field': 'subject', 'type': 'mojibake', 'value': subject[:100]})
        
        # Check sender - apply same decode_header as web interface
        sender = parsed.get('sender', '')
        if sender and '=?' in sender:
            sender = decode_header(sender)
        
        if has_replacement_chars(sender):
            issues.append({'field': 'sender', 'type': 'replacement_char', 'value': sender[:100]})
        if has_mime_encoded(sender):
            issues.append({'field': 'sender', 'type': 'mime_encoded', 'value': sender[:100]})
        if has_mojibake(sender):
            issues.append({'field': 'sender', 'type': 'mojibake', 'value': sender[:100]})
        
        # Check attachment filenames - use our proper extraction function
        import email
        from email.policy import default as email_policy
        
        with open(filepath, 'rb') as f:
            msg = email.message_from_binary_file(f, policy=email_policy)
        
        for part in msg.walk():
            content_disposition = str(part.get('Content-Disposition', ''))
            if 'attachment' in content_disposition:
                # Use our proper extraction function (same as web interface)
                filename = _extract_attachment_filename(part)
                
                if has_replacement_chars(filename):
                    issues.append({'field': 'attachment', 'type': 'replacement_char', 'value': filename[:100]})
                if has_mime_encoded(filename):
                    issues.append({'field': 'attachment', 'type': 'mime_encoded', 'value': filename[:100]})
                if has_mojibake(filename):
                    issues.append({'field': 'attachment', 'type': 'mojibake', 'value': filename[:100]})
    
    except Exception as e:
        if verbose:
            issues.append({'field': 'parse_error', 'type': 'error', 'value': str(e)[:100]})
    
    return issues


def main():
    parser = argparse.ArgumentParser(description='Audit email archive for encoding issues')
    parser.add_argument('--limit', type=int, help='Limit number of emails to check')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show progress')
    parser.add_argument('--config', type=str, help='Path to config file')
    args = parser.parse_args()
    
    # Load config
    config_path = Path(args.config) if args.config else Path('config.yaml')
    if config_path.exists():
        config = load_config(config_path)
        archive_root = Path(config.get('archive_root', '.'))
    else:
        print(f"Config not found at {config_path}, using current directory")
        archive_root = Path('.')
    
    # Open archive
    archive = EmailArchive(archive_root)
    
    # Get all emails from database
    import sqlite3
    conn = sqlite3.connect(archive.db.db_path)
    cursor = conn.execute('SELECT message_id, filename FROM emails ORDER BY email_date DESC')
    emails = cursor.fetchall()
    conn.close()
    
    if args.limit:
        emails = emails[:args.limit]
    
    print(f"Auditing {len(emails)} emails for encoding issues...\n")
    
    # Track issues
    all_issues = []
    checked = 0
    
    for message_id, filename in emails:
        filepath = archive.archive_dir / filename
        
        if not filepath.exists():
            if args.verbose:
                print(f"  SKIP (missing): {filename}")
            continue
        
        issues = check_email(filepath, verbose=args.verbose)
        
        if issues:
            all_issues.append({
                'message_id': message_id,
                'filename': filename,
                'issues': issues,
            })
            if args.verbose:
                print(f"  ISSUE: {filename}")
                for issue in issues:
                    print(f"    - {issue['field']}: {issue['type']}")
        
        checked += 1
        if checked % 1000 == 0:
            print(f"  Checked {checked}/{len(emails)}...")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"AUDIT COMPLETE")
    print(f"{'='*60}")
    print(f"Emails checked: {checked}")
    print(f"Emails with issues: {len(all_issues)}")
    
    if all_issues:
        # Group by issue type
        by_type = {}
        for item in all_issues:
            for issue in item['issues']:
                key = f"{issue['field']}:{issue['type']}"
                if key not in by_type:
                    by_type[key] = []
                by_type[key].append(item)
        
        print(f"\nIssues by type:")
        for key, items in sorted(by_type.items()):
            print(f"  {key}: {len(items)}")
        
        print(f"\n{'='*60}")
        print(f"SAMPLE ISSUES (first 10)")
        print(f"{'='*60}")
        
        for item in all_issues[:10]:
            print(f"\nMessage ID: {item['message_id']}")
            print(f"File: {item['filename']}")
            for issue in item['issues']:
                print(f"  [{issue['field']}] {issue['type']}: {issue['value']}")
        
        if len(all_issues) > 10:
            print(f"\n... and {len(all_issues) - 10} more emails with issues")
        
        # Exit with error code if issues found
        sys.exit(1)
    else:
        print("\n✓ No encoding issues found!")
        sys.exit(0)


if __name__ == '__main__':
    main()
