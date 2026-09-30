---
id: TASK-118
title: Refresh sanitizer dependencies when package.json changes
status: Done
assignee: []
created_date: '2026-09-29 06:39'
updated_date: '2026-09-30 02:48'
labels:
  - web
dependencies: []
priority: medium
type: bug
ordinal: 9750
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
HtmlSanitizer._ensure_deps runs npm install only when ownmail/sanitizer/node_modules is missing. An install that keeps that directory, such as a source checkout or an in-place package upgrade, keeps the versions resolved at its first launch even after package.json raises a floor. TASK-67 raised the DOMPurify and PostCSS floors because of published advisories, and those installs keep the flagged versions until node_modules is removed. TASK-67 found none of those advisories reachable once the worker ignores source-map comments, but a later fix may be. pipx reinstall recreates the environment and resolves current versions. package-lock.json is not tracked, so nothing records which versions an install should have.

The same path has two smaller problems. When the sanitizer fails to start, ownmail serve tells the user to run cd ownmail/sanitizer && npm install, which works only from a source checkout. The install passes npm's --production flag, which npm 11 reports as deprecated in favor of --omit=dev.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When installed dependencies no longer satisfy package.json, the next ownmail serve installs satisfying versions before starting the sanitizer, and an install that already satisfies it starts without running npm
- [x] #2 When the refresh cannot run (npm missing, offline or a failed install), the outcome is defined, reported to the user and covered by tests
- [x] #3 Startup guidance for a failed sanitizer install works for pipx and source installs, and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 654e88c.
1. Decide staleness without running npm: compare each package.json dependency with the version in node_modules/<name>/package.json using a caret-range check. No stamp file, so an install that already meets package.json never runs npm.
2. When a dependency is missing or outside its range, run npm install with --omit=dev (replacing the deprecated --production), keeping dev dependencies on a tree that already has them. Cap npm's network timeouts so it fails and rolls back by itself, mark each install in progress so one that is interrupted is redone from an empty node_modules, serialize installs with a process lock, and check the versions again afterwards. (Revised after the design review: SIGTERM does not make npm roll back while it downloads, so the plan's original timeout step was dropped.)
3. A refresh that cannot run leaves the sanitizer stopped, and serve keeps refusing to serve without it. The sanitizer records why and what to do, and serve prints that in place of the source-checkout-only command, naming the install directory so the guidance works for pipx and source installs.
4. Tests over a temporary sanitizer directory with a fake npm; a guard that the shipped package.json uses only ranges the check understands; README and setup docs for the network requirement after an update; the full pre-push gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Staleness check. Each `dependencies` entry in package.json is compared with the version in node_modules/<name>/package.json. Only ^X.Y.Z ranges with X >= 1 are understood. Prerelease versions and any other range count as unmet, and build metadata is ignored. test_shipped_package_json_is_checkable fails if package.json uses another range form, or gains a field such as overrides that the check would ignore. Only direct dependencies are checked, so a transitive floor is raised through the direct dependency that requires it, as TASK-67 did for nanoid through PostCSS. devDependencies are not checked: a Playwright bump still needs a manual npm install, and CONTRIBUTING.md says so. An install that meets package.json starts without running npm, and without npm installed.

Refresh. npm install --omit=dev replaces the deprecated --production. A tree that already has a devDependency directory uses --include=dev, because npm prunes omitted dependency types; this was verified to remove Playwright. --no-update-notifier keeps npm's upgrade notice out of the logged output. By default npm retries a refused connection for about 70 seconds and waits up to 5 minutes on a stalled download, both longer than the old 60-second limit, so an offline refresh would always have ended in ownmail's timeout with no reason. With --fetch-timeout=30000 --fetch-retries=1 --fetch-retry-mintimeout=2000, npm fails and rolls back by itself. Offline with an empty npm cache, a refresh now fails in about 2.5 seconds with ECONNREFUSED and leaves the old tree intact. ownmail's own limit is 300 seconds, a last resort. Versions are checked again after npm exits 0. With the local package-lock.json and a warm npm cache, a refresh can succeed offline.

