---
id: TASK-137
title: Require CSRF tokens and exact origins for state-changing requests
status: To Do
assignee: []
created_date: '2026-10-10 05:32'
labels:
  - security
dependencies:
  - TASK-136
references:
  - ownmail/web.py
  - ownmail/web_downloads.py
  - ownmail/static/message-actions.js
  - ownmail/static/downloads.js
priority: high
type: bug
ordinal: 9930
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
csrf_check (ownmail/web.py) guards POST routes by comparing headers with request.host_url. It accepts a request with neither Origin nor Referer, accepts a matching Referer when Origin names another site, and compares Referer by string prefix. require_json in ownmail/web_downloads.py also skips its check when both headers are missing. Synthetic test-client POSTs to /delete-forever at https://mail.example with a mocked archive:

| Headers | Status | Deletion called |
|---|---|---|
| None | 204 | Yes |
| `Origin: null` | 403 | No |
| Foreign Origin | 403 | No |
| `Referer: https://mail.example.attacker.invalid/` | 204 | Yes |
| Foreign Origin and matching Referer | 204 | Yes |
| Matching Origin | 204 | Yes |

These results show validation behavior, not a complete cross-site exploit; browser header rules decide exploitability. OwnMail has no login, so any client that reaches the server can already mutate without a browser. This task covers browser-mediated requests and is a prerequisite for cookie-based authentication.

Require a CSRF token on every state-changing request, compare Origin exactly with configured origins after parsing scheme, host and port, and reject a missing or null Origin on browser mutations instead of falling back to Referer. Use the standard library (secrets, hmac.compare_digest); a CSRF library would be a new runtime dependency, which is a STOP item.

No code in the repository posts to these routes except the web UI; the CLI works on the archive directly. Unless the maintainer decides otherwise, header-less requests are rejected and the policy is documented.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every route that accepts a state-changing method, including the /downloads JSON controls, requires a valid token; a test that enumerates app.url_map fails when a new state-changing route lacks protection.
- [ ] #2 Origin is compared exactly with the configured origins; a missing Origin, Origin: null, a prefix-similar origin, and a foreign Origin with a matching Referer are rejected with 403 before any handler runs.
- [ ] #3 Every UI form and fetch call that mutates state sends the token, and the handling of a stale token after a server restart is defined and tested.
- [ ] #4 Test-client regressions reproduce each row of the table above with synthetic requests and assert the mocked mutation is not called in any rejected case; existing tests send the token through a fixture rather than relying on header-less acceptance.
- [ ] #5 Documentation states the policy for header-less and non-browser clients.
- [ ] #6 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changes live request acceptance; confirm deployment with the maintainer before landing.

Open decisions for the maintainer:
- Token lifetime and storage. A random per-process token embedded in pages needs no stored secret but rotates on restart and reload, so open pages need a clear reload prompt. A persisted signing key survives restarts, but storing a secret is a STOP item.
- Non-browser clients. None exist in the repository. Rejecting header-less requests is the default; supporting scripted clients would need a separate credential.
- Configured origins. They can be derived from TASK-136's allowed hosts, or set separately when a TLS-terminating proxy makes request.scheme differ from the browser's origin.
<!-- SECTION:NOTES:END -->
