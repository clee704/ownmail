"""Cached mail stays readable when current configuration no longer refreshes it."""

import pytest

from ownmail.archive import EmailArchive
from ownmail.config import active_entry_status, active_scope_signature
from ownmail.providers.live_imap import _message_id

CHECKED = "2026-01-01T12:00:00+00:00"
LATER = "2026-01-02T12:00:00+00:00"
RAW = b"From: sender@example.test\r\nSubject: cached mail\r\n\r\nPreserved body"


@pytest.fixture
def cached(tmp_path):
    source = {"name": "mail", "type": "gmail_api", "account": "reader@example.test", "active_downloads": True}
    archive = EmailArchive(tmp_path / "archive", {"sources": [source]})
    cache = archive.active_cache(create=True)
    entry = cache.put(
        source_name="mail",
        account=source["account"],
        provider_id="one",
        identity="gmail:one",
        labels=["Inbox"],
        roles=["inbox"],
        raw=RAW,
        checked_at=CHECKED,
    )
    cache.set_source_status(
        "mail",
        source["account"],
        complete=True,
        checked_at=CHECKED,
        active_scope_signature=active_scope_signature("gmail_api", []),
    )
    return archive, source, entry


@pytest.mark.parametrize(
    "change,reason",
    [
        ("disabled", "Active downloads are disabled for this source"),
        ("omitted", "Active downloads are disabled for this source"),
        ("removed", "This Active source is no longer configured"),
        ("account", "This Active source is no longer configured"),
    ],
)
def test_opt_out_marks_cached_mail_stale_without_hiding_or_mutating_it(cached, change, reason):
    archive, source, entry = cached
    assert archive.active_info(entry["id"])["complete"] is True
    cache = archive.active_cache()
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in cache.cache_dir.rglob("*") if path.is_file()
    }
    if change == "disabled":
        source["active_downloads"] = False
    elif change == "omitted":
        source.pop("active_downloads")
    elif change == "removed":
        archive.config["sources"] = []
    else:
        source["account"] = "other@example.test"

    info = archive.active_info(entry["id"])
    assert info["complete"] is False
    assert info["reason"] == reason
    assert archive.get_readable_email(entry["id"])
    assert cache.read(entry["id"]) == RAW
    assert [row[0] for row in archive.search("is:active")] == [entry["id"]]
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before} == before


def test_changed_scope_requires_a_matching_refresh_and_per_message_observation(cached):
    archive, source, entry = cached
    source["active_exclude_labels"] = ["Retained"]
    info = archive.active_info(entry["id"])
    assert info["complete"] is False
    assert info["reason"] == "Active mail has not been refreshed for the current scope"
    cache = archive.active_cache()
    cache.set_source_status(
        "mail",
        source["account"],
        complete=True,
        checked_at=LATER,
        active_scope_signature=active_scope_signature("gmail_api", ["Retained"]),
    )
    info = archive.active_info(entry["id"])
    assert info["complete"] is False
    assert info["reason"] == "This message was not checked in the latest Active refresh"
    cache.put(
        source_name="mail",
        account=source["account"],
        provider_id="one",
        identity="gmail:one",
        labels=entry["labels"],
        roles=entry["roles"],
        raw=RAW,
        checked_at=LATER,
    )
    assert archive.active_info(entry["id"])["complete"] is True


@pytest.mark.parametrize("persisted", [False, True])
def test_excluded_gmail_labels_use_private_scope_metadata_when_labels_are_disabled(cached, persisted):
    archive, source, entry = cached
    source["active_exclude_labels"] = ["Retained"]
    scope = {"active_scope": ["Retained"]} if persisted else {}
    entry = {**entry, "labels": [] if persisted else ["Retained"], **scope}
    assert active_entry_status(archive.config, entry) == "This message is excluded from Active downloads"
    source["active_exclude_labels"] = ["retained"]
    assert active_entry_status(archive.config, entry) is None


