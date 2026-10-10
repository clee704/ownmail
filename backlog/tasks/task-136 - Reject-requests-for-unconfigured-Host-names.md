---
id: TASK-136
title: Reject requests for unconfigured Host names
status: To Do
assignee: []
created_date: '2026-10-10 05:32'
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
- [ ] #1 A configurable allowed-hosts setting applies to every route, including static files and JSON endpoints; any other Host value gets 400 before route code runs.
- [ ] #2 The default when nothing is configured follows the decision recorded in the notes, and serve prints the effective allowed hosts at startup.
- [ ] #3 Test-client regressions reject a synthetic foreign Host (rebind.invalid) for GET and POST, including a POST whose Origin matches that Host, and accept configured hosts with and without an explicit port.
- [ ] #4 Setup documentation describes the setting and its use behind a reverse proxy.
- [ ] #5 The full pre-push gate passes.
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
<!-- SECTION:NOTES:END -->
