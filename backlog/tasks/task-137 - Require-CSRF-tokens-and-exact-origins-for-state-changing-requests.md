---
id: TASK-137
title: Require CSRF tokens and exact origins for state-changing requests
status: Done
assignee: []
created_date: '2026-10-10 05:32'
updated_date: '2026-10-10 07:26'
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
- [x] #1 Every route that accepts a state-changing method, including the /downloads JSON controls, requires a valid token; a test that enumerates app.url_map fails when a new state-changing route lacks protection.
- [x] #2 Origin is compared exactly with the configured origins; a missing Origin, Origin: null, a prefix-similar origin, and a foreign Origin with a matching Referer are rejected with 403 before any handler runs.
- [x] #3 Every UI form and fetch call that mutates state sends the token, and the handling of a stale token after a server restart is defined and tested.
- [x] #4 Test-client regressions reproduce each row of the table above with synthetic requests and assert the mocked mutation is not called in any rejected case; existing tests send the token through a fixture rather than relying on header-less acceptance.
- [x] #5 Documentation states the policy for header-less and non-browser clients.
- [x] #6 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changes live request acceptance; confirm deployment with the maintainer before landing.

Open decisions for the maintainer:
- Token lifetime and storage. A random per-process token embedded in pages needs no stored secret but rotates on restart and reload, so open pages need a clear reload prompt. A persisted signing key survives restarts, but storing a secret is a STOP item.
- Non-browser clients. None exist in the repository. Rejecting header-less requests is the default; supporting scripted clients would need a separate credential.
- Configured origins. They can be derived from TASK-136's allowed hosts, or set separately when a TLS-terminating proxy makes request.scheme differ from the browser's origin.

Maintainer decisions (2026-10-09):
- Signing key: a fresh random key at each process start. Nothing secret is persisted. After a restart, trusted scripts that get a token rejection fetch a fresh token and retry once; a plain HTML form post that fails gets a short "page expired, reload" response.
- Non-browser clients: none exist in the repository. State-changing requests without a valid token are rejected by default.
- Standard library only (secrets, hmac, hashlib); no new runtime dependency.

Implementation: ownmail/web_csrf.py registers a before_request hook right after the TASK-136 Host check, so it runs before every handler. Every method other than GET, HEAD and OPTIONS, on any path, needs (a) an Origin exactly equal to an allowed origin, or, when Origin is absent, a Referer whose scheme://netloc is exactly allowed (Origin: null, an empty Origin and requests with neither header are rejected), and (b) a valid token in the X-CSRF-Token header or the csrf_token form field. Rejections are 403 with X-CSRF-Rejected: origin or token and Cache-Control: no-store; the body is JSON {"error": ...} when the request carried the token header and plain text otherwise. The old Origin/Referer guard in ownmail/web.py and the origin check in web_downloads.require_json were removed.

Allowed origins: the request's own origin, built from request.scheme and the Host that the TASK-136 check accepted, with the port dropped only when it is that scheme's default. Other allowed hosts, and the same host on another port, are separate origins and are rejected. web.allowed_origins (or repeated --allowed-origin) adds origins for deployments behind a TLS-terminating proxy. Entries are canonicalized as browsers serialize origins (lowercase, IPv6 compressed, default port dropped); invalid entries stop serve before the sanitizer starts, and serve prints the configured list. X-Forwarded-* headers are not read.

Token binding (no user sessions yet): signed double-submit. The ownmail_csrf cookie holds 32 random bytes and is host-only (no Domain), Path=/, HttpOnly, SameSite=Strict, and lasts for the browser session. It is Secure on HTTPS requests and on requests whose Host names a configured https origin, as behind a TLS-terminating proxy that forwards the browser's Host. Browsers send it to every port on the host, which is why other ports must fail the origin check. The token is base64url(HMAC-SHA256(process key, cookie value)). It verifies only with the same browser's cookie and the current process key. Cross-site requests do not carry the cookie, and other origins cannot read the token: no CORS headers, no JSONP, GET /csrf-token returns JSON with Cache-Control: no-store and X-Content-Type-Options: nosniff and is Host-checked, and the custom header forces a CORS preflight. Pages carry the token as the text of a JSON data block in <head>, which message CSS cannot match, and the reader page has no form containing it. Every response that renders a token, including GET /csrf-token, is sent with Cache-Control: no-store. Following a link from another site sends no SameSite=Strict cookie, so the server issues a new one; pages already open then recover as after a restart.

