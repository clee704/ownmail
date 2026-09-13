# ownmail

**Your email archive, with a web interface for desktop and mobile.**

Keep your mail as standard `.eml` files on your own drive. Search across accounts,
browse labels, read HTML messages, and preview attachments in your browser.
The command line handles downloads, imports, and archive maintenance.

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
- **Choose your appearance:** Light, dark, or system theme, with adjustable dates,
  time zone, and page size.
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

### What gets archived

By default, ownmail downloads mail outside **Inbox**, **Drafts**, **Trash**, and
**Spam**. Sent mail is eligible. Mail you later file out of the inbox or rescue
from spam can be picked up by subsequent downloads.

You can include inbox mail and drafts with `exclude_roles` in your source
configuration. Trash and spam remain excluded. See
[download filters](docs/archive.md#download-filters) before your first download
if you want to change these defaults.

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
| `download` | Download new eligible mail |
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
| `reconcile` | Review archived mail against the current download filter |
| `rebuild` | Rebuild the index or selected metadata |
| `reset-sync` | Reset download progress for a rescan |
| `list-unknown` | List messages with unparseable dates |
| `sources list` | List configured mail sources |

Run `ownmail <command> --help` for options. See
[archive storage, verification, and repairs](docs/archive.md) for maintenance.

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
