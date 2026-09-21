# Owning your mail

ownmail exists so you can keep your messages on your own storage and remove
them from mail servers. Gmail, Apple Mail, and other mail clients remain useful
for receiving, replying, and organizing live mail. Servers only need to keep
messages while they serve that work.

ownmail brings the mail you care about across accounts into one place to read
and search, from ongoing conversations to old receipts. Spam and messages
discarded before archival stay out.

The Active view and automatic capture of eligible filed and Sent mail are
available. Capture follows the current state reported by the provider; unknown
or failed checks keep affected messages server-owned. Cleanup previews and
separately authorized Gmail Trash moves are available.
See [current download behavior](archive.md#download-filters) and
[cleanup limits](archive.md#server-cleanup).

## Ownership

**Servers control live mail. Ownmail controls the copies it has archived.**

Downloading makes a message available locally. Archiving transfers authority.

| Before a message has been archived | Ownmail's behavior |
|---|---|
| Inbox | Download as **Active**, following server changes. |
| Drafts or other unfinished outgoing mail | Keep Active until sent or discarded. |
| Sent or filed mail outside active states | **Archive** its contents and labels once current checks establish eligibility and the snapshot is successfully saved. |
| Trash or Spam | Skip it; remove any Active cached copy after confirming the change. |

Trash and Spam take precedence over other roles. Inbox or unfinished outgoing
state takes precedence over Sent and filing labels. A star, unread status, or
custom label does not transfer authority.

Active and archived messages appear together in reading and search, with Active
status and freshness visible. Active copies follow server edits and deletion;
they live in a disposable cache outside the archive. A failed refresh does not
imply deletion. Live work continues in the mail client.

Archival happens when ownmail observes eligible mail and safely saves it with
its labels. Sending completes a message even if its conversation continues. A
failed download does not complete the handoff.

After archival, server moves, deletion, or label changes never alter the owned
copy. A verified owned message returning to Inbox remains Archived and is not
tracked as Active again. Ownmail's local edits and Trash are independent of the
server's. Older duplicate Active copies are removed after verifying the owned
file; missing, damaged or ambiguous ownership evidence keeps the cache.

Mail captured before it reaches server Trash is preserved. Mail first observed
in Trash is skipped, even if it passed through an archive folder between
downloads. Discarding a cached Inbox message does not make it a permanent archive.

## Removing server copies

Server cleanup is optional and previews by default. An explicit apply request
can move a Gmail server copy to Trash after verifying its owned contents,
capture metadata, account identity, and current message and thread activity.
Local labels stay unchanged. Whether and when Trash is permanently emptied
depends on the provider's retention settings; ownmail never hard-deletes server mail.

Inbox and unfinished outgoing messages hold their thread's server copies in
place; Trash and Spam do not. Uncertain thread state postpones cleanup. Eligible
messages still enter the archive immediately.

For example, a reply can be archived while the message it answers remains in
Inbox. Both stay available in the mail client until the thread clears. A later
reply can protect server copies still present, but does not restore copies
already removed. A thread left active indefinitely stays on the server.

## Current implementation

Ownmail reads and searches cached Active mail alongside owned messages. Verified
matches appear once in ordinary results, and the reader links to both versions.
Active messages remain managed in the mail client; local labels and Trash belong
to archived copies. Existing contents, label snapshots, and local Trash survive
the introduction of the cache unchanged.

Active downloads default on for each source and use the same manual or scheduled
download operation. Disabling them retains prior cache contents with stale
status. Existing `exclude_roles` settings cannot permit Inbox or unfinished
outgoing mail capture.

Ordinary filed and Sent mail is eligible when a fresh candidate read finds no
Active, discarded, or unrecognized state. Capture requires a successful save of
the contents and configured labels. An unrelated source failure leaves refresh
incomplete while confirmed candidates can still be captured. Sending can
complete capture while a thread remains active.

Provider observations have limits. IMAP's advertised Scheduled attribute and
SubmitPending keyword establish unfinished outgoing state. Gmail's Scheduled
API semantics remain unverified, and hidden or unadvertised state may be
unavailable through either provider. See the [provider details](archive.md#download-filters).

`ownmail cleanup --source NAME` verifies and previews; `--apply` explicitly
requests Gmail Trash moves. Each run rechecks current evidence, including after
an interruption. Legacy captures without complete durable metadata remain held.
IMAP cleanup remains held because account-wide thread visibility is unavailable.

Downloads and previews keep their read-only Gmail login. The explicit
`authorize-cleanup --source NAME` command requests `gmail.modify` through Google
consent and stores a separate cleanup credential. That scope includes broad
mailbox and sending permissions; ownmail uses cleanup access to verify and move
eligible copies to server Trash. Applying uses saved cleanup access and never
opens consent automatically. The
[Mail ownership workstream](<../backlog/tasks/task-14 - Drain-remote-servers-—-delete-archived-mail-once-verified-locally.md>)
records implementation progress and remaining provider limits.
