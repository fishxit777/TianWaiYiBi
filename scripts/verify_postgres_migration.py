"""Verify SQLite and PostgreSQL row counts/checksums without changing either."""

import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from scripts.migrate_sqlite_to_postgres import (
    build_integrity_report,
    snapshot_postgres,
    snapshot_sqlite,
)


def main():
    parser = argparse.ArgumentParser(description="Verify TianWaiYiBi PostgreSQL migration")
    parser.add_argument("--source", default=os.environ.get("DATABASE_PATH", "data/tianwai.db"))
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--report")
    args = parser.parse_args()

    database_url = os.environ.get(args.database_url_env, "").strip()
    if not database_url:
        raise SystemExit(f"環境變數 {args.database_url_env} 尚未設定")
    source_path = Path(args.source).resolve()
    source = snapshot_sqlite(source_path)
    with psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=10,
        application_name="tianwai-yibi-verification",
    ) as connection:
        destination = snapshot_postgres(connection, source)
    report = build_integrity_report(source, destination, source_path.name)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    raise SystemExit(0 if report["status"] == "verified" else 1)


if __name__ == "__main__":
    main()
