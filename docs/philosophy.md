# Owning your mail

ownmail exists so you can keep your messages on your own storage and remove
them from mail servers. Gmail, Apple Mail, and other mail clients remain useful
for receiving, replying, and organizing live mail. Servers only need to keep
messages while they serve that work.

ownmail brings the mail you care about across accounts into one place to read
and search, from ongoing conversations to old receipts. Spam and messages
discarded before archival stay out.

This is the product design. The Active view and server cleanup described below
are planned; [current download behavior](archive.md#download-filters) differs.

## Ownership

**Servers control live mail. Ownmail controls the copies it has archived.**

Downloading makes a message available locally. Archiving transfers authority.

| Before a message has been archived | Ownmail's behavior |
|---|---|
| Inbox | Download as **Active**, following server changes. |
| Drafts or other unfinished outgoing mail | Keep Active until sent or discarded. |
| Sent or filed mail outside active states | **Archive** its contents and labels when successfully saved. |
| Trash or Spam | Skip it; remove any Active cached copy after confirming the change. |

Trash and Spam take precedence over other roles. Inbox or unfinished outgoing
state takes precedence over Sent and filing labels. A star, unread status, or
custom label does not transfer authority.

Active and archived messages appear together in reading and search, with Active
status and freshness visible. Active copies follow server edits and deletion;
they are not permanent backups. A failed refresh does not imply deletion. Live
work continues in the mail client.

Archival happens when ownmail observes eligible mail and safely saves it with
its labels. Sending completes a message even if its conversation continues. A
failed download does not complete the handoff.

After archival, server moves, deletion, or label changes never alter the owned
copy. A server copy returning to Inbox becomes active again; its archived copy
stays unchanged. Ownmail's local edits and Trash are independent of the server's.

Mail captured before it reaches server Trash is preserved. Mail first observed
in Trash is skipped, even if it passed through an archive folder between
downloads. Discarding a cached Inbox message does not make it a permanent archive.

## Removing server copies

Server cleanup is optional. When enabled, ownmail moves a server copy to Trash
only after verifying its archived copy and checking that the message and its
thread are no longer active. Whether and when Trash is permanently emptied
depends on the provider's retention settings.

Inbox and unfinished outgoing messages hold their thread's server copies in
place; Trash and Spam do not. Uncertain thread state postpones cleanup. Eligible
messages still enter the archive immediately.

For example, a reply can be archived while the message it answers remains in
Inbox. Both stay available in the mail client until the thread clears. A later
reply can protect server copies still present, but does not restore copies
already removed. A thread left active indefinitely stays on the server.

## Current implementation

Ownmail already archives eligible mail, preserves message files and label
sidecars, and supports local reading, search, and Trash. Downloads currently
exclude Inbox and Drafts by default; allowing them captures permanent copies,
without the Active ownership distinction.

The [Mail ownership workstream](<../backlog/tasks/task-14 - Drain-remote-servers-—-delete-archived-mail-once-verified-locally.md>)
tracks the remaining implementation: reliable label capture, the Active view,
local label editing, and server cleanup with thread protection.
