"""Tests for configuration loading and validation."""

import tempfile
from pathlib import Path

import pytest

from ownmail.config import (
    get_archive_root,
    get_source_by_account,
    get_source_by_name,
    get_sources,
    load_config,
    parse_secret_ref,
    validate_config,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_empty_when_no_file(self, temp_dir):
        """Test that empty dict is returned when no config exists."""
        config = load_config(config_path=temp_dir / "nonexistent.yaml")
        assert config == {}

    def test_load_config_from_explicit_path(self, temp_dir):
        """Test loading config from explicit path."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text("""
archive_root: /test/path
sources:
  - name: test_source
    type: gmail_api
    account: test@example.com
""")
        config = load_config(config_path=config_path)
        assert config["archive_root"] == "/test/path"
        assert len(config["sources"]) == 1

    def test_load_config_from_cwd(self, temp_dir, monkeypatch):
        """Test loading config from current working directory."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text("archive_root: /from/cwd\n")
        monkeypatch.chdir(temp_dir)
        config = load_config()
        assert config["archive_root"] == "/from/cwd"

    def test_load_config_from_script_dir_fallback(self, temp_dir, monkeypatch):
        """Test loading config from script directory as fallback."""
        # Change to temp_dir so there's no cwd config.yaml
        fallback_dir = temp_dir / "fallback"
        fallback_dir.mkdir()
        config_path = fallback_dir / "config.yaml"
        config_path.write_text("archive_root: /from/script_dir\n")
        # Change to a directory without config.yaml
        monkeypatch.chdir(temp_dir)
        config = load_config(script_dir=fallback_dir)
        assert config.get("archive_root") == "/from/script_dir"


class TestGetArchiveRoot:
    """Tests for get_archive_root function."""

    def test_returns_archive_root_from_config(self):
        """Test getting archive_root from config."""
        config = {"archive_root": "/custom/path"}
        result = get_archive_root(config)
        assert result == Path("/custom/path")

    def test_returns_archive_dir_legacy(self):
        """Test getting archive_dir (legacy key) from config."""
        config = {"archive_dir": "/legacy/path"}
        result = get_archive_root(config)
        assert result == Path("/legacy/path")

    def test_archive_root_takes_precedence(self):
        """Test that archive_root takes precedence over archive_dir."""
        config = {"archive_root": "/new/path", "archive_dir": "/old/path"}
        result = get_archive_root(config)
        assert result == Path("/new/path")

    def test_returns_default_when_not_in_config(self):
        """Test returning default when not specified."""
        config = {}
        result = get_archive_root(config, default=Path("/default"))
        assert result == Path("/default")

    def test_returns_cwd_archive_when_no_default(self):
        """Test returning cwd/archive when no config and no default."""
        config = {}
        result = get_archive_root(config)
        assert result == Path.cwd() / "archive"


class TestGetSources:
    """Tests for get_sources function."""

    def test_returns_empty_list_when_no_sources(self):
        """Test returning empty list when no sources configured."""
        config = {}
        assert get_sources(config) == []

    def test_returns_sources_list(self):
        """Test returning sources list from config."""
        config = {
            "sources": [
                {"name": "source1", "type": "gmail_api"},
                {"name": "source2", "type": "imap"},
            ]
        }
        sources = get_sources(config)
        assert len(sources) == 2
        assert sources[0]["name"] == "source1"
        assert sources[1]["name"] == "source2"


class TestGetSourceByName:
    """Tests for get_source_by_name function."""

    def test_finds_source_by_name(self):
        """Test finding a source by its name."""
        config = {
            "sources": [
                {"name": "gmail_personal", "account": "personal@gmail.com"},
                {"name": "gmail_work", "account": "work@company.com"},
            ]
        }
        source = get_source_by_name(config, "gmail_work")
        assert source is not None
        assert source["account"] == "work@company.com"

    def test_returns_none_when_not_found(self):
        """Test returning None when source name not found."""
        config = {"sources": [{"name": "existing"}]}
        assert get_source_by_name(config, "nonexistent") is None

    def test_returns_none_when_no_sources(self):
        """Test returning None when no sources configured."""
        config = {}
        assert get_source_by_name(config, "any") is None


class TestGetSourceByAccount:
    """Tests for get_source_by_account function."""

    def test_finds_source_by_account(self):
        """Test finding a source by its account email."""
        config = {
            "sources": [
                {"name": "source1", "account": "alice@example.com"},
                {"name": "source2", "account": "bob@example.com"},
            ]
        }
        source = get_source_by_account(config, "bob@example.com")
        assert source is not None
        assert source["name"] == "source2"

    def test_returns_none_when_not_found(self):
        """Test returning None when account not found."""
        config = {"sources": [{"account": "exists@test.com"}]}
        assert get_source_by_account(config, "notfound@test.com") is None


class TestParseSecretRef:
    """Tests for parse_secret_ref function."""

    def test_parses_keychain_ref(self):
        """Test parsing keychain secret reference."""
        result = parse_secret_ref("keychain:oauth-token/alice@gmail.com")
        assert result == {"type": "keychain", "key": "oauth-token/alice@gmail.com"}

    def test_raises_on_invalid_format(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid secret_ref format"):
            parse_secret_ref("no-colon-here")

    def test_raises_on_unsupported_type(self):
        """Test that unsupported type raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported secret_ref type"):
            parse_secret_ref("vault:some/secret")


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_valid_config_returns_no_errors(self):
        """Test that a valid config returns no errors."""
        config = {
            "archive_root": "/test",
            "sources": [
                {
                    "name": "gmail_personal",
                    "type": "gmail_api",
                    "account": "test@gmail.com",
                    "auth": {"secret_ref": "keychain:oauth-token/test@gmail.com"},
                }
            ],
        }
        errors = validate_config(config)
        assert errors == []

    def test_missing_name_field(self):
        """Test error when source missing name."""
        config = {"sources": [{"type": "gmail_api"}]}
        errors = validate_config(config)
        assert any("missing 'name'" in e for e in errors)

    def test_duplicate_source_names(self):
        """Test error on duplicate source names."""
        config = {
            "sources": [
                {"name": "same_name", "type": "gmail_api", "account": "a@test.com",
                 "auth": {"secret_ref": "keychain:a"}},
                {"name": "same_name", "type": "gmail_api", "account": "b@test.com",
                 "auth": {"secret_ref": "keychain:b"}},
            ]
        }
        errors = validate_config(config)
        assert any("Duplicate source name" in e for e in errors)

    def test_missing_type_field(self):
        """Test error when source missing type."""
        config = {
            "sources": [
                {"name": "test", "account": "test@test.com",
                 "auth": {"secret_ref": "keychain:test"}}
            ]
        }
        errors = validate_config(config)
        assert any("missing 'type'" in e for e in errors)

    def test_unknown_source_type(self):
        """Test error on unknown source type."""
        config = {
            "sources": [
                {"name": "test", "type": "unknown", "account": "test@test.com",
                 "auth": {"secret_ref": "keychain:test"}}
            ]
        }
        errors = validate_config(config)
        assert any("unknown type" in e for e in errors)

    def test_missing_account_field(self):
        """Test error when source missing account."""
        config = {
            "sources": [
                {"name": "test", "type": "gmail_api",
                 "auth": {"secret_ref": "keychain:test"}}
            ]
        }
        errors = validate_config(config)
        assert any("missing 'account'" in e for e in errors)

    def test_missing_auth_secret_ref(self):
        """Test error when source missing auth.secret_ref."""
        config = {
            "sources": [
                {"name": "test", "type": "gmail_api", "account": "test@test.com"}
            ]
        }
        errors = validate_config(config)
        assert any("missing 'auth.secret_ref'" in e for e in errors)

    def test_invalid_secret_ref_format(self):
        """Test error on invalid secret_ref format."""
        config = {
            "sources": [
                {"name": "test", "type": "gmail_api", "account": "test@test.com",
                 "auth": {"secret_ref": "invalid-no-colon"}}
            ]
        }
        errors = validate_config(config)
        assert any("Invalid secret_ref" in e for e in errors)

    def test_imap_requires_host(self):
        """Test error when IMAP source missing host."""
        config = {
            "sources": [
                {"name": "test", "type": "imap", "account": "test@test.com",
                 "auth": {"secret_ref": "keychain:test"}}
            ]
        }
        errors = validate_config(config)
        assert any("IMAP requires 'host'" in e for e in errors)

    def test_valid_imap_config(self):
        """Test that valid IMAP config returns no errors."""
        config = {
            "sources": [
                {"name": "work_imap", "type": "imap", "account": "test@company.com",
                 "host": "imap.company.com",
                 "auth": {"secret_ref": "keychain:imap-password/test@company.com"}}
            ]
        }
        errors = validate_config(config)
        assert errors == []

    def test_empty_sources_is_valid(self):
        """Test that empty sources is valid (no errors)."""
        config = {"sources": []}
        errors = validate_config(config)
        assert errors == []
