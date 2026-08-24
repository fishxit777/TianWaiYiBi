"""Compare production and restored PostgreSQL data without exposing row values.

Connection strings are read only from environment variables. Output contains
table names, row counts, and canonical SHA-256 checksums; it never contains a
connection string or a database row.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from scripts.migrate_sqlite_to_postgres import table_checksum


EMPTY_CHECKSUM = table_checksum([])


def _table_names(connection, schema):
    rows = connection.execute(
        """
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = %s
        ORDER BY tablename
        """,
        (schema,),
    ).fetchall()
    return [row["tablename"] for row in rows]


def snapshot_postgres_database(connection, schema="public"):
    """Return a value-free integrity snapshot of every ordinary table."""

    snapshot = {}
    for table in _table_names(connection, schema):
        query = sql.SQL("SELECT to_jsonb(t) AS row_data FROM {}.{} AS t").format(
            sql.Identifier(schema),
            sql.Identifier(table),
        )
        rows = [dict(row) for row in connection.execute(query).fetchall()]
        snapshot[table] = {
            "count": len(rows),
            "checksum": table_checksum(rows),
        }
    return snapshot


def build_restore_report(source, restored):
    tables = {}
    status = "verified"
    for table in sorted(set(source) | set(restored)):
        source_entry = source.get(table, {"count": 0, "checksum": EMPTY_CHECKSUM})
        restored_entry = restored.get(table, {"count": 0, "checksum": EMPTY_CHECKSUM})
        verified = (
            table in source
            and table in restored
            and int(source_entry["count"]) == int(restored_entry["count"])
            and source_entry["checksum"] == restored_entry["checksum"]
        )
        tables[table] = {
            "source_count": int(source_entry["count"]),
            "restored_count": int(restored_entry["count"]),
            "source_checksum": source_entry["checksum"],
            "restored_checksum": restored_entry["checksum"],
            "verified": verified,
        }
        if not verified:
            status = "mismatch"

    source_row_count = sum(int(entry["count"]) for entry in source.values())
    restored_row_count = sum(int(entry["count"]) for entry in restored.values())
    if len(source) != len(restored) or source_row_count != restored_row_count:
        status = "mismatch"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_table_count": len(source),
        "restored_table_count": len(restored),
        "source_row_count": source_row_count,
        "restored_row_count": restored_row_count,
        "tables": tables,
    }


def _snapshot(database_url, schema, application_name):
    with psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=15,
        application_name=application_name,
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return snapshot_postgres_database(connection, schema=schema)


def main():
    parser = argparse.ArgumentParser(description="Verify a TianWaiYiBi PostgreSQL backup restore")
    parser.add_argument("--source-url-env", default="BACKUP_SOURCE_DATABASE_URL")
    parser.add_argument("--restored-url-env", default="RESTORED_DATABASE_URL")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--report")
    args = parser.parse_args()

    source_url = os.environ.get(args.source_url_env, "").strip()
    restored_url = os.environ.get(args.restored_url_env, "").strip()
    if not source_url:
        raise SystemExit(f"Environment variable {args.source_url_env} is not configured")
    if not restored_url:
        raise SystemExit(f"Environment variable {args.restored_url_env} is not configured")

    source = _snapshot(source_url, args.schema, "tianwai-backup-source-verification")
    restored = _snapshot(restored_url, args.schema, "tianwai-backup-restore-verification")
    report = build_restore_report(source, restored)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    raise SystemExit(0 if report["status"] == "verified" else 1)


if __name__ == "__main__":
    main()
