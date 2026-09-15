# ownmail

**Your email archive, with a web interface for desktop and mobile.**

Keep your mail as standard `.eml` files on your own drive. Search across accounts,
browse labels, read HTML messages, and preview attachments in your browser.
Start or schedule downloads in the web interface. The command line also handles
downloads, imports, and archive maintenance.

The goal is to own your mail and remove server copies once they are no longer
needed by your mail clients. Read [Owning your mail](docs/philosophy.md) for the
product philosophy, Active ownership, and server-cleanup limits.

> **Development version:** This README describes `0.4.0-dev` on `master`.
> [PyPI currently provides 0.3.0](https://pypi.org/project/ownmail/), which has an
> older interface. Use the GitHub installation below for the features described here.

## Browse your archive

- **Search and navigate:** Full-text search, sender links, labels, attachment
  indicators, sorting, and pagination across your saved mail.
- **Read on desktop or phone:** A collapsible sidebar becomes a navigation drawer
  on smaller screens. Add the site to your phone's Home Screen for app-style access.
- **Read messages and attachments:** View sanitized HTML, expand message details,
  and preview supported attachment formats or download the originals.
- **Choose your appearance:** Light, dark, or system theme, with adjustable desktop
  message and sidebar density, dates, time zone, and page size. In Settings, choose
  Comfortable, Standard (the default), or Compact spacing; density is saved
  automatically in your browser.
- **Control remote images:** Load images for a message or remember a trusted
  sender. Image blocking is enabled by default, with [limitations](#privacy-and-security).
- **Manage saved mail:** Select messages, move them to the archive's Trash, and
  restore them. Mobile selection supports a long press.

Your `.eml` files and JSON label sidecars preserve the archive; SQLite provides
its rebuildable search index. Downloads are incremental and resumable with Ctrl-C.
You can also import `.eml` exports from other mail tools.

## Install

### Development version from GitHub

Requires **Python 3.10+**, **Git**, and [pipx](https://pipx.pypa.io/stable/).
For the web interface, also install a supported
[Node.js LTS release](https://nodejs.org/en/download) with npm. Connecting a mail
provider requires a working system keychain.

```bash
pipx install "git+https://github.com/clee704/ownmail.git@master"
```

`master` follows ongoing development and can change between installations.
To switch an existing pipx installation from PyPI to this version:

```bash
pipx install --force "git+https://github.com/clee704/ownmail.git@master"
```

To refresh an installation made from GitHub:

```bash
pipx reinstall ownmail
```

Reinstallation uses the original source and resolves dependencies again. It also
picks up new commits when the development version number has not changed.
For a source checkout or editable installation, see [Contributing](CONTRIBUTING.md).

### Published version from PyPI

To use the published 0.3.0 release with its web dependencies:

```bash
pipx install "ownmail[web]==0.3.0"
```

Follow the [0.3.0 README](https://github.com/clee704/ownmail/blob/v0.3.0/README.md)
for that version's behavior and requirements.

## Quick start

Run these commands from a directory where you want to keep `config.yaml`:

```bash
# Connect a mail provider and choose where to store the archive
ownmail setup

# Download eligible mail
ownmail download

# Open the archive in your browser
ownmail serve
```

Setup creates the configuration and stores credentials in your system keychain.
Choose IMAP for a provider that accepts an app password, or Gmail API with OAuth
for read-only Gmail access. See [provider setup and configuration](docs/setup.md).

The browser opens at <http://127.0.0.1:8080>. The first launch installs the HTML
sanitizer's Node.js dependencies and needs internet access. Once installed, local
reading and search work without internet; keep `ownmail serve` running while you
browse. A phone also needs a connection to that server. See
[browser and mobile access](docs/setup.md#browser-and-mobile-access).

### Download from the browser

Open **Settings → Downloads** and choose **Download now** to run the same download
as `ownmail download`, using all configured sources and their existing filters.
The page shows the current source, archived and Active-refreshed message counts,
and failures with a brief reason. Counts cover the current run across all sources;
incomplete Active refreshes remain marked incomplete when capture finishes.
Command-line and web downloads cannot overlap for the same archive.

For automatic downloads, choose an interval and **Save schedule**. Available
intervals are 15 minutes, 30 minutes, 1 hour, 6 hours, and 1 day; **Off** disables
the schedule. The default is Off, and the saved interval survives server restarts.
Each interval starts after a download finishes or the server restarts.
Keep `ownmail serve` running for scheduled downloads; the browser can be closed.
The interval is stored as `web.download_interval_minutes` in `config.yaml`.

### What gets archived

Ownmail caches **Inbox**, **Drafts**, other observed unfinished mail, and mail
with unconfirmed state for reading and search alongside your archive. These
Active copies remain server-owned and follow confirmed server changes. Trash
and Spam stay out.

Ordinary filed and Sent mail is archived after a fresh server check finds it
outside active or discarded states and its contents and configured labels are
saved. Unrecognized states and failed checks keep affected messages uncaptured.
Capture follows the state visible to the provider; hidden or unadvertised
unfinished states may be unavailable to ownmail.

Active downloads default on. Set `active_downloads: false` per source to disable
them; prior cache contents remain stale. Existing `exclude_roles` values are
accepted but cannot allow Inbox or Drafts into the archive. See
[download filters and provider limits](docs/archive.md#download-filters).

## Server cleanup

Preview which archived messages could be moved to server Trash:

```bash
ownmail cleanup --source personal
```

Cleanup verifies the owned contents and capture metadata, the Gmail account,
and current message and thread activity. It reports held messages and failures
with reasons. Local contents and labels stay unchanged; IMAP cleanup remains held.

`--apply` explicitly requests Gmail Trash moves. Existing Gmail sign-in stays
read-only and supports previews. Applying requires `gmail.modify`; a separate
cleanup consent flow is not implemented, and `--apply` does not request broader
permissions. See [cleanup checks, retry behavior, and provider limits](docs/archive.md#server-cleanup).

## Search

Use the search box in the web interface or the same query syntax in the terminal:

```bash
ownmail search "invoice"
ownmail search "from:example.com"
ownmail search "subject:receipt"
ownmail search "attachment:pdf"
ownmail search 'label:"Receipts, 2026"'
```

The web interface includes search help with supported operators and examples.

## Commands

| Command | Purpose |
|---|---|
| `setup` | Connect a mail source and store credentials |
| `download` | Refresh Active mail and archive eligible filed and Sent mail |
| `cleanup --source NAME` | Preview server cleanup; `--apply` requests eligible Gmail Trash moves |
| `serve` | Open the web interface |
| `search "query"` | Search from the terminal |
| `import <path>` | Import external `.eml` files |
| `scan` | Index `.eml` files already in the archive |
| `stats` | Show archive statistics |
| `verify` | Check hashes, files, and index integrity |
| `sync-check` | Compare the archive with its mail sources |
| `trash` | View and manage the archive's Trash |
| `update-labels` | Backfill missing labels |
| `relabel` | Repair IMAP folder labels from the server |
| `reconcile` | Review archived mail against legacy role and folder filters |
| `rebuild` | Rebuild the index or selected metadata |
| `reset-sync` | Reset download progress for a rescan |
| `list-unknown` | List messages with unparseable dates |
| `sources list` | List configured mail sources |

Run `ownmail <command> --help` for options. See
[archive storage, verification, and repairs](docs/archive.md) for maintenance.

`download` ends with an overall summary of downloaded emails, errors, and the
current archive size. With `--source`, download and error counts cover that
source; the archived total still covers the whole archive.

## Privacy and security

Credentials are stored in the system keychain. Messages, attachments, label
sidecars, the search index, and account configuration remain on your filesystem
and can contain sensitive information. Use encrypted storage and protect your
backups; ownmail does not encrypt the archive itself.

The web interface sanitizes message HTML with
[DOMPurify](https://github.com/cure53/DOMPurify). Image blocking is enabled by
default, but does not suppress every remote resource. Some CSS images and
responsive image sources can still contact remote servers. Loading images
explicitly can also reveal your request to the sender's servers.

The server listens on localhost by default and has no built-in login. If you
make it reachable from other devices, control access through a trusted network
or an authenticated proxy. Home Screen access uses the same server; it does not
store an offline archive on the phone.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and repository rules,
and [AGENTS.md](AGENTS.md) for AI-agent instructions. Planned and in-flight work
lives in [the backlog](backlog/tasks).

## License

[MIT](LICENSE)
