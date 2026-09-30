"""HTML sanitizer using DOMPurify via a Node.js sidecar process.

Provides server-side HTML/CSS sanitization for email content before
rendering in the browser. Communicates with a long-lived Node.js child
process over stdin/stdout using newline-delimited JSON.

If Node.js is not available, the web server refuses to start.
"""

from __future__ import annotations

import html as html_module
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path

from ownmail.download_lock import LockHeld, ProcessLock

logger = logging.getLogger(__name__)

# Directory containing this module (and worker.js, package.json)
_SANITIZER_DIR = os.path.dirname(os.path.abspath(__file__))

# A last resort: the network limits below end most failed installs sooner.
_NPM_TIMEOUT = 300  # seconds
# npm waits up to 5 minutes for a stalled download and about 70 seconds for
# retries by default. Failing sooner lets npm roll back and report its own error.
_NPM_NETWORK_ARGS = ["--fetch-timeout=30000", "--fetch-retries=1", "--fetch-retry-mintimeout=2000"]
_NPM_ERROR_CODE = re.compile(r"^npm (?:error|ERR!) code (\S+)", re.MULTILINE)
_NPM_NETWORK_CODES = {
    "ECONNABORTED",
    "ECONNREFUSED",
    "ECONNRESET",
    "EAI_AGAIN",
    "EAI_FAIL",
    "EHOSTUNREACH",
    "ENETDOWN",
    "ENETUNREACH",
    "ENOTFOUND",
    "ETIMEDOUT",
}
# Written to node_modules, holding the npm scope, while npm runs. An install
# stopped partway can leave half-written packages that npm cannot repair, so a
# start that finds the marker installs again from an empty node_modules.
_INSTALL_MARKER = ".ownmail-install-incomplete"
# npm writes this at the end of every install that completes.
_NPM_HIDDEN_LOCKFILE = ".package-lock.json"
# The only range form _satisfies understands; a test keeps package.json to it.
_CARET_RANGE = re.compile(r"\^([1-9]\d*)\.(\d+)\.(\d+)")
# npm ignores build metadata; a prerelease version does not match.
_RELEASE_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:\+[0-9A-Za-z.-]+)?")

_NODE_MISSING = (
    "Node.js was not found.\n"
    "Install a Node.js LTS release with npm from https://nodejs.org, then run ownmail serve again."
)


def _caret_floor(spec: str) -> tuple[int, ...] | None:
    """The lowest version a range such as ^3.4.16 allows, or None for any other range."""
    match = _CARET_RANGE.fullmatch(spec)
    return tuple(int(part) for part in match.groups()) if match else None


def _satisfies(version: object, spec: str) -> bool:
    """Whether an installed version is within a package.json range, as far as _caret_floor understands it."""
    floor = _caret_floor(spec)
    match = _RELEASE_VERSION.fullmatch(version) if isinstance(version, str) else None
    if not floor or not match:
        return False
    installed = tuple(int(part) for part in match.groups())
    return installed >= floor and installed[0] == floor[0]


def _installed_version(name: str) -> object:
    """The version in an installed package's package.json, or None if it cannot be read."""
    try:
        with open(os.path.join(_SANITIZER_DIR, "node_modules", name, "package.json"), encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _unmet(dependencies: dict) -> list[str]:
    """Name each dependency whose installed version is outside its package.json range."""
    return [name for name, spec in dependencies.items() if not _satisfies(_installed_version(name), spec)]


def _recorded_scope(marker: str) -> str | None:
    """The npm scope an unfinished install recorded in its marker, or None."""
    try:
        with open(marker, encoding="utf-8") as f:
            scope = f.read()
    except OSError:
        return None
    return scope if scope in ("--include=dev", "--omit=dev") else None


def _unfinished(node_modules: str) -> bool:
    """Whether an install left its marker and npm has not completed one since, such as by hand."""
    try:
        started = os.stat(os.path.join(node_modules, _INSTALL_MARKER)).st_mtime_ns
    except OSError:
        return False
    try:
        return os.stat(os.path.join(node_modules, _NPM_HIDDEN_LOCKFILE)).st_mtime_ns <= started
    except OSError:
        return True


def _clear(node_modules: str) -> None:
    """Delete everything in node_modules but the install marker, so an interrupted delete still leaves it."""
    for entry in os.scandir(node_modules):
        if entry.name == _INSTALL_MARKER:
            continue
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path)
        else:
            os.remove(entry.path)


