---
id: TASK-136
title: Reject requests for unconfigured Host names
status: Done
assignee: []
created_date: '2026-10-10 05:32'
updated_date: '2026-10-10 07:22'
labels:
  - security
dependencies: []
references:
  - ownmail/web.py
  - ownmail/web_downloads.py
priority: medium
type: bug
ordinal: 9920
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
create_app (ownmail/web.py) configures no Host allowlist (Flask's TRUSTED_HOSTS is unset), and no route checks the Host header. A test-client GET with `Host: rebind.invalid` is served normally. A POST to /empty-trash with that Host and `Origin: http://rebind.invalid` passes csrf_check and empties the bin, because the guard compares Origin with request.host_url, which comes from the request's own Host. A DNS-rebinding page whose name resolves to the server is therefore treated as same-origin. Whether rebinding succeeds depends on the browser and network; it has not been tested.

Add a configurable list of allowed hosts, for example `web.allowed_hosts`, and answer other Host values with 400 before any route runs. The installed Flask (3.1) supports TRUSTED_HOSTS, but pyproject.toml declares `flask>=2.0.0`; either raise that floor or check Host in a request hook.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A configurable allowed-hosts setting applies to every route, including static files and JSON endpoints; any other Host value gets 400 before route code runs.
- [x] #2 The default when nothing is configured follows the decision recorded in the notes, and serve prints the effective allowed hosts at startup.
- [x] #3 Test-client regressions reject a synthetic foreign Host (rebind.invalid) for GET and POST, including a POST whose Origin matches that Host, and accept configured hosts with and without an explicit port.
- [x] #4 Setup documentation describes the setting and its use behind a reverse proxy.
- [x] #5 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changes live request acceptance; confirm deployment with the maintainer before landing.

Open decision for the maintainer: the default when no allowed hosts are configured.
- Loopback names only (localhost, 127.0.0.1, ::1). Fails closed; LAN and reverse-proxy deployments must configure the setting before upgrading.
- Loopback names plus the --host address when it is a specific address; wildcard binds (0.0.0.0, ::) must configure the setting or serve refuses to start.
- Any Host with a startup warning. Keeps current behavior and gives no protection by default.
The first two fail closed; the second keeps direct-address deployments working.

Reverse proxies normally pass the public Host through. Trusting X-Forwarded-* headers is out of scope unless the maintainer decides to support it.

Maintainer decision (2026-10-09): when no allowed hosts are configured, accept only loopback Host values (localhost, 127.0.0.1, [::1]), with or without the serving port. Deployments reached by other names or addresses must configure them explicitly.

Implementation: ownmail/web_hosts.py adds a before_request hook, registered before every other hook, that answers a Host outside app.config["allowed_hosts"] with a plain-text 400. A missing Host is rejected. Flask's TRUSTED_HOSTS config was not used: pyproject.toml allows flask>=2.0.0 and raising that floor needs sign-off. The installed Flask 3.1 and Werkzeug 3.1 were also checked: their matching ignores the port, compares case-sensitively, and truncates a bracketed IPv6 literal at its first colon, so a trusted [::1] also matches [::2]. Flask raises the TRUSTED_HOSTS rejection after before_request hooks have run.

Setting: web.allowed_hosts in config.yaml, or repeated --allowed-host options, which replace the config list. Entries are host names or addresses with an optional port; IPv6 addresses go in brackets. A port-less entry also accepts the serving port; an entry with a port accepts only that port. The list replaces the loopback default. Invalid entries stop serve before the sanitizer starts. Serve prints the effective list at startup and, for a non-loopback bind with nothing configured, says that only loopback names are accepted.

For TASK-137: app.config["allowed_hosts"] holds the exact accepted Host values in canonical form (lowercase, IPv6 compressed, port without leading zeros). normalize_host() in ownmail/web_hosts.py canonicalizes a Host value the same way, so the netloc of a parsed Origin can be compared with that list. X-Forwarded-* headers are not read.

Tests: tests/test_web_hosts.py covers foreign Hosts on pages, static files, favicon, attachments, JSON endpoints, unknown paths and a POST /empty-trash whose Origin matches the foreign Host; absent Host; loopback defaults with and without the serving port; other ports; IPv6 literals; case; configured entries with and without ports; invalid entries; and serve startup output. The live-browser helper in tests/test_image_blocking.py now allows its random serving port the same way serve does.

Follow-up (2026-10-10):
- resolve_allowed_hosts rejects a serving port outside 1-65535, so `serve --port 0` exits 1 before the sanitizer starts. Before, create_app rejected the derived `localhost:0` only after the sanitizer worker was running.
- The browser tab opened at startup now uses an allowed Host. A wildcard bind opens the first allowed loopback name, then any allowed host on the serving port; a specific bind opens its own address. If none is allowed, serve prints that and opens nothing, instead of a page that gets 400.
- tests/test_web_hosts.py covers the port refusal and the browser-tab matrix.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Requests whose Host is not in a configured allowlist now get a plain-text 400 before any route, static file or JSON endpoint runs. With nothing configured, only localhost, 127.0.0.1 and [::1] are accepted, with or without the serving port. web.allowed_hosts and --allowed-host set other names, serve prints the effective list, and the setup guide covers LAN and reverse-proxy use. Existing LAN deployments must list their address before upgrading.
<!-- SECTION:FINAL_SUMMARY:END -->
