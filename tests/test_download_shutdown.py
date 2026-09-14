"""Server shutdown releases background download processes."""

import os
import select
import signal
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

from ownmail import web


@pytest.fixture
def server_parts(monkeypatch):
    manager = Mock()
    sanitizer = Mock(available=True)
    app = Mock(config={}, extensions={"downloads": manager})
    monkeypatch.setattr(web, "create_app", Mock(return_value=app))
    monkeypatch.setattr("ownmail.sanitizer.HtmlSanitizer", Mock(return_value=sanitizer))
    return app, manager, sanitizer


@pytest.fixture
def previous_handler():
    previous = Mock()
    original = signal.signal(signal.SIGTERM, previous)
    yield previous
    signal.signal(signal.SIGTERM, original)


@pytest.mark.parametrize("reload, child", [(False, False), (True, False), (True, True)])
def test_sigterm_cleans_up_and_restores_handler(server_parts, previous_handler, monkeypatch, reload, child):
    app, manager, sanitizer = server_parts
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    if child:
        monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")

    def serve(**kwargs):
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        assert handler is not previous_handler
        if reload:
            # Werkzeug replaces the handler with its own SystemExit callback.
            def reloader_exit(signum, frame):
                raise SystemExit(0)

            signal.signal(signal.SIGTERM, reloader_exit)
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    app.run.side_effect = serve
    with pytest.raises(SystemExit) as exc:
        web.run_server(Mock(), reload=reload, open_browser=False)
    assert exc.value.code == 0
    assert manager.start_scheduler.call_count == int(not reload or child)
    manager.stop.assert_called_once()
    sanitizer.stop.assert_called_once()
    assert signal.getsignal(signal.SIGTERM) is previous_handler


@pytest.mark.parametrize("failure", ["start", "run", "download_stop", "sanitizer_stop"])
def test_shutdown_restores_handler_even_if_a_component_raises(server_parts, previous_handler, failure):
    app, manager, sanitizer = server_parts
    operation = {
        "start": manager.start_scheduler,
        "run": app.run,
        "download_stop": manager.stop,
        "sanitizer_stop": sanitizer.stop,
    }[failure]
    operation.side_effect = RuntimeError("component failed")
    with pytest.raises(RuntimeError, match="component failed"):
        web.run_server(Mock(), open_browser=False)
    manager.stop.assert_called_once()
    sanitizer.stop.assert_called_once()
    assert signal.getsignal(signal.SIGTERM) is previous_handler


def test_server_in_worker_thread_leaves_process_signals_alone(server_parts, previous_handler):
    app, manager, sanitizer = server_parts
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(web.run_server, Mock(), open_browser=False).result(timeout=2)
    app.run.assert_called_once()
    manager.stop.assert_called_once()
    sanitizer.stop.assert_called_once()
    assert signal.getsignal(signal.SIGTERM) is previous_handler


@pytest.mark.skipif(os.name == "nt", reason="Exercises POSIX SIGTERM and detached child processes")
def test_sigterm_reaps_real_detached_download(tmp_path):
    script = tmp_path / "server.py"
    marker = tmp_path / "download-stopped"
    child_code = textwrap.dedent("""\
        import os
        import signal
        import sys
        from pathlib import Path

        def stop(signum, frame):
            Path(sys.argv[1]).write_text(str(signum))
            raise SystemExit(0)

        signal.signal(signal.SIGINT, stop)
        print(f"CHILD_READY:{os.getpid()}", flush=True)
        while True:
            signal.pause()
        """)
    script.write_text(
        textwrap.dedent("""\
        import os
        import signal
        import subprocess
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock

        from ownmail import downloads, sanitizer, web

        marker = sys.argv[1]
        child_code = sys.argv[2]
        real_popen = subprocess.Popen
        downloads.subprocess.Popen = lambda args, **kwargs: real_popen(
            [sys.executable, "-c", child_code, marker], **kwargs
        )
        manager = downloads.DownloadManager(Path(marker).parent, "synthetic-config.yaml")

        def serve(**kwargs):
            assert manager.start_download()
            while True:
                signal.pause()

        app = SimpleNamespace(config={}, extensions={"downloads": manager}, run=serve)
        web.create_app = lambda *args, **kwargs: app
        sanitizer.HtmlSanitizer = lambda **kwargs: Mock(available=True)
        web.run_server(Mock(), open_browser=False)
        """)
    )
    server = subprocess.Popen(
        [sys.executable, "-u", str(script), str(marker), child_code],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    child_pid = None
    try:
        deadline = time.monotonic() + 10
        pending = b""
        while child_pid is None:
            ready, _, _ = select.select([server.stdout], [], [], max(0, deadline - time.monotonic()))
            assert ready, "Server did not start its synthetic download"
            chunk = os.read(server.stdout.fileno(), 4096)
            assert chunk, "Server exited before starting its synthetic download"
            lines = (pending + chunk).split(b"\n")
            pending = lines.pop()
            for line in lines:
                if line.startswith(b"CHILD_READY:"):
                    child_pid = int(line.partition(b":")[2])
                    break
        os.kill(server.pid, signal.SIGTERM)
        output, _ = server.communicate(timeout=15)
        assert server.returncode == 0, output
        assert marker.read_text() == str(signal.SIGINT)
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=5)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
