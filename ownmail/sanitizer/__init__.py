"""HTML sanitizer using DOMPurify via a Node.js sidecar process.

Provides server-side HTML/CSS sanitization for email content before
rendering in the browser. Communicates with a long-lived Node.js child
process over stdin/stdout using newline-delimited JSON.

If Node.js is not available, degrades gracefully — the iframe sandbox
in the template still provides protection.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

# Directory containing this module (and worker.js, package.json)
_SANITIZER_DIR = os.path.dirname(os.path.abspath(__file__))


class HtmlSanitizer:
    """HTML sanitizer backed by DOMPurify running in a Node.js sidecar.

    Usage:
        sanitizer = HtmlSanitizer()
        sanitizer.start()
        try:
            clean_html = sanitizer.sanitize(dirty_html)
        finally:
            sanitizer.stop()

    If Node.js is not installed, start() logs a warning and sanitize()
    returns the original HTML unchanged.
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
        self._stderr_thread: threading.Thread | None = None

    @staticmethod
    def is_node_available() -> bool:
        """Check if Node.js is installed and accessible."""
        return shutil.which("node") is not None

    def _ensure_deps(self) -> bool:
        """Install npm dependencies if not already present.

        Returns True if deps are ready, False on failure.
        """
        node_modules = os.path.join(_SANITIZER_DIR, "node_modules")
        if os.path.isdir(node_modules):
            return True

        npm = shutil.which("npm")
        if not npm:
            logger.warning(
                "npm not found — cannot install HTML sanitizer dependencies. "
                "Install Node.js (https://nodejs.org) for HTML sanitization."
            )
            return False

        print("📦 Installing HTML sanitizer dependencies (one-time setup)...")
        try:
            result = subprocess.run(
                [npm, "install", "--production", "--no-fund", "--no-audit"],
                cwd=_SANITIZER_DIR,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning(
                    "npm install failed (exit %d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                if self._verbose:
                    print(f"[verbose] npm install stderr: {result.stderr.strip()}", flush=True)
                return False
            print("✓ HTML sanitizer ready")
            return True
        except subprocess.TimeoutExpired:
            logger.warning("npm install timed out after 60 seconds")
            return False
        except Exception as e:
            logger.warning("npm install failed: %s", e)
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

    def start(self) -> None:
        """Start the DOMPurify sidecar process.

        If Node.js is not available or setup fails, sanitize() will
        return HTML unchanged (graceful degradation).
        """
        if not self.is_node_available():
            logger.warning(
                "Node.js not found — HTML sanitization disabled. "
                "Install Node.js (https://nodejs.org) for sanitized email rendering."
            )
            return

        if not self._ensure_deps():
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
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, daemon=True
            )
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
            logger.warning("HTML sanitizer worker did not send ready signal")
            self._kill_process()

        except FileNotFoundError:
            logger.warning("Node.js not found — HTML sanitization disabled")
        except Exception as e:
            logger.warning("Failed to start HTML sanitizer: %s", e)
            self._kill_process()

    def sanitize(self, html: str) -> tuple[str, bool]:
        """Sanitize HTML content using DOMPurify.

        Args:
            html: Raw HTML string to sanitize.

        Returns:
            Tuple of (sanitized HTML string, needs_padding bool).
            Returns (original HTML, True) if sanitizer is unavailable or on error.
        """
        if not self._available or self._process is None:
            return html, True

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
                        logger.warning(
                            "HTML sanitization timed out after %.1fs", self._timeout
                        )
                        self._restart()
                        return html, True

                    line = self._process.stdout.readline()
                    if not line:
                        # Process died
                        logger.warning("HTML sanitizer process died unexpectedly")
                        self._restart()
                        return html, True

                    try:
                        response = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from sanitizer: %s", line[:100])
                        continue

                    if response.get("id") == req_id:
                        if response.get("error"):
                            logger.warning(
                                "DOMPurify error: %s", response["error"]
                            )
                            return html, True
                        result_html = response.get("html", html)
                        needs_padding = response.get("needsPadding", True)
                        if self._verbose:
                            elapsed_ms = (time.monotonic() - _t0) * 1000
                            print(
                                f"[verbose] Sanitized {input_len:,} chars → {len(result_html):,} chars in {elapsed_ms:.1f}ms",
                                flush=True,
                            )
                        return result_html, needs_padding

            except (BrokenPipeError, OSError) as e:
                logger.warning("Sanitizer communication error: %s", e)
                self._restart()
                return html, True

    def _restart(self) -> None:
        """Restart the worker process after a failure."""
        self._kill_process()
        self._available = False
        try:
            self.start()
        except Exception as e:
            logger.warning("Failed to restart HTML sanitizer: %s", e)

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
