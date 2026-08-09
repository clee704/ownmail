"""Tests for reconcile: the download filter evaluated against the archive."""

import sqlite3

from ownmail import reconcile, roles
from ownmail.database import ArchiveDatabase

ACCOUNT = "alice@example.com"


def _filter(exclude_roles=None, exclude_folders=()):
    return reconcile.SourceFilter(
        name="personal",
        account=ACCOUNT,
        exclude_roles=roles.resolve_exclude_roles(exclude_roles),
        exclude_folders=frozenset(exclude_folders),
    )


def _classify(labels, source_filter=None):
    return reconcile.classify("eid", ACCOUNT, labels, source_filter or _filter())


class TestSourceFilter:
    """The filter reconcile compares against, built from config."""

    def test_reads_the_configured_roles(self):
        config = {"sources": [{"name": "personal", "account": ACCOUNT, "exclude_roles": []}]}
        (source_filter,) = reconcile.source_filters(config)
        assert source_filter.exclude_roles == roles.FIXED_EXCLUDE_ROLES
        assert not source_filter.rejects("INBOX")

    def test_an_absent_key_takes_the_default(self):
        config = {"sources": [{"name": "personal", "account": ACCOUNT}]}
        (source_filter,) = reconcile.source_filters(config)
        assert source_filter.rejects("INBOX")
        assert source_filter.rejects("[Gmail]/Trash")

    def test_named_folders_are_matched_exactly(self):
        config = {"sources": [{"name": "personal", "account": ACCOUNT, "exclude_folders": ["Newsletters"]}]}
        (source_filter,) = reconcile.source_filters(config)
        assert source_filter.rejects("Newsletters")
        assert not source_filter.rejects("newsletters")

    def test_one_filter_per_account(self):
        """Archived rows record the account, so a second source on it is moot."""
        config = {
            "sources": [
                {"name": "first", "account": ACCOUNT},
                {"name": "second", "account": ACCOUNT, "exclude_roles": []},
            ]
        }
        assert [f.name for f in reconcile.source_filters(config)] == ["first"]

    def test_a_source_without_an_account_is_skipped(self):
        assert reconcile.source_filters({"sources": [{"name": "half-configured"}]}) == []

    def test_describe_names_both_halves_of_the_filter(self):
        source_filter = _filter(exclude_roles=["inbox"], exclude_folders=["Newsletters"])
        described = source_filter.describe()
        assert "inbox" in described and "trash" in described
        assert "Newsletters" in described


class TestClassify:
    """Which archived messages the filter rejects, and which are ambiguous."""

    def test_a_message_the_filter_admits_is_not_a_candidate(self):
        assert _classify(["Receipts"]) is None

    def test_a_message_with_no_labels_is_not_a_candidate(self):
        assert _classify([]) is None

    def test_only_an_excluded_label_can_be_swept(self):
        candidate = _classify(["[Gmail]/Trash"])
        assert candidate.rejected == ("[Gmail]/Trash",)
        assert candidate.kept == ()

    def test_a_real_label_alongside_is_reported_not_swept(self):
        """It was filed somewhere the filter can't see. AC #5."""
        candidate = _classify(["INBOX", "Receipts"])
        assert candidate.rejected == ("INBOX",)
        assert candidate.kept == ("Receipts",)

    def test_gmail_classifiers_are_not_filing(self):
        """Gmail hangs these on mail nobody has touched."""
        candidate = _classify(["INBOX", "IMPORTANT", "CATEGORY_PROMOTIONS"])
        assert candidate.kept == ()

    def test_a_star_is_something_the_owner_did(self):
        candidate = _classify(["INBOX", "STARRED"])
        assert candidate.kept == ("STARRED",)

    def test_the_catch_all_folder_is_not_filing(self):
        """Every Gmail-over-IMAP message is in All Mail; it says nothing."""
        candidate = _classify(["[Gmail]/All Mail", "[Gmail]/Trash"])
        assert candidate.kept == ()

    def test_unread_from_an_old_archive_is_not_filing(self):
        candidate = _classify(["INBOX", "UNREAD"])
        assert candidate.kept == ()

    def test_a_role_the_filter_admits_counts_as_filing(self):
        """Sent mail is archived on purpose — report it rather than sweep it."""
        candidate = _classify(["[Gmail]/Trash", "[Gmail]/Sent Mail"])
        assert candidate.kept == ("[Gmail]/Sent Mail",)

    def test_a_widened_filter_stops_rejecting(self):
        """AC #2: the same message, read against a filter that admits inbox."""
        assert _classify(["INBOX"], _filter(exclude_roles=[])) is None

    def test_a_narrowed_filter_starts_rejecting(self):
        assert _classify(["Newsletters"], _filter(exclude_folders=["Newsletters"])).kept == ()


