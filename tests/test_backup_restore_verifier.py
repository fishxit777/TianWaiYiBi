import json
import subprocess
import sys
from pathlib import Path

from scripts.verify_postgres_backup_restore import build_restore_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _entry(count, checksum):
    return {"count": count, "checksum": checksum}


def test_build_restore_report_verifies_table_count_rows_and_checksums():
    source = {
        "ideas": _entry(6, "a" * 64),
        "orders": _entry(2, "b" * 64),
    }
    restored = {
        "ideas": _entry(6, "a" * 64),
        "orders": _entry(2, "b" * 64),
    }

    report = build_restore_report(source, restored)

    assert report["status"] == "verified"
    assert report["source_table_count"] == 2
    assert report["restored_table_count"] == 2
    assert report["source_row_count"] == 8
    assert report["restored_row_count"] == 8
    assert all(entry["verified"] for entry in report["tables"].values())


def test_build_restore_report_marks_missing_or_changed_tables_as_mismatch():
    source = {
        "ideas": _entry(6, "a" * 64),
        "orders": _entry(2, "b" * 64),
    }
    restored = {"ideas": _entry(7, "c" * 64)}

    report = build_restore_report(source, restored)

    assert report["status"] == "mismatch"
    assert report["tables"]["ideas"]["verified"] is False
    assert report["tables"]["orders"]["verified"] is False
    assert report["tables"]["orders"]["restored_count"] == 0


def test_restore_report_contains_no_connection_or_row_values():
    secret_value = "owner@example.com"
    report = build_restore_report(
        {"orders": _entry(1, "d" * 64)},
        {"orders": _entry(1, "d" * 64)},
    )
    serialized = json.dumps(report, ensure_ascii=False)

    assert secret_value not in serialized
    assert "postgresql://" not in serialized
    assert set(report["tables"]["orders"]) == {
        "source_count",
        "restored_count",
        "source_checksum",
        "restored_checksum",
        "verified",
    }


def test_restore_verifier_supports_direct_cli_invocation():
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "verify_postgres_backup_restore.py"),
            "--help",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Verify a TianWaiYiBi PostgreSQL backup restore" in result.stdout
