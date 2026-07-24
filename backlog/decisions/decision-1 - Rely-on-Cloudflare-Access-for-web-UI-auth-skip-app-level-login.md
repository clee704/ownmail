---
id: decision-1
title: 'Rely on Cloudflare Access for web UI auth, skip app-level login'
date: '2026-07-24 04:14'
status: Accepted
---
## Context

`web.py` has no built-in authentication. `SECURITY_AUDIT.md` (2026-02-09) rated this
Low severity and acceptable because the server binds to `127.0.0.1` by default — not
network-exposed out of the box.

`AUTH_PLAN.md` proposed adding session-based login directly to the app: username +
scrypt password hash in `config.yaml`, a `/login` form, Flask session cookies, a
`set-password` CLI command. Written assuming the app would be reachable through a
Cloudflare Tunnel.

That assumption undersold what Cloudflare provides. **Cloudflare Tunnel** by itself is
just transport (HTTPS termination + hiding the origin IP) — it does not gate access at
all. **Cloudflare Access** (Zero Trust, free up to 50 users) is the actual auth layer:
attached to a tunnel, it requires an identity check (email OTP or SSO) before any
request reaches the origin.

## Decision

Do not implement `AUTH_PLAN.md`. For this single-user personal tool, put the web UI
behind a Cloudflare Tunnel with a Cloudflare Access policy attached, and let Cloudflare
own login, session, and logout at the edge instead of hand-rolling it in Flask.

## Consequences

- `AUTH_PLAN.md` is superseded and removed; no `/login` route, no password hash in
  `config.yaml`, no `set-password` command.
- ownmail keeps binding to `127.0.0.1` by default (per `SECURITY_AUDIT.md`) — it has no
  auth of its own. All access control for non-local use lives in Cloudflare config, not
  in this repo.
- Single point of failure: if the Access policy is ever removed or misconfigured on the
  tunnel, the app is wide open to anyone with the URL, with no app-level fallback.
  Mitigate by treating the Access policy as the thing to double-check after any tunnel
  config change, not by re-opening this decision.
- If a real pain point with Cloudflare Access shows up later (e.g. needing per-route
  policies, or dropping Cloudflare entirely), revisit — but don't re-litigate absent a
  concrete driver, same bar applied to TASK-1's other no-gos.

