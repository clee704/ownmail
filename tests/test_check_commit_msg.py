"""Tests for the Conventional Commit header check."""

import subprocess

import pytest

from scripts import check_commit_msg


@pytest.mark.parametrize(
    "header",
    ["feat: add import command (TASK-7)", "release: 0.4.0", "chore: " + "x" * 64],
)
def test_accepts_documented_headers(header):
    assert check_commit_msg.header_error(header) is None


@pytest.mark.parametrize(
    ("header", "reason"),
    [
        ("Add import command", "expected"),
        ("style: drop emoji", "expected"),
        ("feat(web): add scope", "expected"),
        ("feat:missing space", "expected"),
        ("feat: ", "expected"),
        ("chore: " + "x" * 66, "73 characters"),
    ],
)
def test_rejects_undocumented_headers(header, reason):
    assert reason in check_commit_msg.header_error(header)


def test_message_file_checks_only_the_first_line(tmp_path, capsys):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("docs: explain review\n\nBody lines are free-form.\n")
    assert check_commit_msg.main([str(message)]) == 0

    message.write_text("Explain review\n")
    assert check_commit_msg.main([str(message)]) == 1
    assert "commit message: 'Explain review'" in capsys.readouterr().err


def test_header_option_checks_pull_request_titles():
    assert check_commit_msg.main(["--header", "fix: keep refreshes current"]) == 0
    assert check_commit_msg.main(["--header", "Keep refreshes current"]) == 1


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    monkeypatch.chdir(tmp_path)
    return git


def test_range_reports_each_invalid_commit(repo, capsys):
    repo("commit", "-q", "--allow-empty", "-m", "Initial commit")
    base = repo("rev-parse", "HEAD")
    repo("commit", "-q", "--allow-empty", "-m", "feat: add a thing")
    assert check_commit_msg.main(["--range", f"{base}..HEAD"]) == 0

    repo("commit", "-q", "--allow-empty", "-m", "fix things")
    assert check_commit_msg.main(["--range", f"{base}..HEAD"]) == 1
    err = capsys.readouterr().err
    assert "'fix things'" in err
    assert "Initial commit" not in err


def test_range_from_new_branch_checks_only_the_pushed_head(repo):
    repo("commit", "-q", "--allow-empty", "-m", "Initial commit")
    repo("commit", "-q", "--allow-empty", "-m", "feat: add a thing")
    assert check_commit_msg.main(["--range", "0" * 40 + "..HEAD"]) == 0