@pytest.mark.parametrize(
    "matched_by,persisted_scope",
    [("locator", None), ("locator", []), ("labels", None), ("labels", []), ("scope", ["Retained"])],
)
def test_imap_scope_checks_exact_folder_locator_and_all_observed_memberships(cached, matched_by, persisted_scope):
    archive, source, entry = cached
    source.update(type="imap", active_exclude_folders=["Retained"])
    entry = {
        **entry,
        "provider_id": _message_id("Retained" if matched_by == "locator" else "INBOX", "10", 1),
        "labels": ["Retained"] if matched_by == "labels" else [],
    }
    if persisted_scope is not None:
        entry["active_scope"] = persisted_scope
    assert active_entry_status(archive.config, entry) == "This message is excluded from Active downloads"


def test_imap_inbox_membership_remains_fresh_through_excluded_all_mail_locator(cached):
    archive, source, entry = cached
    source.update(type="imap", active_exclude_folders=["All Mail"])
    cache = archive.active_cache()
    entry = cache.put(
        source_name=entry["source_name"],
        account=entry["account"],
        provider_id=_message_id("All Mail", "10", 1),
        identity=entry["identity"],
        labels=["All Mail", "INBOX"],
        roles=["inbox"],
        raw=RAW,
        checked_at=LATER,
        active_scope=["INBOX"],
    )
    cache.set_source_status(
        "mail",
        source["account"],
        complete=True,
        checked_at=LATER,
        active_scope_signature=active_scope_signature("imap", ["All Mail"]),
    )
    info = archive.active_info(entry["id"])
    assert info["complete"] is True
    assert info["reason"] is None


@pytest.mark.parametrize("locator", ["bad", "imap:!", "imap:e30="])
@pytest.mark.parametrize("scope", [{}, {"active_scope": []}])
def test_unreadable_imap_locator_cannot_claim_to_be_in_scope(cached, locator, scope):
    archive, source, entry = cached
    source.update(type="imap", active_exclude_folders=["Retained"])
    assert (
        active_entry_status(archive.config, {**entry, "provider_id": locator, **scope})
        == "Active mail scope could not be verified"
    )


def test_invalid_scope_configuration_is_stale_without_provider_access(cached):
    archive, source, entry = cached
    source["active_exclude_labels"] = "Retained"
    info = archive.active_info(entry["id"])
    assert info["complete"] is False
    assert info["reason"] == "Active scope configuration is invalid"


@pytest.mark.parametrize("unknown", [False, True])
@pytest.mark.parametrize("source_complete", [False, True])
def test_current_message_state_is_independent_of_unrelated_refresh_errors(cached, unknown, source_complete):
    archive, source, entry = cached
    cache = archive.active_cache()
    cache.put(
        source_name="mail",
        account=source["account"],
        provider_id="one",
        identity="gmail:one",
        labels=entry["labels"],
        roles=entry["roles"],
        raw=RAW,
        checked_at=CHECKED,
        state="unknown" if unknown else "active",
    )
    error = None if source_complete else "Some messages could not be checked"
    cache.set_source_status(
        "mail",
        source["account"],
        complete=source_complete,
        checked_at=CHECKED,
        error=error,
        active_scope_signature=active_scope_signature("gmail_api", []),
    )
    info = archive.active_info(entry["id"])
    assert info["complete"] is (not unknown)
    assert info["reason"] == ("Message state is unrecognized" if unknown else None)
    assert info["refresh_error"] == error


def test_interrupted_refresh_retains_last_check_time_and_explains_staleness(cached):
    archive, source, entry = cached
    cache = archive.active_cache()
    cache.set_source_status(
        "mail",
        source["account"],
        complete=False,
        checked_at=LATER,
        error="Refresh interrupted; completed saves are retained",
        active_scope_signature=active_scope_signature("gmail_api", []),
    )
    info = archive.active_info(entry["id"])
    assert info["complete"] is False
    assert info["checked_at"] == CHECKED
    assert info["reason"] == "This message was not checked in the latest Active refresh"
    assert info["refresh_error"] == "Refresh interrupted; completed saves are retained"
