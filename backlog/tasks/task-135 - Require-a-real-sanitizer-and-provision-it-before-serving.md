---
id: TASK-135
title: Require a real sanitizer and provision it before serving
status: Done
assignee: []
created_date: '2026-10-10 05:32'
updated_date: '2026-10-10 06:06'
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
- [x] #1 create_app raises when no sanitizer is given or the given sanitizer is unavailable; no production module provides a passthrough, and tests pass a test-only passthrough explicitly.
- [x] #2 `ownmail serve` never runs npm; with missing or out-of-range sanitizer dependencies it exits with a non-zero status and names the provisioning step.
- [x] #3 An explicit provisioning step installs or refreshes sanitizer dependencies with the existing install locking and recovery, and README and setup docs describe it.
- [x] #4 Regressions show create_app failing without a sanitizer and with an unavailable one, and serve refusing to start without invoking npm (subprocess mocked) when dependencies are unmet.
- [x] #5 The full pre-push gate passes and no runtime dependency is added.
- [x] #6 `ownmail serve --reload` with a non-loopback --host prints a warning and still starts; --debug with a non-loopback host stays refused.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changes live request acceptance; confirm deployment with the maintainer before landing.

Open decisions for the maintainer:
- Where provisioning happens: a dedicated command or the existing setup command. This reverses the install-on-serve behavior documented in README and kept by TASK-118 and TASK-127.
- Which production WSGI server to support, if any. A new runtime dependency needs sign-off and lands through a PR.
- Whether serve should refuse or warn when --reload or --debug is combined with a non-loopback --host.

Maintainer decisions, 2026-10-09:
- Provisioning moves into the existing `ownmail setup` command. `ownmail serve` never runs npm; with missing or out-of-range packages it refuses to start and names `ownmail setup`.
- Every production construction path fails closed without a real sanitizer; the passthrough is reachable only through an explicit test-only helper.
- With --reload or --debug on a non-loopback host, serve prints a warning but still starts, since refusing would break existing deployments. A later change may tighten this.
- Choosing and adding a production WSGI server stays out of scope; no dependency is added.

Implementation, 2026-10-09:
- create_app raises ValueError unless it receives an available sanitizer, before any startup work. The passthrough moved from ownmail/web.py to tests/conftest.py (PassthroughSanitizer); web tests build apps through create_test_app, which passes it explicitly unless a test supplies its own sanitizer.
- HtmlSanitizer.start() and _ensure_deps() now default to install=False, and run_server passes install=False explicitly. Unmet or unfinished dependencies produce an error naming `ownmail setup --web`; serve prints it, refuses, and exits 1. Every repair hint that said to run ownmail serve again now names the setup step.
- `ownmail setup` runs credential setup and then the web step; `ownmail setup --web` (exclusive with --method) runs only the web step. That step calls start(install=True), reusing the existing install lock, unfinished-install marker, recovery and npm error reporting, then stops the worker. It exits 1 when the sanitizer is not ready.
- --reload on a non-loopback host adds a warning to the banner. --debug on a non-loopback host was already refused before this task because the Werkzeug debugger allows remote code execution; that refusal is kept, since no existing deployment can rely on it and loosening it would need its own decision.
- Tests and the suite never run npm: the integration fixtures start with install=False and skip with the setup guidance when dependencies are unmet. CI gains an `ownmail setup --web` step so the Python 3.10 and 3.11 jobs keep running the sanitizer integration tests; that step is not exercised locally.
- Existing deployments must run `ownmail setup --web` with the deployed environment's ownmail before restarting serve whenever the installed sanitizer packages might be missing or out of range (fresh or reinstalled environments, or a package.json floor raise).

Validation, 2026-10-09: the new regressions fail against the previous production code (19 failures, including serve calling the mocked npm once) and pass after the change. The full pre-push gate passed with browser tests running and no npm invocation. No dependency was added. Landing waits for maintainer confirmation because it changes deployed startup behavior.
<!-- SECTION:NOTES:END -->
