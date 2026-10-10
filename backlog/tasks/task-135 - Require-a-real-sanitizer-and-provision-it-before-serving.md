---
id: TASK-135
title: Require a real sanitizer and provision it before serving
status: To Do
assignee: []
created_date: '2026-10-10 05:32'
labels:
  - security
dependencies: []
references:
  - ownmail/web.py
  - ownmail/sanitizer/__init__.py
  - README.md
priority: medium
type: bug
ordinal: 9910
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
create_app (ownmail/web.py) uses _PassthroughSanitizer, which returns message HTML unchanged, when no sanitizer is passed. run_server starts HtmlSanitizer, refuses to serve when it is unavailable and passes it in, so `ownmail serve` is safe today. Any other construction path, such as a WSGI factory for a production server, would embed unsanitized sender HTML by default.

run_server also calls HtmlSanitizer.start() with installation enabled, so serving startup runs npm install when sanitizer packages are missing or outside their ranges (_ensure_deps and _install in ownmail/sanitizer/__init__.py). That fetches and writes code while the service starts.

Make every construction path fail closed: create_app requires an available sanitizer, and the passthrough moves to the test suite. Serving starts the sanitizer with `start(install=False)` and refuses with repair guidance when dependencies are not provisioned; an explicit step provisions them beforehand. README currently documents installation on first launch and needs updating.

Choosing a production WSGI server is a separate decision. Adding one as a runtime dependency is a STOP item under AGENTS.md, and this task adds no dependency.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 create_app raises when no sanitizer is given or the given sanitizer is unavailable; no production module provides a passthrough, and tests pass a test-only passthrough explicitly.
- [ ] #2 `ownmail serve` never runs npm; with missing or out-of-range sanitizer dependencies it exits with a non-zero status and names the provisioning step.
- [ ] #3 An explicit provisioning step installs or refreshes sanitizer dependencies with the existing install locking and recovery, and README and setup docs describe it.
- [ ] #4 Regressions show create_app failing without a sanitizer and with an unavailable one, and serve refusing to start without invoking npm (subprocess mocked) when dependencies are unmet.
- [ ] #5 The full pre-push gate passes and no runtime dependency is added.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changes live request acceptance; confirm deployment with the maintainer before landing.

Open decisions for the maintainer:
- Where provisioning happens: a dedicated command or the existing setup command. This reverses the install-on-serve behavior documented in README and kept by TASK-118 and TASK-127.
- Which production WSGI server to support, if any. A new runtime dependency needs sign-off and lands through a PR.
- Whether serve should refuse or warn when --reload or --debug is combined with a non-loopback --host.
<!-- SECTION:NOTES:END -->
