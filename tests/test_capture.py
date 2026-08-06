"""Tests for the capture state envelope."""

import json

from ownmail import capture


class TestLegacyState:
    """Two formats predate the envelope, and neither may force a resync."""

    def test_gmail_bare_history_id(self):
        state = capture.load("987654321")
        assert state.cursor == "987654321"
        assert state.excluded == frozenset()
        assert state.fingerprint is None

    def test_imap_watermark_map_is_handed_back_verbatim(self):
        """The provider parses this itself, so it must survive unmodified."""
        raw = json.dumps({"INBOX": {"max_uid": 42, "uidvalidity": "7"}})
        assert capture.load(raw).cursor == raw

    def test_empty_state(self):
        assert capture.load(None) == capture.CaptureState()
        assert capture.load("") == capture.CaptureState()

    def test_legacy_state_is_never_stale(self):
        """No recorded fingerprint means unknown, not changed."""
        assert not capture.load("987654321").stale("anything")


class TestRoundTrip:
    def test_envelope_survives_dump_and_load(self):
        state = capture.CaptureState(cursor="123", excluded=frozenset({"a", "b"}), fingerprint="deadbeef")
        assert capture.load(capture.dump(state)) == state

    def test_dump_is_stable_across_set_ordering(self):
        """An unchanged run must produce an unchanged stored string."""
        one = capture.CaptureState(excluded=frozenset({"c", "a", "b"}))
        two = capture.CaptureState(excluded=frozenset({"b", "c", "a"}))
        assert capture.dump(one) == capture.dump(two)

    def test_future_version_is_treated_as_legacy(self):
        """An envelope we don't understand degrades to a cursor, not a crash."""
        raw = json.dumps({"v": capture.VERSION + 1, "cursor": "x"})
        assert capture.load(raw).cursor == raw


class TestDeparted:
    def test_ids_that_left_the_excluded_set(self):
        state = capture.CaptureState(excluded=frozenset({"a", "b", "c"}))
        assert state.departed(frozenset({"b"})) == frozenset({"a", "c"})

    def test_nothing_departed_when_membership_is_unchanged(self):
        state = capture.CaptureState(excluded=frozenset({"a", "b"}))
        assert state.departed(frozenset({"a", "b"})) == frozenset()

    def test_arrivals_into_the_excluded_set_are_not_departures(self):
        state = capture.CaptureState(excluded=frozenset({"a"}))
        assert state.departed(frozenset({"a", "new"})) == frozenset()


class TestStale:
    def test_changed_filter_is_stale(self):
        assert capture.CaptureState(fingerprint="one").stale("two")

    def test_unchanged_filter_is_not(self):
        assert not capture.CaptureState(fingerprint="one").stale("one")


class TestFingerprint:
    def test_order_does_not_matter(self):
        """Reordering exclude_folders in config is not a filter change."""
        assert capture.fingerprint("trash", "spam") == capture.fingerprint("spam", "trash")

    def test_different_filters_differ(self):
        assert capture.fingerprint("trash", "spam") != capture.fingerprint("trash", "spam", "inbox")

    def test_accepts_non_strings(self):
        assert capture.fingerprint(frozenset({"a"}), ["b"], None)
