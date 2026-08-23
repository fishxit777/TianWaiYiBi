import json
import sqlite3

import pytest

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
