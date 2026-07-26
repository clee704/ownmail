"""Pytest fixtures for ownmail tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def mock_archive_db(**overrides):
    """A stand-in ArchiveDatabase for tests that only exercise the web layer.

    web.py's context processor asks for the stats and the label sidebar on every
    template render, and those need real ints and dicts — a bare MagicMock
    returns mocks that blow up on comparison and iteration. Pass keyword
    overrides for whatever a given test actually cares about:

        db = mock_archive_db(get_email_count=100)
    """
    db = MagicMock()
    db.get_email_count.return_value = 0
    db.get_trash_count.return_value = 0
    db.get_label_counts.return_value = {}
    db.get_role_counts.return_value = {}
    for name, value in overrides.items():
        getattr(db, name).return_value = value
    return db


@pytest.fixture
def sample_eml_simple():
    """A simple plain text email."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 1 Jan 2024 10:00:00 +0000
Message-ID: <test123@example.com>

This is a test email body.
"""


@pytest.fixture
def sample_eml_html():
    """An HTML email."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: HTML Test
Date: Tue, 2 Jan 2024 12:00:00 +0000
Message-ID: <html456@example.com>
Content-Type: text/html; charset="utf-8"

<html>
<body>
<h1>Hello World</h1>
<p>This is an HTML email.</p>
</body>
</html>
"""


@pytest.fixture
def sample_eml_multipart():
    """A multipart email with attachment."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Email with Attachment
Date: Wed, 3 Jan 2024 14:00:00 +0000
Message-ID: <multi789@example.com>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="boundary123"

--boundary123
Content-Type: text/plain; charset="utf-8"

This email has an attachment.

--boundary123
Content-Type: application/pdf; name="document.pdf"
Content-Disposition: attachment; filename="document.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRv
Ymo=

--boundary123--
"""


@pytest.fixture
def sample_eml_korean():
    """An email with Korean characters (common encoding issues)."""
    return """From: =?UTF-8?B?7ZWc6rWt7Ja0?= <korean@example.com>
To: recipient@example.com
Subject: =?UTF-8?B?7ZWc6riAIO2FjOyKpO2KuA==?=
Date: Thu, 4 Jan 2024 16:00:00 +0900
Message-ID: <korean@example.com>
Content-Type: text/plain; charset="utf-8"

안녕하세요, 테스트 이메일입니다.
""".encode()


@pytest.fixture
def sample_eml_malformed():
    """A malformed email with embedded CR/LF in headers."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Test with
 continuation line
Date: Fri, 5 Jan 2024 18:00:00 +0000
Message-ID: <malformed@example.com>

Body text.
"""


@pytest.fixture
def sample_eml_with_labels():
    """An email with labels (stored in DB, not in .eml headers)."""
    return b"""From: sender@example.com
To: recipient@example.com
Subject: Labeled Email
Date: Sat, 6 Jan 2024 20:00:00 +0000
Message-ID: <labeled@example.com>

This email has labels.
"""
