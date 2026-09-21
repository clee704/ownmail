"""Fresh Gmail scans use bounded HTTP batches without trusting partial results."""

import json
from collections import Counter
from email.parser import Parser
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from ownmail.providers.gmail import GmailProvider


class GmailTransport:
    """Serve synthetic mail through the real Google client's HTTP boundary."""

    def __init__(self, count):
        self.messages = {
            f"m{index}": {"id": f"m{index}", "threadId": f"t{index}", "labelIds": ["Label_1"]} for index in range(count)
        }
        self.requests = Counter()
        self.batch_sizes = []
        self.errors = {}
        self.omitted = set()
        self.fail_batch = None
        self.failure = RuntimeError("private transport details")

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        url = urlsplit(uri)
        query = parse_qs(url.query)
        self.requests[method, url.path] += 1
        response_headers = {"status": "200", "content-type": "application/json"}
        if method == "GET" and url.path == "/gmail/v1/users/me/labels":
            content = json.dumps(
                {
                    "labels": [
                        {"id": label, "name": label, "type": "system"}
                        for label in ["INBOX", "DRAFT", "SENT", "TRASH", "SPAM", "SCHEDULED"]
                    ]
                    + [{"id": "Label_1", "name": "Projects", "type": "user"}]
                }
            )
        elif method == "GET" and url.path == "/gmail/v1/users/me/messages":
            assert query["includeSpamTrash"] == ["true"]
            assert query["maxResults"] == ["500"]
            assert "q" not in query and "labelIds" not in query
            offset = int(query.get("pageToken", ["0"])[0])
            ids = list(self.messages)[offset : offset + 500]
            page = {"messages": [{"id": message_id} for message_id in ids]}
            if offset + 500 < len(self.messages):
                page["nextPageToken"] = str(offset + 500)
            content = json.dumps(page)
        elif method == "POST" and url.path == "/batch":
            request = Parser().parsestr(f"Content-Type: {headers['content-type']}\r\n\r\n{body}")
            parts = request.get_payload()
            self.batch_sizes.append(len(parts))
            if len(self.batch_sizes) == self.fail_batch:
                raise self.failure
            responses = []
            for part in reversed(parts):
                verb, path, version = part.get_payload().splitlines()[0].split()
                path = urlsplit(path)
                message_id = path.path.rsplit("/", 1)[-1]
                assert verb == "GET" and path.path.startswith("/gmail/v1/users/me/messages/")
                assert parse_qs(path.query) == {
                    "format": ["minimal"],
                    "fields": ["id,threadId,labelIds"],
                    "alt": ["json"],
                }
                if message_id in self.omitted:
                    continue
                status = self.errors.get(message_id, 200)
                payload = self.messages[message_id] if status == 200 else {"error": "private remote details"}
                responses.append(
                    "--response\r\nContent-Type: application/http\r\n"
                    f"Content-ID: {part['Content-ID']}\r\n\r\n"
                    f"HTTP/1.1 {status} result\r\nContent-Type: application/json\r\n\r\n"
                    f"{json.dumps(payload)}\r\n"
                )
            content = "".join(responses) + "--response--\r\n"
            response_headers["content-type"] = 'multipart/mixed; boundary="response"'
        else:
            raise AssertionError(f"Unexpected separate HTTP request: {method} {url.path}")
        return HttpMockSequence([(response_headers, content)]).request(uri)


def provider_for(transport, *, include_labels=True):
    provider = GmailProvider("person@example.test", MagicMock(), source_name="source", include_labels=include_labels)
    provider._service = build("gmail", "v1", http=transport, static_discovery=True)
    return provider


@pytest.mark.parametrize("include_labels", [True, False])
def test_initial_and_unchanged_scans_batch_one_thousand_fresh_observations(include_labels):
    transport = GmailTransport(1000)
    provider = provider_for(transport, include_labels=include_labels)
    previous = None
    for _ in range(2):
        progress = []
        result = provider.list_live_messages(on_progress=progress.append)
        assert result.complete
        assert (result.source_name, result.account) == ("source", "person@example.test")
        assert [message.message_id for message in result.messages] == list(transport.messages)
        assert all(message.state == "eligible" for message in result.messages)
        assert all(message.labels == (("Projects",) if include_labels else ()) for message in result.messages)
        assert transport.requests == {
            ("GET", "/gmail/v1/users/me/labels"): 1,
            ("GET", "/gmail/v1/users/me/messages"): 2,
            ("POST", "/batch"): 20,
        }
        assert transport.batch_sizes == [50] * 20
        assert progress == list(range(50, 1001, 50))
        if previous is not None:
            assert result == previous
        previous = result
        transport.requests.clear()
        transport.batch_sizes.clear()


