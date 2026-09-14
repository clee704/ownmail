"""Download process locking and CLI status contracts."""

import errno
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ownmail.cli import main
from ownmail.download_lock import DownloadInProgress, DownloadLock


def test_competing_download_process_exits_before_opening_archive(tmp_path):
    archive_root = tmp_path / "archive"
    alias = tmp_path / "alias"
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n")
    with DownloadLock(archive_root):
        alias.symlink_to(archive_root, target_is_directory=True)
        result = subprocess.run(
            [sys.executable, "-m", "ownmail", "--config", str(config_path), "--archive-root", str(alias), "download"],
            capture_output=True,
            text=True,
            timeout=15,
        )

    assert result.returncode == 75, result.stderr + result.stdout
    assert "already running" in result.stdout
    assert not (archive_root / "ownmail.db").exists()
    with DownloadLock(alias):
        assert (archive_root / ".download.lock").exists()


def test_terminated_process_does_not_leave_archive_locked(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; from pathlib import Path; from ownmail.download_lock import DownloadLock; "
            "lock = DownloadLock(Path(sys.argv[1])); lock.__enter__(); os._exit(42)",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 42, result.stderr
    with DownloadLock(tmp_path):
        pass


@pytest.mark.parametrize("result", [True, False, KeyboardInterrupt(), RuntimeError("failed"), SystemExit(7)])
def test_main_holds_lock_through_download_and_releases_on_exit(tmp_path, monkeypatch, result):
    monkeypatch.setattr(sys, "argv", ["ownmail", "--archive-root", str(tmp_path), "download"])

    def download(*args):
        with pytest.raises(DownloadInProgress):
            with DownloadLock(tmp_path):
                pytest.fail("The download did not hold its archive lock")
        if isinstance(result, BaseException):
            raise result
        return result

    with patch("ownmail.cli.load_config", return_value={}):
        with patch("ownmail.cli.EmailArchive"):
            with patch("ownmail.cli.cmd_download", side_effect=download):
                if result is True:
                    assert main() is None
                else:
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == (7 if isinstance(result, SystemExit) else 1)

    lock_path = tmp_path / ".download.lock"
    inode = lock_path.stat().st_ino
    with DownloadLock(tmp_path):
        assert lock_path.stat().st_ino == inode


def test_failed_archive_initialization_releases_download_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ownmail", "--archive-root", str(tmp_path), "download"])
    with patch("ownmail.cli.load_config", return_value={}):
        with patch("ownmail.cli.EmailArchive", side_effect=OSError("unavailable")):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code == 1
    with DownloadLock(tmp_path):
        pass


@pytest.mark.parametrize("error", [None, OSError(errno.EACCES, "busy"), OSError(errno.ENOSYS, "unsupported")])
def test_windows_lock_uses_nonblocking_byte_lock_and_closes_file(tmp_path, monkeypatch, error):
    msvcrt = MagicMock()
    descriptors = []

    def locking(descriptor, mode, count):
        descriptors.append(descriptor)
        assert mode == msvcrt.LK_NBLCK
        assert count == 1
        assert os.lseek(descriptor, 0, os.SEEK_CUR) == 0
        if error:
            raise error

    msvcrt.locking.side_effect = locking
    monkeypatch.setitem(sys.modules, "msvcrt", msvcrt)
    monkeypatch.setattr(sys, "platform", "win32")
    if error:
        expected = DownloadInProgress if error.errno == errno.EACCES else OSError
        with pytest.raises(expected):
            with DownloadLock(tmp_path):
                pytest.fail("Lock acquisition should have failed")
    else:
        with DownloadLock(tmp_path):
            assert descriptors
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


@pytest.mark.parametrize("location", ["explicit", "cwd", "script", "missing"])
def test_serve_receives_effective_config_path(tmp_path, monkeypatch, location):
    script_dir = tmp_path / "script"
    script_dir.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr("ownmail.cli.SCRIPT_DIR", script_dir)
    script_config = script_dir / "config.yaml"
    if location != "missing":
        script_config.write_text("web: {brand_name: Script}\n")
    cwd_config = cwd / "config.yaml"
    if location in ("explicit", "cwd"):
        cwd_config.write_text("web: {brand_name: Working}\n")
    args = ["ownmail"]
    expected = {"cwd": cwd_config, "script": script_config, "missing": None}.get(location)
    if location == "explicit":
        expected = cwd / "chosen.yaml"
        expected.write_text("web: {brand_name: Explicit}\n")
        args += ["--config", "chosen.yaml"]
    args += ["serve", "--no-browser"]
    monkeypatch.setattr(sys, "argv", args)

    with patch("ownmail.cli.EmailArchive") as archive:
        with patch("ownmail.web.run_server") as run_server:
            main()

    assert run_server.call_args.args[8] == expected
    expected_brand = {"explicit": "Explicit", "cwd": "Working", "script": "Script", "missing": "ownmail"}[location]
    assert run_server.call_args.args[11] == expected_brand
    if expected:
        assert isinstance(expected, Path)
        assert archive.call_args.args[1]["web"]["brand_name"] == expected_brand
