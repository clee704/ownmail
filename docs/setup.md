# Setup and browser access

[Back to README](../README.md)

## Email providers

`ownmail setup` connects a provider, saves its credentials in the system keychain,
and creates `config.yaml` in your working directory. It asks where to store the
archive. Running setup again can add another source.

### IMAP with an app password

Use this method with a provider that allows password-based IMAP access:

```bash
ownmail setup --method imap
```

Enter the email address, IMAP server hostname, and app password when prompted.
Gmail addresses use `imap.gmail.com` automatically. Other providers must support
the IMAP login method used by ownmail; an IMAP service that requires OAuth alone
cannot use this method.

For Gmail:

1. Enable [2-Step Verification](https://myaccount.google.com/signinoptions/two-step-verification).
2. Create an [App Password](https://myaccount.google.com/apppasswords).
3. Enter it at the hidden password prompt during setup.

App password availability depends on account settings and administrator policy.
See [Google's app password guidance](https://support.google.com/accounts/answer/185833).
Gmail API with OAuth is another option where account policy allows it.

### Gmail API with OAuth

This method uses the read-only Gmail API scope, supports batch downloads, and
preserves native Gmail labels. It requires a Google Cloud project and desktop
OAuth credentials.

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project and enable the Gmail API.
3. Configure the OAuth consent settings and any required test users.
4. Create an OAuth client with application type **Desktop app** and download its JSON file.
5. Run setup:

```bash
ownmail setup --method oauth
```

Supply the client credential JSON when prompted and complete browser consent.
See [Google's desktop OAuth setup guide](https://developers.google.com/workspace/gmail/api/quickstart/python#set_up_your_environment)
for the current console steps. Ownmail stores the imported credentials and token
in the system keychain; protect the downloaded JSON file as well.

## Configuration

Setup writes a configuration like this synthetic example. Replace the provider
and account values with your own:

```yaml
archive_root: ./archive

sources:
  - name: personal
    type: imap
    host: imap.example.com
    account: mail@example.com
    auth:
      secret_ref: keychain:imap-password/mail@example.com
```

The account reference identifies an entry in the system keychain; it is not the
password. Relative archive paths are resolved from the working directory.

Run commands from the directory containing `config.yaml`, or give its path after
the command:

```bash
ownmail download --config /path/to/config.yaml
ownmail serve --config /path/to/config.yaml
```

[config.example.yaml](../config.example.yaml) documents additional sources,
a separate database directory, download filters, and web settings. The web
Settings page controls appearance, date formats, time zone, page size, and
image preferences.

## Browser and mobile access

Install a supported [Node.js LTS release](https://nodejs.org/en/download) with npm,
then start the server:

```bash
ownmail serve
```

It opens <http://127.0.0.1:8080> automatically. Use `--no-browser` to suppress that
step or `--port 8081` to choose another port. Keep the process running while using
the interface.

The first launch downloads the sanitizer dependencies through npm. Later local
reading and search can work without internet, though remote images and external
links still need their respective servers. If the sanitizer cannot start,
ownmail refuses to serve message HTML; check that Node.js and npm are available.

To reach the server from a phone on a trusted network:

```bash
ownmail serve --host 0.0.0.0
```

Open the serving computer's network address and port in the phone's browser.
This exposes the archive to other devices that can reach that address. There is
no built-in login; use network access controls or an authenticated proxy, and do
not expose the server directly to the public internet.

You can add the site to the phone's Home Screen. Its icon and standalone layout
use the same running server, so this does not provide a separate offline copy.

## HTML and remote images

Ownmail sanitizes email HTML through [DOMPurify](https://github.com/cure53/DOMPurify)
in a Node.js sidecar before displaying it. Image blocking is enabled by default,
but some CSS images and responsive image sources can still contact remote servers.
Use **Load images** for one message or **Always trust this sender** to remember a
sender. Loading remote content can reveal your request to the remote server.

For live template and Python changes during development, see
[Running locally](../CONTRIBUTING.md#running-locally).