def test_batches_observe_current_lifecycle_states_on_every_run():
    transport = GmailTransport(7)
    provider = provider_for(transport)
    labels = [["INBOX"], ["DRAFT"], ["TRASH", "INBOX"], ["SPAM"], ["SCHEDULED"], ["SENT"], ["Label_1"]]
    for message, current_labels in zip(transport.messages.values(), labels):
        message["labelIds"] = current_labels
    first = provider.list_live_messages()
    assert first.complete
    assert [message.state for message in first.messages] == [
        "active",
        "active",
        "discarded",
        "discarded",
        "unknown",
        "eligible",
        "eligible",
    ]
    for message in transport.messages.values():
        message["labelIds"] = ["TRASH"]
    second = provider.list_live_messages()
    assert second.complete
    assert [message.state for message in second.messages] == ["discarded"] * 7


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_failed_batch_member_preserves_other_observations_without_confirming_absence(status):
    transport = GmailTransport(3)
    transport.errors["m1"] = status
    progress = []
    result = provider_for(transport).list_live_messages(on_progress=progress.append)
    assert not result.complete
    assert [message.message_id for message in result.messages] == ["m0", "m2"]
    assert result.reason == "Some Gmail messages could not be checked"
    assert progress == [3]


@pytest.mark.parametrize("change", [{"id": "other"}, {"threadId": None}, {"labelIds": "INBOX"}])
def test_invalid_batch_metadata_cannot_authorize_capture(change):
    transport = GmailTransport(3)
    transport.messages["m1"].update(change)
    result = provider_for(transport).list_live_messages()
    assert not result.complete
    assert [message.message_id for message in result.messages] == ["m0", "m2"]


@pytest.mark.parametrize("failure", ["transport", "missing"])
def test_broken_batch_retains_previous_batches_and_continues_conservatively(failure):
    transport = GmailTransport(101)
    if failure == "transport":
        transport.fail_batch = 2
    else:
        transport.omitted.add("m75")
    progress = []
    result = provider_for(transport).list_live_messages(on_progress=progress.append)
    assert not result.complete
    assert [message.message_id for message in result.messages] == [f"m{index}" for index in range(50)] + ["m100"]
    assert progress == [50, 100, 101]


def test_batch_interrupt_propagates_without_reporting_unchecked_messages():
    transport = GmailTransport(101)
    transport.fail_batch = 2
    transport.failure = KeyboardInterrupt()
    progress = []
    with pytest.raises(KeyboardInterrupt):
        provider_for(transport).list_live_messages(on_progress=progress.append)
    assert progress == [50]
    assert transport.batch_sizes == [50, 50]


@pytest.mark.parametrize("failure", ["missing", "duplicate", "unexpected", "exception"])
def test_missing_or_ambiguous_callbacks_leave_snapshot_incomplete(failure):
    provider = provider_for(GmailTransport(3))

    def new_batch(*, callback):
        def execute():
            for message_id in ["m2", "m0", "m1"]:
                if failure == "missing" and message_id == "m1":
                    continue
                callback(message_id, {"id": message_id, "threadId": "thread", "labelIds": ["SENT"]}, None)
            if failure == "exception":
                raise RuntimeError("private batch details")
            if failure == "duplicate":
                callback("m1", {"id": "m1", "threadId": "thread"}, None)
            if failure == "unexpected":
                callback("other", {"id": "other", "threadId": "thread"}, None)

        batch = MagicMock()
        batch.execute.side_effect = execute
        return batch

    provider._service.new_batch_http_request = new_batch
    result = provider.list_live_messages()
    assert not result.complete
    expected = ["m0", "m2"] if failure in {"missing", "duplicate"} else ["m0", "m1", "m2"]
    assert [message.message_id for message in result.messages] == expected


def test_catalog_failure_is_incomplete_even_without_emitted_labels():
    provider = provider_for(GmailTransport(1), include_labels=False)
    provider._service.users = MagicMock(side_effect=RuntimeError("private catalog details"))
    result = provider.list_live_messages()
    assert not result.complete
    assert not result.messages
    assert result.reason == "Gmail live enumeration failed"
