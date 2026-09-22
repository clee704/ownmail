#!/usr/bin/env python3
"""Check commit headers against the Conventional Commit format in CONTRIBUTING.md.

Usage:
    python scripts/check_commit_msg.py MESSAGE_FILE     # commit-msg hook
    python scripts/check_commit_msg.py --header TEXT    # pull request title
    python scripts/check_commit_msg.py --range OLD..NEW # pushed commits
"""

import argparse
import re
import subprocess
import sys

TYPES = ("feat", "fix", "docs", "test", "refactor", "perf", "chore", "release")
MAX_LENGTH = 72
HEADER_RE = re.compile(rf"^(?:{'|'.join(TYPES)}): \S")
# GitHub sends an all-zero "before" revision when a push creates the branch.
ZERO_REV = re.compile(r"^0+$")


def header_error(header: str) -> str | None:
    """Return why a commit header is invalid, or None when it is valid."""
    if not HEADER_RE.match(header):
        return f"expected '<type>: <description>' with type in {', '.join(TYPES)}"
    if len(header) > MAX_LENGTH:
        return f"{len(header)} characters; keep it within {MAX_LENGTH}"
    return None


def range_headers(rev_range: str) -> list[tuple[str, str]]:
    """Return (short revision, header) pairs for the commits in a range."""
    old, _, new = rev_range.partition("..")
    args = [new, "-1"] if ZERO_REV.match(old) else [rev_range]
    out = subprocess.run(
        ["git", "log", "--format=%h%x00%s", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [tuple(line.split("\0", 1)) for line in out.splitlines()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("message_file", nargs="?")
    group.add_argument("--header")
    group.add_argument("--range", dest="rev_range")
    args = parser.parse_args(argv)

    if args.message_file:
        with open(args.message_file, encoding="utf-8") as f:
            headers = [("commit message", f.readline().rstrip("\n"))]
    elif args.header is not None:
        headers = [("title", args.header)]
    else:
        headers = range_headers(args.rev_range)

    failed = False
    for source, header in headers:
        error = header_error(header)
        if error:
            print(f"{source}: {header!r}: {error}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
