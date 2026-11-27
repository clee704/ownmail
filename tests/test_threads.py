"""Thread grouping inputs and components (doc-11)."""

import email
import itertools
import json
import sqlite3
from contextlib import closing
from email.policy import default as email_policy

import pytest

from ownmail import GmailArchive, commands
from ownmail.active_cache import ActiveCache
from ownmail.archive import EmailArchive
from ownmail.database import ArchiveDatabase
from ownmail.parser import EmailParser
from ownmail.threads import derive_thread_inputs, group_threads

ACCOUNT = "reader@example.test"
RAW = (
    b"From: sender@example.test\r\n"
    b"To: reader@example.test\r\n"
    b"Subject: Re: RE:fwd:  Quarterly   Plan\r\n"
    b"Date: Mon, 15 Jan 2024 10:00:00 +0000\r\n"
    b"Message-ID: <Child@Example.test>\r\n"
    b"References: <root@example.test> <bad token@x> junk\r\n"
    b" <Parent@Example.test>\r\n"
    b"In-Reply-To: <Parent@Example.test>\r\n"
    b"\r\n"
    b"Body\r\n"
)
EXPECTED = {
    "message_id": "<Child@Example.test>",
    "references": ["<root@example.test>", "<Parent@Example.test>"],
    "in_reply_to": ["<Parent@Example.test>"],
    "subject_key": "quarterly plan",
    "is_reply": True,
}


def rec(email_id, message_id=None, references=(), in_reply_to=(), subject="", account=ACCOUNT):
    """Build a grouping record from a raw subject, as the parser would."""
    msg = email.message_from_bytes(b"\r\n", policy=email_policy)
    inputs = derive_thread_inputs(msg, subject)
    return (
        email_id,
        account,
        message_id,
        list(references),
        list(in_reply_to),
        inputs["subject_key"],
        inputs["is_reply"],
    )


# -- Input extraction ---------------------------------------------------------


def test_parse_file_derives_inputs_from_headers():
    assert EmailParser.parse_file(content=RAW)["thread_inputs"] == EXPECTED


def test_subject_key_uses_the_parsers_decoded_subject():
    raw = b"Subject: =?UTF-8?B?UmU6IOqzhO2ajQ==?=\r\nMessage-ID: <a b>\r\n\r\nx"
    inputs = EmailParser.parse_file(content=raw)["thread_inputs"]
    assert inputs == {
        "message_id": None,
        "references": [],
        "in_reply_to": [],
        "subject_key": "계획",
        "is_reply": True,
    }


@pytest.mark.parametrize(
    ("subject", "key", "is_reply"),
    [
        ("Plan", "plan", False),
        ("Fw: Plan", "plan", True),
        ("Re: Re: Fwd: Plan", "plan", True),
        ("Plan Re: later", "plan re: later", False),
        ("Reply: Plan", "reply: plan", False),
        ("Re:", "", True),
        ("", "", False),
    ],
)
def test_subject_key_strips_leading_reply_and_forward_prefixes(subject, key, is_reply):
    assert rec("e", subject=subject)[5:] == (key, is_reply)


def test_unparseable_message_still_yields_empty_inputs(monkeypatch):
    monkeypatch.setattr(email, "message_from_bytes", lambda *a, **k: 1 / 0)
    inputs = EmailParser.parse_file(content=b"x")["thread_inputs"]
    assert inputs == {"message_id": None, "references": [], "in_reply_to": [], "subject_key": "", "is_reply": False}


# -- Grouping -----------------------------------------------------------------


def test_reference_chain_groups_under_smallest_email_id():
    records = [
        rec("c", "<c@x>", ["<a@x>", "<b@x>"], ["<b@x>"]),
        rec("b", "<b@x>", ["<a@x>"], ["<a@x>"]),
        rec("a", "<a@x>"),
        rec("z", "<z@x>"),
    ]
    assert group_threads(records) == {"a": "a", "b": "a", "c": "a"}


def test_siblings_group_through_a_missing_ancestor():
    records = [rec("2", "<s2@x>", in_reply_to=["<gone@x>"]), rec("1", "<s1@x>", ["<gone@x>"])]
    assert group_threads(records) == {"1": "1", "2": "1"}


def test_message_without_message_id_links_through_its_references():
    assert group_threads([rec("b", None, ["<a@x>"]), rec("a", "<a@x>")]) == {"a": "a", "b": "a"}


def test_identifiers_compare_case_sensitively():
    assert group_threads([rec("a", "<A@x>"), rec("b", None, ["<a@x>"])]) == {}


def test_duplicate_and_cyclic_references_terminate():
    records = [
        rec("a", "<a@x>", ["<b@x>", "<b@x>", "<a@x>"], ["<b@x>"]),
        rec("b", "<b@x>", ["<a@x>"], ["<a@x>"]),
    ]
    assert group_threads(records) == {"a": "a", "b": "a"}


def test_links_span_accounts_and_stores():
    records = [rec("owned", "<m@x>", account="a@x"), rec("active", "<m@x>", account="b@x")]
    assert group_threads(records) == {"active": "active", "owned": "active"}


def test_fallback_joins_the_single_candidate():
    records = [rec("o", "<o@x>", subject="Plan"), rec("r", "<r@x>", subject="Re: plan")]
    assert group_threads(records) == {"o": "o", "r": "o"}


def test_fallback_without_candidates_leaves_singletons():
    records = [
        rec("r1", subject="Re: Plan"),
        rec("r2", subject="Re: Plan"),
        rec("other", subject="Other"),
        rec("x", subject="Plan", account="other@x"),
    ]
    assert group_threads(records) == {}


def test_fallback_with_several_candidates_stays_put():
    records = [rec("o1", "<o1@x>", subject="Plan"), rec("o2", "<o2@x>", subject="Plan"), rec("r", subject="Re: Plan")]
    assert group_threads(records) == {}


