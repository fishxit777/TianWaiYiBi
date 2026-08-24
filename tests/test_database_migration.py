import json
import inspect
import sqlite3

import pytest

from tianwai.db import _migrate_section_messages, _migrate_section_messages_postgres

from scripts.migrate_sqlite_to_postgres import (
    MIGRATION_TABLES,
    build_integrity_report,
    snapshot_sqlite,
    table_checksum,
    validate_destination_counts,
)


def _source_database(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE ideas (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, title TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, order_no TEXT UNIQUE, customer_email TEXT);
        INSERT INTO settings VALUES ('idea_price', '199', '2026-08-23T00:00:00+00:00');
        INSERT INTO ideas VALUES (3, 'test-idea', '測試仙策');
        INSERT INTO orders VALUES (9, 'TWYB-TEST-9', 'owner@example.com');
        """
    )
    connection.commit()
    connection.close()


def test_migration_table_order_keeps_foreign_key_dependencies():
    assert MIGRATION_TABLES.index("customers") < MIGRATION_TABLES.index("section_messages")
    assert MIGRATION_TABLES.index("customers") < MIGRATION_TABLES.index("customer_devices")
    assert MIGRATION_TABLES.index("ideas") < MIGRATION_TABLES.index("orders")
    assert MIGRATION_TABLES.index("orders") < MIGRATION_TABLES.index("activation_codes")
    assert MIGRATION_TABLES.index("access_events") < MIGRATION_TABLES.index("risk_incidents")


def test_snapshot_sqlite_reports_counts_and_hashes_without_values(tmp_path):
    source = tmp_path / "source.db"
    _source_database(source)
    snapshot = snapshot_sqlite(source)

    assert snapshot["settings"]["count"] == 1
    assert snapshot["ideas"]["count"] == 1
    assert snapshot["orders"]["count"] == 1
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert "owner@example.com" not in serialized
    assert "TWYB-TEST-9" not in serialized
    assert len(snapshot["orders"]["checksum"]) == 64


def test_table_checksum_is_deterministic_and_sensitive_to_changes():
    rows = [{"id": 2, "value": "b"}, {"id": 1, "value": "a"}]
    assert table_checksum(rows) == table_checksum(list(reversed(rows)))
    changed = [{"id": 2, "value": "changed"}, {"id": 1, "value": "a"}]
    assert table_checksum(rows) != table_checksum(changed)


def test_destination_rejects_business_rows_by_default():
    counts = {table: 0 for table in MIGRATION_TABLES}
    counts["settings"] = 1
    counts["ideas"] = 6
    validate_destination_counts(counts, allow_nonempty=False)

    counts["orders"] = 1
    with pytest.raises(RuntimeError, match="orders"):
        validate_destination_counts(counts, allow_nonempty=False)


def test_integrity_report_contains_only_metadata():
    source = {"orders": {"count": 1, "checksum": "a" * 64}}
    destination = {"orders": {"count": 1, "checksum": "a" * 64}}
    report = build_integrity_report(source, destination, "source.db")
    assert report["status"] == "verified"
    assert report["source"] == "source.db"
    assert report["tables"]["orders"]["count"] == 1
    assert "database_url" not in json.dumps(report)


def test_integrity_report_fails_on_count_or_checksum_mismatch():
    source = {"orders": {"count": 1, "checksum": "a" * 64}}
    destination = {"orders": {"count": 2, "checksum": "b" * 64}}
    report = build_integrity_report(source, destination, "source.db")
    assert report["status"] == "mismatch"
    assert report["tables"]["orders"]["verified"] is False


def test_legacy_sqlite_conversations_upgrade_without_losing_existing_rows(tmp_path):
    database = tmp_path / "legacy-conversations.db"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE ideas (id INTEGER PRIMARY KEY);
        CREATE TABLE customers (id INTEGER PRIMARY KEY);
        CREATE TABLE section_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL UNIQUE,
            section_key TEXT NOT NULL,
            idea_id INTEGER REFERENCES ideas(id),
            author_type TEXT NOT NULL CHECK (author_type IN ('customer', 'admin')),
            customer_id INTEGER REFERENCES customers(id),
            reply_to_id INTEGER REFERENCES section_messages(id),
            visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
            status TEXT NOT NULL CHECK (status IN ('pending', 'published', 'hidden')),
            body TEXT NOT NULL CHECK (length(body) BETWEEN 2 AND 800),
            moderated_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (author_type = 'admin' OR customer_id IS NOT NULL),
            CHECK (visibility = 'public' OR customer_id IS NOT NULL)
        );
        INSERT INTO ideas VALUES (1);
        INSERT INTO customers VALUES (1);
        INSERT INTO section_messages
            (public_id, section_key, idea_id, author_type, customer_id,
             visibility, status, body, created_at, updated_at)
        VALUES
            ('MSG-LEGACY', 'idea-detail', 1, 'customer', 1,
             'public', 'published', '既有留言', '2026-08-24T00:00:00+00:00',
             '2026-08-24T00:00:00+00:00');
        """
    )

    _migrate_section_messages(connection)

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(section_messages)")
    }
    assert {"visitor_token_hash", "source_hash"} <= columns
    preserved = connection.execute(
        "SELECT public_id, body FROM section_messages WHERE id = 1"
    ).fetchone()
    assert dict(preserved) == {"public_id": "MSG-LEGACY", "body": "既有留言"}
    connection.execute(
        """
        INSERT INTO section_messages
            (public_id, section_key, idea_id, author_type, visitor_token_hash,
             source_hash, visibility, status, body, created_at, updated_at)
        VALUES
            ('MSG-VISITOR', 'idea-detail', 1, 'visitor', 'v-hash', 's-hash',
             'public', 'pending', '訪客留言', '2026-08-24T00:00:00+00:00',
             '2026-08-24T00:00:00+00:00')
        """
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO section_messages
                (public_id, section_key, idea_id, author_type, visitor_token_hash,
                 source_hash, visibility, status, body, created_at, updated_at)
            VALUES
                ('MSG-VISITOR-PRIVATE', 'idea-detail', 1, 'visitor', 'v-hash-2',
                 's-hash', 'private', 'published', '不允許私密訪客留言',
                 '2026-08-24T00:00:00+00:00', '2026-08-24T00:00:00+00:00')
            """
        )
    connection.close()


def test_postgres_conversation_migration_serializes_worker_startup():
    source = inspect.getsource(_migrate_section_messages_postgres)
    assert "pg_advisory_xact_lock" in source
    assert "ADD COLUMN IF NOT EXISTS visitor_token_hash" in source
    assert "ADD COLUMN IF NOT EXISTS source_hash" in source