Interrupted installs. On SIGTERM or SIGINT, npm defers its rollback until the current reify step ends, and after SIGKILL it cannot roll back at all. The design review reproduced a killed refresh that left retired .name-hash directories and half-written packages; every later npm install then failed with ENOTEMPTY. ownmail therefore writes node_modules/.ownmail-install-incomplete, holding the npm scope, before npm runs. It removes the marker only when npm exits by itself with a result npm rolls back from: exit 0, or an error that carries an npm error code. After a timeout, a signal, or a crash without an error code, ownmail clears node_modules down to the marker. For example, npm 10 offline with an existing lockfile crashes with "Exit handler never called!" and leaves empty package directories. A start that finds the marker clears node_modules, keeping the marker so an interrupted delete still leaves it, and installs again with the recorded scope. The exception is when npm has completed an install since the marker was written. npm rewrites node_modules/.package-lock.json at the end of every completed install, so running the printed manual command resolves the marker. Ctrl-C leaves the marker in place. A resolved marker stays until the next install replaces it. A ProcessLock, extracted from DownloadLock, serializes installs. A second ownmail process that needs to install while another is installing is refused with a message to wait, and each process checks the state again under the lock. Restarts while serving never run npm, because the render lock would be held for the whole install. Instead they report that the dependencies changed and that ownmail serve needs a restart.

Failure outcome. A refresh that cannot run leaves the sanitizer stopped, and ownmail serve refuses to start, as it already did without a sanitizer. Serving with the old versions was rejected. The package.json floors are the versions the worker was validated against, raised in TASK-67 for advisories, and DOMPurify ignores configuration keys it does not know, so a newer worker on an older tree could lose protections without any warning. The cost is that the first launch after an update that raises a floor needs the network; the .eml files and ownmail search still work offline. The refusal now happens right after the sanitizer starts, before create_app and the banner. A refused serve therefore no longer prints "Running at:" or auto-expires trash.

Reporting. HtmlSanitizer.error holds the cause and what to do. start() stores failures there instead of logging them, and serve prints the text inside its refusal. There are messages for:
- Node.js missing
- npm missing, naming the unmet packages
- an npm error code, in either the "npm error" or "npm ERR!" form, with a network hint for connection and timeout codes
- a crash or a signal
- a failed post-install check
- an unwritable directory
- an unfinished install that cannot be removed
- another process installing
- a worker that did not start: check that Node.js is an LTS release, otherwise delete node_modules to reinstall
- a restart

npm failures end with npm --prefix <sanitizer dir> install <same scope>, quoted for the shell (list2cmdline on Windows), which works for pipx and source installs. npm's stderr is still logged at warning, the duplicate verbose print was removed, and _restart logs its error.

Tests. The 13 earlier _ensure_deps tests patched os.path.isdir and subprocess.run globally but not the sanitizer directory. On a stale tree, several of them reached a real npm run in the checkout. They were replaced, along with 4 start() tests that duplicated TestSanitizerLifecycle. TestSanitizerDeps runs over a temporary sanitizer directory whose name contains a space, and subprocess.run fails unless the test fakes npm. The fake checks that npm runs under a marker recording its scope. The review mutation-tested the first version: 75 mutants, 24 survivors. Every survivor that changes behavior now fails a test, covering install propagation, literal npm arguments, network codes, error-code parsing, the manual command's scope and the refusal output. The exceptions are the equivalent mutants and flush=True on the progress lines. 12 further mutants of the revised marker, lock and crash handling were all killed.

Verification with real npm 10.9.7 on a scratch copy of the sanitizer directory:
- A stale refresh took 1.4 seconds and kept Playwright.
- An offline refresh failed in 2.5 seconds with ECONNREFUSED and rolled back.
- An offline rebuild crash cleared the tree down to the marker, and the next online start reinstalled with Playwright.
- After a timeout kill, the printed manual command left the next start with no npm run.
- Of two concurrent starts, the second was refused and the tree was untouched.

ownmail serve on the development tree served with npm off PATH, and with Node.js off PATH it refused before the banner. A non-editable install into a fresh virtual environment, which is what pipx does, ships no node_modules; its first serve installed into site-packages. With a stale tree there and no network, serve refused and printed the site-packages path. That command, run from another directory, fixed the tree, and the next serve started without npm. Full pre-push gate with required browser tests: 3923 passed, 1 expected failure, 96.49% coverage.

Limits. Windows was not tested: there subprocess.run's timeout kills only the npm.cmd wrapper. A tree left broken by an npm run killed before this change has no marker, so its worker fails to start, and the message suggests deleting node_modules. Filed TASK-121 (show the worker's startup error), TASK-122 (exit non-zero when serve refuses) and TASK-123 (remaining duplicate sanitizer tests).
<!-- SECTION:NOTES:END -->
