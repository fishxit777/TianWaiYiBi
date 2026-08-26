import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from conftest import login_admin, set_public_csrf
from tianwai.analytics import build_demand_radar
from tianwai.db import get_db, migrate_database


def _idea_id(connection, slug="brand-world-forge"):
    return connection.execute("SELECT id FROM ideas WHERE slug = ?", (slug,)).fetchone()["id"]


def _event(connection, idea_id, name, session_id, value="", *, automated=0, source="direct"):
    connection.execute(
        """
        INSERT INTO analytics_events
            (event_name, idea_id, source, session_id, event_value, event_version,
             is_automated, page_path, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, '/ideas/test', ?)
        """,
        (
            name,
            idea_id,
            source,
            session_id,
            value,
            automated,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def test_analytics_schema_supports_deduplication_quality_and_order_attribution(app):
    with app.app_context():
        connection = get_db()
        analytics_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(analytics_events)")
        }
        order_columns = {row["name"] for row in connection.execute("PRAGMA table_info(orders)")}
        indexes = {
            row["name"] for row in connection.execute("PRAGMA index_list(analytics_events)")
        }

    assert {"event_value", "event_version", "dedupe_key", "is_automated", "page_path"} <= analytics_columns
    assert "analytics_session_id" in order_columns
    assert {"idx_analytics_dedupe", "idx_analytics_idea_funnel", "idx_analytics_session_time"} <= indexes


def test_legacy_database_adds_radar_columns_before_creating_dependent_indexes(tmp_path):
    database_path = tmp_path / "legacy-radar.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            idea_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payment_provider TEXT NOT NULL DEFAULT 'mock',
            payment_ref TEXT,
            payment_token_hash TEXT NOT NULL UNIQUE,
            access_token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            paid_at TEXT
        );
        CREATE TABLE analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            idea_id INTEGER,
            source TEXT NOT NULL,
            session_id TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    schema_path = Path(__file__).parents[1] / "tianwai" / "schema.sql"
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    migrate_database(connection)

    analytics_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(analytics_events)")
    }
    order_columns = {row[1] for row in connection.execute("PRAGMA table_info(orders)")}
    indexes = {row[1] for row in connection.execute("PRAGMA index_list(analytics_events)")}
    connection.close()

    assert {"event_value", "event_version", "dedupe_key", "is_automated", "page_path"} <= analytics_columns
    assert "analytics_session_id" in order_columns
    assert {"idx_analytics_dedupe", "idx_analytics_idea_funnel", "idx_analytics_session_time"} <= indexes


def test_base_schemas_defer_migration_dependent_indexes():
    schema_directory = Path(__file__).parents[1] / "tianwai"
    for filename in ("schema.sql", "schema_postgres.sql"):
        schema = (schema_directory / filename).read_text(encoding="utf-8")
        assert "idx_analytics_dedupe" not in schema
        assert "idx_analytics_session_time" not in schema
        assert "idx_orders_analytics_session" not in schema


def test_public_interest_is_anonymous_validated_and_deduplicated(app, client):
    csrf = set_public_csrf(client)
    payload = {"event_name": "interest_registered", "idea_slug": "brand-world-forge"}

    first = client.post("/api/events", json=payload, headers={"X-CSRF-Token": csrf})
    second = client.post("/api/events", json=payload, headers={"X-CSRF-Token": csrf})
    invalid = client.post(
        "/api/events",
        json={"event_name": "reading_depth", "idea_slug": "brand-world-forge", "event_value": "99"},
        headers={"X-CSRF-Token": csrf},
    )

    assert first.status_code == 200 and first.get_json()["recorded"] is True
    assert second.status_code == 200 and second.get_json()["recorded"] is False
    assert invalid.status_code == 400
    with app.app_context():
        row = get_db().execute(
            "SELECT source, session_id, event_value FROM analytics_events WHERE event_name = 'interest_registered'"
        ).fetchone()
    assert row["source"] == "direct"
    assert row["session_id"]
    assert row["event_value"] == ""


def test_demand_radar_gates_small_samples_and_excludes_automated_traffic(app):
    with app.app_context():
        connection = get_db()
        idea_id = _idea_id(connection)
        for index in range(9):
            _event(connection, idea_id, "view_idea", f"small-{index}")
        _event(connection, idea_id, "view_idea", "bot-session", automated=1)
        connection.commit()

        first = build_demand_radar(connection, days=30, payment_ready=False)
        item = next(entry for entry in first["items"] if entry["slug"] == "brand-world-forge")
        assert item["funnel"]["visitors"] == 9
        assert item["evidence_index"] is None
        assert item["confidence"]["level"] == "insufficient"
        assert first["data_quality"]["automated_excluded"] == 1

        _event(connection, idea_id, "view_idea", "qualified-10")
        for index in range(6):
            _event(connection, idea_id, "reading_depth", f"small-{index}", "50")
        for index in range(4):
            _event(connection, idea_id, "engaged_read", f"small-{index}", "45")
        for index in range(3):
            _event(connection, idea_id, "interest_registered", f"small-{index}")
        connection.commit()

        qualified = build_demand_radar(connection, days="invalid", payment_ready=False)
        item = next(entry for entry in qualified["items"] if entry["slug"] == "brand-world-forge")

    assert qualified["window_days"] == 30
    assert item["confidence"]["level"] == "exploratory"
    assert item["evidence_index"] is not None
    assert item["diagnosis"]["code"] == "prelaunch_signal"
    assert item["funnel"]["checkout"] == 0
    assert qualified["method"]["claim"] == "需求證據指數，不是購買機率"


def test_admin_dashboard_exposes_auditable_radar_and_window_controls(client):
    login_admin(client)
    page = client.get("/admin").get_data(as_text=True)
    response = client.get("/admin/api/dashboard?analytics_days=7")

    assert "仙策需求雷達" in page
    assert 'data-demand-days="7"' in page
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["demand_radar"]["window_days"] == 7
    assert payload["demand_radar"]["method"]["minimum_sample"] == 10
    assert "conversion_available" in payload["metrics"]
