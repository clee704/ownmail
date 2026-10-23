"""Owned SQLite handles close independently of garbage collection."""

import sqlite3
import subprocess
import sys
import textwrap
from contextlib import closing, nullcontext

import pytest

from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase
from tests.conftest import create_test_app


@pytest.mark.parametrize("fail", [False, True])
def test_query_connection_closes_after_commit_or_rollback(tmp_path, fail):
    db = ArchiveDatabase(tmp_path)
    outcome = pytest.raises(RuntimeError, match="synthetic failure") if fail else nullcontext()
    with outcome, db._connect() as conn:
        conn.execute("INSERT INTO sync_state VALUES ('transaction', 'saved')")
        if fail:
            raise RuntimeError("synthetic failure")

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")
    with closing(sqlite3.connect(db.db_path)) as reader:
        assert reader.execute("SELECT value FROM sync_state WHERE key='transaction'").fetchone() == (
            None if fail else ("saved",)
        )


@pytest.mark.parametrize("fail", [False, True])
def test_consolidated_count_closes_on_success_and_query_error(tmp_path, monkeypatch, fail):
    archive = EmailArchive(tmp_path / "archive")
    connections = []
    connect = sqlite3.connect

    class CountConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if fail and sql.startswith("SELECT COUNT(*)"):
                raise sqlite3.OperationalError("synthetic query failure")
            return super().execute(sql, *args, **kwargs)

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs, factory=CountConnection)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    if fail:
        with pytest.raises(sqlite3.OperationalError, match="synthetic query failure"):
            archive.consolidated_count()
    else:
        assert archive.consolidated_count() == 0
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_search_request_closes_every_owned_connection(tmp_path, monkeypatch):
    archive = EmailArchive(tmp_path / "archive")
    app = create_test_app(archive)
    connections = []
    connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    response = app.test_client().get("/search")
    assert response.status_code == 200
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_repeated_search_requests_under_low_descriptor_limit(tmp_path):
    pytest.importorskip("resource")
    script = textwrap.dedent("""
        import gc
        import resource
        import sys
        from pathlib import Path

        from ownmail.archive import EmailArchive
        from tests.conftest import create_test_app

        archive = EmailArchive(Path(sys.argv[1]) / "archive")
        (archive.archive_dir / "synthetic.eml").write_text("Subject: Synthetic result\\n\\nSearch body\\n")
        archive.db.mark_downloaded(
            "synthetic", "synthetic", "synthetic.eml", email_date="2024-01-01T00:00:00"
        )
        archive.db.index_email(
            "synthetic", "Synthetic result", "sender@example.test", "reader@example.test",
            "2024-01-01", "Search body", ""
        )
        app = create_test_app(archive)
        app.testing = True
        client = app.test_client()
        gc.collect()
        gc.disable()
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        limit = 128 if hard == resource.RLIM_INFINITY else min(128, hard)
        resource.setrlimit(resource.RLIMIT_NOFILE, (limit, hard))
        for index in range(100):
            response = client.get("/search?q=Search")
            assert response.status_code == 200, (index, response.status_code)
            assert b"Synthetic result" in response.data, index
            response.close()
        assert not gc.isenabled()
    """)
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
