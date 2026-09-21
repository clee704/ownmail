"""Active scope names are exact, provider-specific configuration values."""

import pytest

from ownmail.config import active_scope_signature, validate_config


def config(kind, **settings):
    return {
        "sources": [
            {
                "name": "mail",
                "type": kind,
                "account": "reader@example.test",
                "host": "mail.example.test",
                "auth": {"secret_ref": "keychain:mail"},
                **settings,
            }
        ]
    }


@pytest.mark.parametrize("kind,key", [("imap", "active_exclude_folders"), ("gmail_api", "active_exclude_labels")])
@pytest.mark.parametrize("names", [[], ["Retained", "Retained/2020", "Exact Case", " spaced ", "保管"]])
def test_valid_scope_names_preserve_exact_values(kind, key, names):
    configured = config(kind, **{key: names})
    assert validate_config(configured) == []
    assert configured["sources"][0][key] == names


@pytest.mark.parametrize("kind,key", [("gmail_api", "active_exclude_folders"), ("imap", "active_exclude_labels")])
def test_scope_key_requires_its_provider(kind, key):
    errors = validate_config(config(kind, **{key: []}))
    assert len(errors) == 1
    assert f"{key} is only supported for" in errors[0]


@pytest.mark.parametrize("kind,key", [("imap", "active_exclude_folders"), ("gmail_api", "active_exclude_labels")])
@pytest.mark.parametrize("value", [None, "Retained", {}, True, 1, ("Retained",), [None], [1], [""], [" "]])
def test_scope_requires_a_list_of_nonempty_strings(kind, key, value):
    assert validate_config(config(kind, **{key: value})) == [f"Source 'mail': {key} must be a list of nonempty names"]


@pytest.mark.parametrize("kind,key", [("imap", "active_exclude_folders"), ("gmail_api", "active_exclude_labels")])
@pytest.mark.parametrize("control", ["\n", "\r", "\t", "\x00", "\x7f", "\x85"])
def test_scope_rejects_control_characters(kind, key, control):
    assert validate_config(config(kind, **{key: ["Retained" + control]})) == [
        f"Source 'mail': {key} cannot contain control characters"
    ]


@pytest.mark.parametrize("name", ['Retained"', "Retained\\"])
def test_gmail_scope_rejects_query_delimiters_but_imap_keeps_literal_names(name):
    assert validate_config(config("gmail_api", active_exclude_labels=[name])) == [
        "Source 'mail': active_exclude_labels cannot contain quotes or backslashes"
    ]
    assert validate_config(config("imap", active_exclude_folders=[name])) == []


def test_scope_signature_is_order_independent_and_provider_specific():
    signature = active_scope_signature("gmail", ["Retained", "Saved", "Retained"])
    assert signature == active_scope_signature("gmail_api", ["Saved", "Retained"])
    assert signature != active_scope_signature("imap", ["Saved", "Retained"])
    assert signature != active_scope_signature("gmail_api", ["Saved"])
    assert active_scope_signature("imap", None) == active_scope_signature("imap", [])
