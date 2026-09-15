"""Structured progress from the CLI subprocess through the web status API."""

import subprocess
import sys
import textwrap
import time
from unittest.mock import patch

import pytest

from ownmail.archive import EmailArchive
from ownmail.web import create_app
from ownmail.yaml_util import load_yaml


def wait_for_status(client, predicate):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get("/downloads")
        assert response.status_code == 200
        if predicate(response.json):
            return response.json
        time.sleep(0.02)
    raise AssertionError(f"Download status did not reach the expected state: {response.json}")


def test_live_counts_and_failure_survive_cli_completion(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "sources:\n"
        "  - {name: First, type: imap, account: first@example.com, host: mail.example.com, "
        "auth: {secret_ref: 'keychain:synthetic'}}\n"
        "  - {name: Second, type: imap, account: second@example.com, host: mail.example.com, "
        "auth: {secret_ref: 'keychain:synthetic'}}\n"
    )
    release = tmp_path / "continue-download"
    script = tmp_path / "synthetic_download.py"
    script.write_text(
        textwrap.dedent("""\
        import sys
        import time
        from pathlib import Path

        from ownmail.cli import main
        from ownmail.keychain import KeychainStorage
        from ownmail.live import LiveMessage, LiveSnapshot
        from ownmail.providers.imap import ImapProvider

        release = Path(sys.argv.pop(1))

        def forbid_credentials(*args):
            raise AssertionError("Synthetic download must not access credentials")

        def message(self, message_id):
            if message_id == "duplicate":
                time.sleep(0.3)
            if message_id == "deleted":
                deadline = time.monotonic() + 10
                while not release.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                if not release.exists():
                    raise RuntimeError("Test did not release the synthetic download")
                return None
            if message_id == "broken":
                raise RuntimeError("Synthetic private diagnostic: token=do-not-expose")
            raw = (
                "From: sender@example.com\\r\\nTo: recipient@example.com\\r\\n"
                "Date: Mon, 01 Jan 2024 12:00:00 +0000\\r\\n"
                f"Subject: Synthetic {self.source_name} message\\r\\n"
                f"Message-ID: <{self.source_name}@example.com>\\r\\n"
                "\\r\\nSynthetic body.\\r\\n"
            ).encode()
            return LiveMessage(message_id, identity_token=message_id, state="eligible", raw=raw)

        def listing(self):
            ids = ["saved", "duplicate", "deleted", "broken"] if self.source_name == "First" else ["saved"]
            return LiveSnapshot(self.source_name, self.account,
                [LiveMessage(message_id, identity_token=message_id, state="eligible") for message_id in ids],
                complete=True)

        KeychainStorage.load_imap_password = forbid_credentials
        ImapProvider.authenticate = lambda self: None
        ImapProvider.list_live_messages = listing
        ImapProvider.read_live_message = message
        ImapProvider.close = lambda self: None
        main()
        """)
    )
    archive = EmailArchive(tmp_path / "archive", load_yaml(config))
    app = create_app(archive, config_path=str(config))
    manager = app.extensions["downloads"]
    real_popen = subprocess.Popen

    def spawn(args, **kwargs):
        return real_popen([sys.executable, str(script), str(release), *args[3:]], **kwargs)

    try:
        with patch("ownmail.downloads.subprocess.Popen", side_effect=spawn):
            client = app.test_client()
            assert client.post("/downloads", json={}).status_code == 202
            live = wait_for_status(client, lambda s: s["running"] and s.get("skipped") == 1)
            assert live["has_progress"] is True
            assert (live["downloaded"], live["skipped"], live["errors"]) == (1, 1, 0)
            assert live["source"] == "First"
            assert live["phase"] == "refreshing"

            release.touch()
            final = wait_for_status(client, lambda s: not s["running"])
            assert final["state"] == "failed"
            assert final["has_progress"] is True
            assert final["active_complete"] is False
            assert (final["downloaded"], final["skipped"], final["errors"]) == (2, 2, 1)
            assert final["source"] == "Second"
            assert final["failure_reason"]
            assert "do-not-expose" not in str(final)
            assert "first@example.com" not in str(final)
            assert archive.db.get_email_count() == 2
            assert client.get("/downloads").json == final
    finally:
        release.touch()
        manager.stop()


@pytest.mark.parametrize(
    "configuration, reason",
    [("sources: []\n", "setup"), ("sources: [invalid YAML", "config")],
)
def test_startup_failure_reaches_settings_without_console_output(tmp_path, configuration, reason):
    config = tmp_path / "config.yaml"
    config.write_text(configuration)
    app = create_app(EmailArchive(tmp_path / "archive", {}), config_path=str(config))
    manager = app.extensions["downloads"]
    try:
        client = app.test_client()
        assert client.post("/downloads", json={}).status_code == 202
        final = wait_for_status(client, lambda s: not s["running"])
        assert final["state"] == "failed"
        assert final["has_progress"] is True
        assert final["downloaded"] == final["skipped"] == final["errors"] == 0
        assert reason in final["failure_reason"]
        assert str(tmp_path) not in str(final)
        assert "Traceback" not in str(final)
    finally:
        manager.stop()