class TestBuildPlan:
    """The whole sweep, against a real archive."""

    DEFAULT_CONFIG = {"sources": [{"name": "personal", "account": ACCOUNT}]}

    def _archive(self, temp_dir, rows, config=None):
        """Build a database from (provider_id, account, labels) rows."""
        db = ArchiveDatabase(temp_dir)
        for provider_id, account, labels in rows:
            email_id = f"{provider_id}-{account}"
            db.mark_downloaded(email_id, provider_id, f"{provider_id}.eml", account=account)
            with sqlite3.connect(db.db_path) as conn:
                (rowid,) = conn.execute("SELECT rowid FROM emails WHERE email_id = ?", (email_id,)).fetchone()
                for label in labels:
                    conn.execute(
                        "INSERT INTO email_labels (email_rowid, label, email_date) VALUES (?, ?, ?)",
                        (rowid, label, "2024-01-01T00:00:00+00:00"),
                    )
                conn.commit()
        return db, self.DEFAULT_CONFIG if config is None else config

    def _plan(self, temp_dir, rows, config=None):
        db, config = self._archive(temp_dir, rows, config)
        return reconcile.build_plan(db.db_path, config), db

    def test_splits_the_sweep_from_the_reported(self, temp_dir):
        plan, _ = self._plan(
            temp_dir,
            [
                ("m1", ACCOUNT, ["Deleted Items"]),
                ("m2", ACCOUNT, ["INBOX", "Receipts"]),
                ("m3", ACCOUNT, ["Receipts"]),
            ],
        )
        assert [c.email_id for c in plan.sweep] == [f"m1-{ACCOUNT}"]
        assert [c.email_id for c in plan.reported] == [f"m2-{ACCOUNT}"]

    def test_an_edited_filter_changes_the_answer(self, temp_dir):
        """AC #2: config, not code, decides what reconcile rejects."""
        rows = [("m1", ACCOUNT, ["INBOX"])]
        eager = {"sources": [{"name": "personal", "account": ACCOUNT, "exclude_roles": []}]}
        plan, _ = self._plan(temp_dir, rows, eager)
        assert plan.sweep == []

        plan, _ = self._plan(temp_dir / "narrowed", rows)
        assert len(plan.sweep) == 1

    def test_each_account_is_read_against_its_own_filter(self, temp_dir):
        config = {
            "sources": [
                {"name": "personal", "account": ACCOUNT},
                {"name": "work", "account": "bob@work.com", "exclude_roles": []},
            ]
        }
        plan, _ = self._plan(
            temp_dir,
            [("m1", ACCOUNT, ["INBOX"]), ("m2", "bob@work.com", ["INBOX"])],
            config,
        )
        assert [c.account for c in plan.sweep] == [ACCOUNT]

    def test_mail_with_no_configured_source_is_reported_and_skipped(self, temp_dir):
        plan, _ = self._plan(temp_dir, [("m1", "imported@elsewhere.com", ["Deleted Items"])])
        assert plan.sweep == []
        assert plan.unconfigured == [("imported@elsewhere.com", 1)]

    def test_mail_already_in_the_bin_is_left_out(self, temp_dir):
        """Otherwise an applied run would report the same mail forever."""
        db, config = self._archive(temp_dir, [("m1", ACCOUNT, ["Deleted Items"])])
        db.trash_email(f"m1-{ACCOUNT}", "trash/m1.eml")
        plan = reconcile.build_plan(db.db_path, config)
        assert plan.sweep == []
        assert plan.unconfigured == []

    def test_no_sources_means_nothing_to_compare_against(self, temp_dir):
        plan, _ = self._plan(temp_dir, [("m1", ACCOUNT, ["Deleted Items"])], {})
        assert plan.filters == []
        assert plan.sweep == []

    def test_an_archive_the_filter_agrees_with_yields_nothing(self, temp_dir):
        plan, _ = self._plan(temp_dir, [("m1", ACCOUNT, ["Receipts"])])
        assert plan.sweep == []
        assert plan.reported == []


class TestCountsByLabel:
    """AC #1's breakdown: which part of the filter is responsible."""

    def _candidate(self, rejected, account=ACCOUNT):
        return reconcile.Candidate(email_id="e", account=account, rejected=rejected, kept=())

    def test_groups_by_label_and_account_largest_first(self):
        counts = reconcile.counts_by_label(
            [
                self._candidate(("TRASH",)),
                self._candidate(("TRASH",)),
                self._candidate(("INBOX",), account="bob@work.com"),
            ]
        )
        assert counts == [("TRASH", ACCOUNT, 2), ("INBOX", "bob@work.com", 1)]

    def test_a_message_rejected_twice_is_counted_under_both(self):
        counts = reconcile.counts_by_label([self._candidate(("INBOX", "TRASH"))])
        assert sorted(counts) == [("INBOX", ACCOUNT, 1), ("TRASH", ACCOUNT, 1)]