class HtmlSanitizer:
    """HTML sanitizer backed by DOMPurify running in a Node.js sidecar.

    Usage:
        sanitizer = HtmlSanitizer()
        sanitizer.start()
        try:
            clean_html, needs_padding, supports_dark = sanitizer.sanitize(dirty_html)
        finally:
            sanitizer.stop()

    If Node.js or the worker's dependencies are unavailable, start() leaves
    the sanitizer unavailable with the reason in error, and sanitize()
    returns the HTML escaped.
    """

    def __init__(self, timeout: float = 5.0, verbose: bool = False):
        """Initialize sanitizer.

        Args:
            timeout: Seconds to wait for sanitization response.
            verbose: Print detailed timing and activity logs.
        """
        self._process: subprocess.Popen | None = None
        self._timeout = timeout
        self._verbose = verbose
        self._lock = threading.Lock()
        self._request_id = 0
        self._available = False
        self._error: str | None = None
        self._stderr_thread: threading.Thread | None = None

    @staticmethod
    def is_node_available() -> bool:
        """Check if Node.js is installed and accessible."""
        return shutil.which("node") is not None

    def _ensure_deps(self, install: bool = True) -> bool:
        """Make the installed npm dependencies meet package.json.

        npm runs only when a dependency is missing or outside its range, or
        an earlier install did not finish. With install False, that is
        reported instead.

        Returns True if deps are ready. On failure, sets error.
        """
        try:
            with open(os.path.join(_SANITIZER_DIR, "package.json"), encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, ValueError) as e:
            self._error = f"The sanitizer's package.json could not be read ({e}).\nReinstall ownmail."
            return False
        dependencies = manifest.get("dependencies", {})
        unmet = _unmet(dependencies)
        if not unmet and not _unfinished(os.path.join(_SANITIZER_DIR, "node_modules")):
            return True

        if not install:
            self._error = (
                "The sanitizer dependencies changed while ownmail serve was running.\n"
                "Restart ownmail serve to install them."
            )
            return False

        names = ", ".join(unmet or dependencies)
        npm = shutil.which("npm")
        if not npm:
            self._error = (
                f"npm was not found, so the sanitizer dependencies ({names}) could not be installed.\n"
                "Install Node.js with npm from https://nodejs.org, then run ownmail serve again."
            )
            return False

        try:
            with ProcessLock(Path(_SANITIZER_DIR, ".install.lock")):
                return self._install(npm, manifest)
        except LockHeld:
            self._error = (
                "Another ownmail process is installing the sanitizer dependencies.\n"
                "Wait for it to finish, then run ownmail serve again."
            )
        except OSError as e:
            self._error = (
                f"The sanitizer dependencies ({names}) could not be installed ({e}).\n"
                f"Check that {_SANITIZER_DIR} is writable, then run ownmail serve again."
            )
        return False

    def _install(self, npm: str, manifest: dict) -> bool:
        """Run npm install while holding the install lock. Returns True if deps are ready."""
        dependencies = manifest.get("dependencies", {})
        node_modules = os.path.join(_SANITIZER_DIR, "node_modules")
        marker = os.path.join(node_modules, _INSTALL_MARKER)
        # Checked again under the lock, in case another process just finished.
        unfinished = _unfinished(node_modules)
        unmet = _unmet(dependencies)
        if not unmet and not unfinished:
            return True

        names = ", ".join(unmet or dependencies)
        # --omit=dev would remove the test dependencies of a development tree.
        dev = any(os.path.isdir(os.path.join(node_modules, name)) for name in manifest.get("devDependencies", {}))
        scope = _recorded_scope(marker) or ("--include=dev" if dev else "--omit=dev")
        if unfinished:
            print("📦 Reinstalling HTML sanitizer dependencies after an unfinished install...", flush=True)
            try:
                _clear(node_modules)
            except OSError as e:
                self._error = (
                    f"The sanitizer dependencies ({names}) could not be installed: "
                    f"an unfinished install could not be removed ({e}).\n"
                    f"Delete {node_modules}, then run ownmail serve again."
                )
                return False
        elif os.path.isdir(node_modules):
            print(f"📦 Updating HTML sanitizer dependencies ({names}) from npm...", flush=True)
        else:
            print("📦 Installing HTML sanitizer dependencies from npm (one-time setup)...", flush=True)

        try:
            os.makedirs(node_modules, exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write(scope)
        except OSError as e:
            hint = f"Check that {_SANITIZER_DIR} is writable"
            return self._install_failed(names, f"the install could not start ({e})", hint, scope)
        try:
            result = subprocess.run(
                [npm, "install", scope, "--no-fund", "--no-audit", "--no-update-notifier", *_NPM_NETWORK_ARGS],
                cwd=_SANITIZER_DIR,
                capture_output=True,
                text=True,
                timeout=_NPM_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            reason = f"npm install did not finish within {_NPM_TIMEOUT} seconds"
            return self._abandon(names, reason, "Check the internet connection", scope)
        except Exception as e:
            os.remove(marker)
            return self._install_failed(names, f"npm could not run ({e})", "Check the npm installation", scope)

        code = _NPM_ERROR_CODE.search(result.stderr)
        if result.returncode != 0:
            logger.warning("npm install failed (exit %d): %s", result.returncode, result.stderr.strip())
        if result.returncode < 0 or (result.returncode > 0 and not code):
            # A signal, or a crash without an error code, can stop npm before it rolls back.
            if result.returncode < 0:
                reason = f"npm install was stopped by signal {-result.returncode}"
            else:
                reason = f"npm install exited with code {result.returncode}"
            return self._abandon(names, reason, "Check the internet connection and the npm output above", scope)
        os.remove(marker)
        if result.returncode != 0:
            code = code[1]
            network = code in _NPM_NETWORK_CODES or code.endswith("TIMEOUT")
            hint = "Check the internet connection" if network else "Fix the npm error shown above"
            return self._install_failed(names, f"npm install failed with {code}", hint, scope)
        unmet = _unmet(dependencies)
        if unmet:
            reason = f"npm install finished but left {', '.join(unmet)} outside the package.json ranges"
            return self._install_failed(names, reason, "Check the npm configuration", scope)
        print("✓ HTML sanitizer dependencies installed")
        return True

    def _abandon(self, names: str, reason: str, hint: str, scope: str) -> bool:
        """Remove an install npm may have left half-written, then record why it failed. Returns False.

        The marker stays, so the next start installs with the same scope
        unless npm completes an install first.
        """
        try:
            _clear(os.path.join(_SANITIZER_DIR, "node_modules"))
        except OSError:
            pass  # The next start clears what is left.
        return self._install_failed(names, reason, hint, scope)

    def _install_failed(self, names: str, reason: str, hint: str, scope: str) -> bool:
        """Record why an install failed, with the command that installs by hand. Returns False."""
        command = ["npm", "--prefix", _SANITIZER_DIR, "install", scope]
        command = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
        self._error = (
            f"The sanitizer dependencies ({names}) could not be installed: {reason}.\n"
            f"{hint}, then run ownmail serve again, or install them with:\n"
            f"  {command}"
        )
        return False

    def _drain_stderr(self) -> None:
        """Read stderr from the worker in a background thread to prevent blocking."""
        try:
            assert self._process is not None
            assert self._process.stderr is not None
            for line in self._process.stderr:
                line = line.strip()
                if line:
                    logger.debug("[sanitizer] %s", line)
        except (ValueError, OSError):
            # Process closed
            pass

    def start(self, install: bool = True) -> None:
        """Start the DOMPurify sidecar process.

        Installs or updates its npm dependencies first, unless install is
        False. If Node.js is not available or setup fails, error says why
        and what to do, and sanitize() returns HTML escaped.
        """
        self._error = None
        if not self.is_node_available():
            self._error = _NODE_MISSING
            return

        if not self._ensure_deps(install):
            return

        worker_path = os.path.join(_SANITIZER_DIR, "worker.js")
        try:
            if self._verbose:
                print(f"[verbose] Starting sanitizer: node {worker_path}", flush=True)
            self._process = subprocess.Popen(
                ["node", worker_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=_SANITIZER_DIR,
                text=True,
                bufsize=1,  # Line-buffered
            )

            # Start stderr drain thread
            self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
            self._stderr_thread.start()

            # Wait for ready signal
            ready_line = self._process.stdout.readline()
            if ready_line:
                try:
                    msg = json.loads(ready_line)
                    if msg.get("ready"):
                        self._available = True
                        if self._verbose:
                            print("[verbose] HTML sanitizer sidecar ready (DOMPurify + jsdom)", flush=True)
                        logger.info("HTML sanitizer started (DOMPurify sidecar)")
                        return
                except json.JSONDecodeError:
                    pass

            # If we get here, the worker didn't signal ready
            self._kill_process()
            self._error = (
                "The sanitizer worker did not start. Check that Node.js is a supported LTS release (node --version).\n"
                f"If it is, delete {os.path.join(_SANITIZER_DIR, 'node_modules')} and run ownmail serve again "
                "to reinstall the sanitizer dependencies."
            )

        except FileNotFoundError:
            self._error = _NODE_MISSING
        except Exception as e:
            self._error = f"The sanitizer worker could not start ({e})."
            self._kill_process()

    def sanitize(self, html: str) -> tuple[str, bool, bool]:
        """Sanitize HTML content using DOMPurify.

        Args:
            html: Raw HTML string to sanitize.

        Returns:
            Tuple of (sanitized HTML, needs_padding, supports_dark_mode).
            Returns (escaped HTML, True, False) if sanitizer is unavailable or on error.
        """
        if not self._available or self._process is None:
            return html_module.escape(html), True, False

        with self._lock:
            self._request_id += 1
            req_id = self._request_id
            input_len = len(html)
            _t0 = time.monotonic() if self._verbose else None

            try:
                request = json.dumps({"id": req_id, "html": html}) + "\n"
                self._process.stdin.write(request)
                self._process.stdin.flush()

                # Read response with timeout
                start = time.monotonic()
                while True:
                    elapsed = time.monotonic() - start
                    if elapsed >= self._timeout:
                        logger.warning("HTML sanitization timed out after %.1fs", self._timeout)
                        self._restart()
                        return html_module.escape(html), True, False

                    line = self._process.stdout.readline()
                    if not line:
                        # Process died
                        logger.warning("HTML sanitizer process died unexpectedly")
                        self._restart()
                        return html_module.escape(html), True, False

                    try:
                        response = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from sanitizer: %s", line[:100])
                        continue

                    if response.get("id") == req_id:
                        if response.get("error"):
                            logger.warning("DOMPurify error: %s", response["error"])
                            return html_module.escape(html), True, False
                        result_html = response.get("html", html)
                        needs_padding = response.get("needsPadding", True)
                        supports_dark = response.get("supportsDarkMode", False)
                        if self._verbose:
                            elapsed_ms = (time.monotonic() - _t0) * 1000
                            print(
                                f"[verbose] Sanitized {input_len:,} chars → {len(result_html):,} chars in {elapsed_ms:.1f}ms",
                                flush=True,
                            )
                        return result_html, needs_padding, supports_dark

            except (BrokenPipeError, OSError) as e:
                logger.warning("Sanitizer communication error: %s", e)
                self._restart()
                return html_module.escape(html), True, False

    def _restart(self) -> None:
        """Restart the worker process after a failure.

        Never runs npm: an install would hold the lock that every render waits on.
        """
        self._kill_process()
        self._available = False
        try:
            self.start(install=False)
        except Exception as e:
            self._error = str(e)
        if self._error:
            logger.warning("Failed to restart HTML sanitizer: %s", self._error)

    def _kill_process(self) -> None:
        """Terminate the worker process."""
        if self._process is not None:
            try:
                self._process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
            except Exception:
                pass
            self._process = None

    def stop(self) -> None:
        """Stop the DOMPurify sidecar process."""
        self._available = False
        self._kill_process()
        logger.info("HTML sanitizer stopped")

    @property
    def available(self) -> bool:
        """Whether the sanitizer is running and available."""
        return self._available

    @property
    def error(self) -> str | None:
        """Why the last start() left the sanitizer unavailable and what to do, or None."""
        return self._error
