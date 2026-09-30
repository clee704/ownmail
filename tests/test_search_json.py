"""Pure JSON search contract, independent of the pending acquisition policy."""

import copy
import json
from unittest.mock import patch

import pytest

from ownmail.search_json import search_error_json, search_results_json, validate_search_pagination


def row(identifier="owned", *, snippet="Body", attachments=0):
    return (
        identifier,
        "/synthetic/private/message.eml",
        "Subject",
        "sender@example.test",
        "2026-09-30",
        snippet,
        attachments,
    )


def test_owned_result_contract_omits_internal_path_and_preserves_null_headers(capsys):
    rows = [("stable-id", "/synthetic/private/message.eml", None, None, None, None, None)]
    assert json.loads(search_results_json(rows, {})) == {
        "results": [
            {
                "id": "stable-id",
                "sender": None,
                "subject": None,
                "date": None,
                "snippet": "",
                "has_attachments": False,
                "archived": True,
                "active": None,
            }
        ],
        "pagination": {"limit": 50, "offset": 0, "has_more": False, "next_offset": None},
    }
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("archived,complete", [(False, True), (True, False)])
def test_active_and_matched_results_keep_existing_ownership_and_freshness(archived, complete):
    identifier = "owned" if archived else "active-synthetic"
    info = {
        "active": True,
        "archived": archived,
        "complete": complete,
        "checked_at": "2026-09-29T11:00:00+00:00",
        "content_at": "2026-09-28T12:00:00+00:00",
        "reason": None if complete else "Active mail has not been refreshed for the current scope",
        "refresh_error": None if complete else "Synthetic refresh failed",
        "cache_id": "active-synthetic",
        "archive_id": "owned" if archived else None,
        "source_name": "internal-source",
        "future_internal_field": "omit",
    }
    original = copy.deepcopy(info)
    result = json.loads(search_results_json([row(identifier, attachments=1)], {identifier: info}))["results"][0]
    assert result == {
        "id": identifier,
        "sender": "sender@example.test",
        "subject": "Subject",
        "date": "2026-09-30",
        "snippet": "Body",
        "has_attachments": True,
        "archived": archived,
        "active": {key: info[key] for key in ("complete", "checked_at", "content_at", "reason", "refresh_error")},
    }
    assert info == original


def test_missing_active_metadata_is_an_error_not_an_archived_result():
    with pytest.raises(ValueError, match="Active status is unavailable"):
        search_results_json([row("active-synthetic")], {})


@pytest.mark.parametrize(
    "count,has_more,next_offset", [(0, False, None), (1, False, None), (2, False, None), (3, True, 9)]
)
def test_page_uses_one_lookahead_without_reslicing_the_offset(count, has_more, next_offset):
    rows = [row(f"id-{i}") for i in range(count)]
    original = list(rows)
    result = json.loads(search_results_json(rows, {}, limit=2, offset=7))
    assert [item["id"] for item in result["results"]] == [f"id-{i}" for i in range(min(count, 2))]
    assert result["pagination"] == {"limit": 2, "offset": 7, "has_more": has_more, "next_offset": next_offset}
    assert rows == original


def test_page_cap_and_order_remain_bounded_with_excess_input():
    rows = [row(str(i)) for i in range(650, -1, -1)]
    result = json.loads(search_results_json(rows, {}, limit=500, offset=1000))
    assert len(result["results"]) == 500
    assert result["results"][0]["id"] == "650"
    assert result["results"][-1]["id"] == "151"
    assert result["pagination"] == {"limit": 500, "offset": 1000, "has_more": True, "next_offset": 1500}


@pytest.mark.parametrize("limit,offset", [(1, 0), (500, 123)])
def test_valid_pagination_boundaries(limit, offset):
    assert validate_search_pagination(limit, offset) is None


@pytest.mark.parametrize("limit", [0, -1, 501, True, False, 1.5, "50", None])
def test_invalid_limit_is_rejected_before_formatting(limit):
    with pytest.raises(ValueError, match="limit must be an integer from 1 to 500"):
        validate_search_pagination(limit, 0)
    with pytest.raises(ValueError, match="limit must be an integer from 1 to 500"):
        search_results_json([], {}, limit=limit)


@pytest.mark.parametrize("offset", [-1, True, False, 1.5, "0", None])
def test_invalid_offset_is_rejected_before_formatting(offset):
    with pytest.raises(ValueError, match="offset must be a nonnegative integer"):
        validate_search_pagination(50, offset)
    with pytest.raises(ValueError, match="offset must be a nonnegative integer"):
        search_results_json([], {}, offset=offset)


@pytest.mark.parametrize("snippet,expected", [("", ""), ("界" * 200, "界" * 200), ("界" * 201, "界" * 199 + "…")])
def test_snippet_cap_counts_unicode_characters_including_ellipsis(snippet, expected):
    result = json.loads(search_results_json([row(snippet=snippet)], {}))["results"][0]
    assert result["snippet"] == expected
    assert len(result["snippet"]) <= 200


def test_json_quotes_controls_and_unicode_round_trip_as_data():
    text = '"quoted"\\slash\n\x00한글 <script>data</script>'
    result = search_results_json([("id", "/omit", text, text, text, text, 0)], {})
    assert "\n" not in result and "\x00" not in result
    assert "한글" in result
    parsed = json.loads(result)["results"][0]
    assert all(parsed[key] == text for key in ("subject", "sender", "date", "snippet"))


@pytest.mark.parametrize(
    "code,message",
    [
        ("invalid_query", 'Unclosed quote: "'),
        ("invalid_pagination", "limit must be an integer from 1 to 500"),
        ("unavailable", "A required local search index is unavailable"),
        ("search_failed", "Synthetic error\nwith control \x00 and 한글"),
    ],
)
def test_error_is_a_single_json_envelope_without_printing(code, message, capsys):
    result = search_error_json(code, message)
    assert json.loads(result) == {"error": {"code": code, "message": message}}
    assert "\n" not in result and "\x00" not in result
    assert capsys.readouterr() == ("", "")


def test_formatting_never_acquires_files_database_or_network():
    def unexpected_io(*args, **kwargs):
        raise AssertionError("A pure formatter must not acquire source data")

    with (
        patch("builtins.open", side_effect=unexpected_io),
        patch("io.open", side_effect=unexpected_io),
        patch("sqlite3.connect", side_effect=unexpected_io),
        patch("socket.create_connection", side_effect=unexpected_io),
    ):
        assert json.loads(search_results_json([row()], {}))["results"][0]["id"] == "owned"
        assert json.loads(search_error_json("unavailable", "Synthetic"))["error"]["code"] == "unavailable"
