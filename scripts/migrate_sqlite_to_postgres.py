"""One-way, integrity-checked migration from TianWaiYiBi SQLite to PostgreSQL.

The PostgreSQL connection string is read only from an environment variable so it
does not appear in shell history or process arguments. Reports contain counts and
SHA-256 checksums only; they never contain row values or credentials.
"""

import argparse
import base64
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


MIGRATION_TABLES = (
    "settings",
    "ideas",
    "customers",
    "section_messages",
    "customer_devices",
    "orders",
    "order_consents",
    "activation_codes",
    "customer_login_codes",
    "customer_sessions",
    "access_events",
    "risk_incidents",
    "notification_queue",
    "email_events",
    "payment_events",
    "refund_events",
    "analytics_events",
    "line_events",
    "admin_sessions",
    "admin_webauthn_credentials",
    "admin_webauthn_challenges",
    "admin_recovery_codes",
    "admin_login_attempts",
    "security_events",
    "blocked_ips",
    "audit_logs",
)

SEED_ONLY_TABLES = {"settings", "ideas"}


def _canonical_value(value):
    if isinstance(value, bytes):
        return {"bytes_b64": base64.b64encode(value).decode("ascii")}
    return value


def table_checksum(rows):
    canonical_rows = []
    for row in rows:
        normalized = {
            str(key): _canonical_value(value)
            for key, value in dict(row).items()
        }
        canonical_rows.append(normalized)
    canonical_rows.sort(
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    payload = json.dumps(
        canonical_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sqlite_table_names(connection):
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _sqlite_table_columns(connection, table):
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]


def snapshot_sqlite(source_path, include_rows=False):
    connection = sqlite3.connect(Path(source_path))
    connection.row_factory = sqlite3.Row
    try:
        existing = _sqlite_table_names(connection)
        snapshot = {}
        for table in MIGRATION_TABLES:
            if table not in existing:
                continue
            columns = _sqlite_table_columns(connection, table)
            rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]
            entry = {
                "count": len(rows),
                "checksum": table_checksum(rows),
                "columns": columns,
            }
            if include_rows:
                entry["rows"] = rows
            snapshot[table] = entry
        return snapshot
    finally:
        connection.close()


def validate_destination_counts(counts, allow_nonempty=False):
    if allow_nonempty:
        return
    occupied = {
        table: int(count)
        for table, count in counts.items()
        if table not in SEED_ONLY_TABLES and int(count) > 0
    }
    if occupied:
        names = ", ".join(sorted(occupied))
        raise RuntimeError(f"PostgreSQL 目的端已有營運資料，拒絕覆寫：{names}")


def build_integrity_report(source, destination, source_name):
    report = {
        "status": "verified",
        "source": Path(source_name).name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": {},
    }
    for table in sorted(set(source) | set(destination)):
        source_entry = source.get(table, {"count": 0, "checksum": table_checksum([])})
        destination_entry = destination.get(table, {"count": 0, "checksum": table_checksum([])})
        verified = (
            int(source_entry["count"]) == int(destination_entry["count"])
            and source_entry["checksum"] == destination_entry["checksum"]
        )
        report["tables"][table] = {
            "count": int(source_entry["count"]),
            "source_checksum": source_entry["checksum"],
            "destination_checksum": destination_entry["checksum"],
            "verified": verified,
        }
        if not verified:
            report["status"] = "mismatch"
    return report


def _postgres_table_columns(connection, table):
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [row["column_name"] for row in rows]


def _destination_counts(connection):
    from psycopg import sql

    counts = {}
    for table in MIGRATION_TABLES:
        if not _postgres_table_columns(connection, table):
            continue
        row = connection.execute(
            sql.SQL("SELECT COUNT(*) AS count FROM {}").format(sql.Identifier(table))
        ).fetchone()
        counts[table] = int(row["count"])
    return counts


def snapshot_postgres(connection, source_snapshot):
    from psycopg import sql

    snapshot = {}
    for table, source_entry in source_snapshot.items():
        destination_columns = set(_postgres_table_columns(connection, table))
        columns = [name for name in source_entry["columns"] if name in destination_columns]
        if not columns:
            continue
        query = sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(", ").join(sql.Identifier(name) for name in columns),
            sql.Identifier(table),
        )
        rows = [dict(row) for row in connection.execute(query).fetchall()]
        snapshot[table] = {
            "count": len(rows),
            "checksum": table_checksum(rows),
            "columns": columns,
        }
    return snapshot


def _reset_identity(connection, table):
    from psycopg import sql

    if "id" not in _postgres_table_columns(connection, table):
        return
    query = sql.SQL(
        """
        SELECT setval(
            pg_get_serial_sequence(%s, 'id'),
            COALESCE(MAX(id), 1),
            MAX(id) IS NOT NULL
        ) FROM {}
        """
    ).format(sql.Identifier(table))
    connection.execute(query, (table,))


def migrate(source_path, database_url, allow_nonempty=False):
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    source_path = Path(source_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"找不到 SQLite 來源：{source_path}")
    source = snapshot_sqlite(source_path, include_rows=True)
    safe_source = {
        table: {key: value for key, value in entry.items() if key != "rows"}
        for table, entry in source.items()
    }

    project_root = Path(__file__).resolve().parents[1]
    schema = (project_root / "tianwai" / "schema_postgres.sql").read_text(encoding="utf-8")
    with psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=10,
        application_name="tianwai-yibi-migration",
    ) as connection:
        try:
            connection.execute(schema, prepare=False)
            counts = _destination_counts(connection)
            validate_destination_counts(counts, allow_nonempty=allow_nonempty)
            if not allow_nonempty:
                connection.execute("DELETE FROM ideas")
                connection.execute("DELETE FROM settings")

            for table in MIGRATION_TABLES:
                entry = source.get(table)
                if not entry or not entry["rows"]:
                    continue
                destination_columns = set(_postgres_table_columns(connection, table))
                columns = [name for name in entry["columns"] if name in destination_columns]
                query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(sql.Identifier(name) for name in columns),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                )
                with connection.cursor() as cursor:
                    cursor.executemany(
                        query,
                        [tuple(row.get(name) for name in columns) for row in entry["rows"]],
                    )
                _reset_identity(connection, table)

            destination = snapshot_postgres(connection, safe_source)
            report = build_integrity_report(safe_source, destination, source_path.name)
            if report["status"] != "verified":
                raise RuntimeError("PostgreSQL 遷移完整性核對失敗；交易已回滾")
            connection.commit()
            return report
        except Exception:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Migrate TianWaiYiBi SQLite data to PostgreSQL")
    parser.add_argument("--source", default=os.environ.get("DATABASE_PATH", "data/tianwai.db"))
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--allow-nonempty", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()

    database_url = os.environ.get(args.database_url_env, "").strip()
    if not database_url:
        raise SystemExit(f"環境變數 {args.database_url_env} 尚未設定")
    report = migrate(args.source, database_url, allow_nonempty=args.allow_nonempty)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