Once authentication sessions exist: bind the token to the session instead of the anonymous cookie (derive it from the session secret or keep a per-session random token server-side), rotate it at login and logout, reject tokens from other sessions, and drop the ownmail_csrf cookie. If sessions must survive restarts, the per-process key has to be revisited; storing a key is a STOP item.

State-changing routes (all POST): /trash/<email_id>, /restore/<email_id>, /trash-bulk, /restore-bulk, /delete-forever, /empty-trash, /trust-sender, /untrust-sender, /settings, /labels/<email_id>, /downloads, /downloads/schedule. No GET route changes user-visible state. GET, HEAD and OPTIONS are exempt from the checks, and Flask sends HEAD to the GET view, so no view may serve both a safe method and a state-changing one: /labels/<email_id> and /settings have separate GET and POST views. Two GET paths do internal bookkeeping that requests cannot direct: opening an existing Active cache rebuilds its disposable search index, and GET /downloads reaps a finished download process.

Callers: message-actions.js adds window.ownmailFetch, which sends the token on non-GET requests and makes the single retry; ownmailRequest (used by every reader, list, trash and label action) and downloads.js use it. The Settings and Empty Trash forms carry the hidden field. The token reaches templates through a context processor: touching app.jinja_env in create_app would create the Jinja environment before run_server enables template reloading.

The sanitizer unwraps message forms (TASK-139), so the request checks are a second layer for them. The browser tests render a synthetic message form without the sanitizer. With rel=noreferrer, Chromium sends Origin: null and the origin check rejects it. Without noreferrer, the browser sends the reader's own origin and the token check rejects it.

Tests: tests/test_web_csrf.py discovers every rule and method in app.url_map. It runs an origin matrix and a token matrix (missing, empty, forged, other cookie, no cookie, expired key, valid) against each state-changing method, with the handler replaced by a recorder. It sends every GET, HEAD and OPTIONS with a write payload, a foreign Origin and no token, and fails if a view that accepts a state-changing method runs. It checks that a server on port 8080 accepts only its own origin and that only the scheme's default port is dropped; reproduces each row of the reported table on /delete-forever and asserts the mocked deletion is not called; and covers the token endpoint, cookie attributes including Secure behind a proxy, no-store on pages, the stale Settings form and allowed-origin configuration. tests/test_csrf_browser.py runs reader, settings, download and trash actions in Chromium across a simulated restart. tests/test_message_actions.py covers the single retry. tests/conftest.py makes app.test_client() fetch and send a token for mutations; app.test_client(csrf=False) sends requests as written.

Deployment: direct HTTP access through allowed hosts needs no configuration. An HTTPS-terminating proxy needs web.allowed_origins before upgrading; origins opened directly need no entry. After the restart that installs the change, open pages recover on their next action, except the Settings form, which needs a reload. Scripts or other non-browser clients that posted to the web server stop working.

Origin fallback: as the 2026-10-09 requirements specify, a request without Origin passes the origin check only when its Referer's origin matches an allowed origin exactly (it still needs a valid token). A missing Origin with no matching Referer, Origin: null, a prefix-similar origin, and a foreign Origin with a matching Referer are rejected, as AC #2 requires.

Follow-up (2026-10-10):
- HEAD /labels/<email_id> with a JSON body ran the label write without either check. The view treated every method other than GET as a write, Flask routes HEAD to it, and the CSRF check exempts HEAD. Browsers cannot send such a request, but other clients can. The route now has separate GET and POST views, and the exempt-method test above covers every rule.
- Origins derived from every allowed host also accepted other allowed names and port-less variants, such as http://localhost and http://127.0.0.1 for a server on port 8080. Only the request's own origin is derived now, and configured origins add to it instead of replacing the derived list.
- The cookie is also Secure when the Host names a configured https origin, and responses that render a token are not cacheable. X-Forwarded-* headers are still not read.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Every request other than GET, HEAD and OPTIONS now needs an Origin exactly equal to an allowed origin (or, without Origin, an exactly matching Referer) and a CSRF token, checked before any handler runs. Tokens are HMACs of a host-only, HttpOnly, SameSite=Strict cookie under a per-process key, so a restart expires them: open pages refresh the token and retry once, and a stale Settings form asks for a reload. The allowed origin is the one the request was sent to; web.allowed_origins and --allowed-origin add the browser's origin behind an HTTPS proxy. Clients without a browser can no longer post to the web server. Deployments behind an HTTPS-terminating proxy must set web.allowed_origins before upgrading.
<!-- SECTION:FINAL_SUMMARY:END -->