def test_reply_only_component_of_two_is_a_candidate():
    records = [
        rec("r1", "<r1@x>", ["<gone@x>"], subject="Re: Plan"),
        rec("r2", "<r2@x>", ["<gone@x>"], subject="Re: Plan"),
        rec("r3", subject="Re: Plan"),
    ]
    assert group_threads(records) == {"r1": "r1", "r2": "r1", "r3": "r1"}


def test_reply_with_references_never_falls_back():
    records = [rec("o", "<o@x>", subject="Plan"), rec("r", in_reply_to=["<elsewhere@x>"], subject="Re: Plan")]
    assert group_threads(records) == {}


def test_originals_sharing_a_subject_stay_apart():
    assert group_threads([rec("a", subject="Plan"), rec("b", subject="Plan")]) == {}


def test_result_does_not_depend_on_input_order():
    """Fallback is decided against reference components, never against earlier joins.

    f's own component {f, g} also matches, so only o is another candidate; h sees
    both components and stays a singleton even after f merges them.
    """
    records = [
        rec("o", "<o@x>", subject="Plan"),
        rec("f", "<f@x>", subject="Re: Plan"),
        rec("g", "<g@x>", ["<f@x>"], subject="Re: Other"),
        rec("h", subject="Re: Plan"),
        rec("s1", "<s1@x>", ["<gone@x>"]),
        rec("s2", "<s2@x>", ["<gone@x>"]),
        rec("q", subject="Re: Lone"),
    ]
    expected = {"f": "f", "g": "f", "o": "f", "s1": "s1", "s2": "s1"}
    for order in itertools.permutations(records):
        assert group_threads(order) == expected


# -- Storage ------------------------------------------------------------------


def stored(db_path, email_id):
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(
            "SELECT account, message_id, references_json, in_reply_to_json, subject_key, is_reply "
            "FROM thread_inputs WHERE email_id = ?",
            (email_id,),
        ).fetchone()


STORED = (
    ACCOUNT,
    EXPECTED["message_id"],
    json.dumps(EXPECTED["references"]),
    json.dumps(EXPECTED["in_reply_to"]),
    EXPECTED["subject_key"],
    1,
)


def _rebuild(archive, eid, path):
    with closing(sqlite3.connect(archive.db.db_path)) as conn:
        assert commands._index_email_for_rebuild(archive, eid, path, conn)
        conn.commit()


@pytest.mark.parametrize(
    "index",
    [
        lambda archive, eid, path: commands._index_single_email(archive, eid, path),
        _rebuild,
        lambda archive, eid, path: archive._index_email(eid, path),
        lambda archive, eid, path: GmailArchive(archive.archive_dir).index_email(eid, path),
    ],
    ids=["single", "rebuild", "archive", "compat"],
)
def test_index_paths_write_inputs(temp_dir, index):
    archive = EmailArchive(temp_dir, {})
    path = temp_dir / "m.eml"
    path.write_bytes(RAW)
    eid = ArchiveDatabase.make_email_id(ACCOUNT, "p1")
    archive.db.mark_downloaded(eid, "p1", "m.eml", account=ACCOUNT)
    index(archive, eid, path)
    assert stored(archive.db.db_path, eid) == STORED


def test_import_registration_writes_inputs(temp_dir):
    archive = EmailArchive(temp_dir, {})
    path = temp_dir / "m.eml"
    path.write_bytes(RAW)
    with closing(sqlite3.connect(archive.db.db_path)) as conn:
        assert archive._register_and_index(path, RAW, "p1", ACCOUNT, conn) == "imported"
        conn.commit()
    assert stored(archive.db.db_path, ArchiveDatabase.make_email_id(ACCOUNT, "p1")) == STORED


def test_active_cache_indexing_and_rebuild_write_inputs(tmp_path):
    cache = ActiveCache(tmp_path / "archive")
    entry = cache.put(
        source_name="mail",
        account=ACCOUNT,
        provider_id="42",
        identity="epoch:42",
        roles=["inbox"],
        labels=["INBOX"],
        raw=RAW,
        checked_at="2024-01-01T12:00:00+00:00",
    )
    assert stored(cache.db.db_path, entry["id"]) == STORED
    with closing(sqlite3.connect(cache.db.db_path)) as conn, conn:
        conn.execute("DELETE FROM thread_inputs")
    cache.rebuild_index()
    assert stored(cache.db.db_path, entry["id"]) == STORED


def test_reindex_without_inputs_drops_stale_row(temp_dir):
    db = ArchiveDatabase(temp_dir)
    db.mark_downloaded("e1", "p1", "m.eml", account=ACCOUNT)
    db.index_email("e1", "s", "f", "t", "d", "b", "", thread_inputs=EXPECTED)
    db.index_email("e1", "s", "f", "t", "d", "b", "")
    assert stored(db.db_path, "e1") is None


def test_deleting_an_emails_row_removes_its_thread_rows(temp_dir):
    db = ArchiveDatabase(temp_dir)
    for eid in ("e1", "e2"):
        db.mark_downloaded(eid, eid, f"{eid}.eml", account=ACCOUNT)
        db.index_email(eid, "s", "f", "t", "d", "b", "", thread_inputs=EXPECTED)
    with closing(sqlite3.connect(db.db_path)) as conn, conn:
        conn.executemany("INSERT INTO thread_members VALUES (?, 'e1')", [("e1",), ("e2",)])
        conn.execute("DELETE FROM emails WHERE email_id = 'e1'")
        assert conn.execute("SELECT email_id FROM thread_inputs").fetchall() == [("e2",)]
        assert conn.execute("SELECT email_id FROM thread_members").fetchall() == [("e2",)]
