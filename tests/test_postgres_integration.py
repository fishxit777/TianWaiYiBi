import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from urllib.parse import urlparse, urlsplit, urlunsplit

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").strip(),
    reason="TEST_DATABASE_URL is only provided by the PostgreSQL integration workflow",
)


@pytest.fixture
def pg_app(monkeypatch):
    # These integration checks may create synthetic data: refuse remote targets.
    test_url = os.environ["TEST_DATABASE_URL"]
    assert urlparse(test_url).hostname in {"127.0.0.1", "localhost", "::1"}
    monkeypatch.setenv("DATABASE_URL", test_url)
    monkeypatch.setenv("APP_SECRET_KEY", "postgres-integration-secret-at-least-32-characters")
    monkeypatch.setenv("ADMIN_USERNAME", "integration-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "integration-password-not-for-production")
    monkeypatch.setenv("BASE_URL", "http://localhost")

    from tianwai import create_app

    application = create_app({"TESTING": True})
    # Each case shares only this disposable loopback database; commerce tests
    # must never inherit the public sale state from a previous case.
    from tianwai.db import get_db

    with application.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE ideas SET prepared_price = NULL, sale_state = 'preparing', release_ready = 0"
        )
        connection.commit()
    return application


def test_real_postgres_schema_seed_insert_and_row_mapping(pg_app):
    from tianwai.db import get_db, utc_now
    from tianwai.passkeys import authentication_challenge_allowed, create_challenge

    app = pg_app
    with app.app_context():
        connection = get_db()
        assert connection.backend == "postgresql"
        published = connection.execute(
            "SELECT public_title, sort_order FROM ideas WHERE published = 1 ORDER BY sort_order"
        ).fetchall()
        assert len(published) == 14
        assert [row["sort_order"] for row in published] == list(range(1, 15))
        assert all(row["public_title"].startswith("封印盲策・第") for row in published)
        cursor = connection.execute(
            "INSERT INTO audit_logs (action, target, detail, ip, created_at) VALUES (?, ?, ?, ?, ?)",
            ("postgres_ci", "database", "adapter_verified", "127.0.0.1", utc_now()),
        )
        connection.commit()
        assert cursor.lastrowid > 0
        row = connection.execute(
            "SELECT action, detail FROM audit_logs WHERE action = ?", ("postgres_ci",)
        ).fetchone()
        assert dict(row) == {"action": "postgres_ci", "detail": "adapter_verified"}
        index = connection.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ? AND indexname = ?
            """,
            ("admin_webauthn_challenges", "idx_admin_webauthn_challenge_ip_time"),
        ).fetchone()
        assert index is not None

    with app.test_request_context("/admin/identity/options"):
        assert authentication_challenge_allowed() is True
        for _ in range(10):
            create_challenge("authentication")
        assert authentication_challenge_allowed() is False

    with app.test_request_context("/activate/postgres-session-check"):
        from tianwai.access import _create_customer_session

        raw_session, raw_device, session_id = _create_customer_session(
            "postgres-session-check@example.com"
        )
        assert raw_session
        assert session_id > 0
        assert isinstance(raw_device, str)

    response = app.test_client().get("/healthz")
    assert response.status_code == 200
    assert "postgresql" not in response.get_data(as_text=True).lower()
    assert os.environ["TEST_DATABASE_URL"] not in response.get_data(as_text=True)


def test_real_postgres_legacy_outbox_migration_preserves_claim(pg_app):
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
    from tianwai.db import PostgresConnection, migrate_notification_outbox

    # An isolated schema leaves the app's real synthetic queue untouched.
    schema = "v32_legacy_" + uuid.uuid4().hex
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as native:
        native.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        native.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        native.execute("CREATE TABLE notification_queue (id INTEGER PRIMARY KEY, channel TEXT, status TEXT, attempts INTEGER)")
        native.execute("INSERT INTO notification_queue VALUES (1, 'line', 'pending', 2)")
        adapter = PostgresConnection(native)
        migrate_notification_outbox(adapter)
        adapter.execute(
            "UPDATE notification_queue SET claim_token = 'synthetic-claim', claimed_until = '2099-01-01', "
            "provider_retry_key = 'synthetic-stable-key', next_attempt_at = '2099-01-02' WHERE id = 1"
        )
        adapter.commit()
        before = dict(adapter.execute("SELECT * FROM notification_queue WHERE id = 1").fetchone())
        migrate_notification_outbox(adapter)
        adapter.commit()
        assert dict(adapter.execute("SELECT * FROM notification_queue WHERE id = 1").fetchone()) == before
        assert before["attempts"] == 2
        assert before["retryable"] == 1


def test_real_postgres_two_workers_claim_once_without_network(pg_app, monkeypatch):
    from tianwai import notifications as n
    from tianwai.db import get_db

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "synthetic-pg-line-token")
    monkeypatch.setenv("LINE_ADMIN_USER_ID", "U" + "a" * 32)
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("external send forbidden"))
    ready = n.line_admin_delivery_ready
    monkeypatch.setattr(n, "line_admin_delivery_ready", lambda: False)
    key = "v32-pg-cas-" + uuid.uuid4().hex
    with pg_app.app_context():
        n.queue_admin_messages(key, line_message="synthetic test only")
        row = dict(get_db().execute("SELECT * FROM notification_queue WHERE dedupe_key = ?", ("line:" + key,)).fetchone())
    monkeypatch.setattr(n, "line_admin_delivery_ready", ready)
    delivered = []
    lock = Lock()
    def deliver(claimed):
        with lock:
            delivered.append(claimed["id"])
        return "sent", ""
    monkeypatch.setattr(n, "_deliver", deliver)
    barrier = Barrier(2, timeout=10)
    def claim():
        with pg_app.app_context():
            barrier.wait()
            return n._attempt_delivery(row)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _i: claim(), range(2)))
    assert results.count("sent") == 1
    assert results.count(None) == 1
    assert delivered == [row["id"]]
    with pg_app.app_context():
        stored = get_db().execute("SELECT attempts, status, claim_token FROM notification_queue WHERE id = ?", (row["id"],)).fetchone()
    assert dict(stored) == {"attempts": 1, "status": "sent", "claim_token": ""}


def test_real_postgres_concurrent_login_code_is_single_use(pg_app, monkeypatch):
    from conftest import set_public_csrf
    from test_session_hardening_v32 import _ConnectionProxy, _prepare_login
    from tianwai import access
    from tianwai.db import get_db

    first, second = pg_app.test_client(), pg_app.test_client()
    email, code, code_id, first_csrf = _prepare_login(pg_app, first)
    second_csrf = set_public_csrf(second)
    with second.session_transaction() as state:
        state["customer_login_email"] = email
    barrier = Barrier(2, timeout=10)
    monkeypatch.setattr(access, "get_db", lambda: _ConnectionProxy(get_db(), after_read=barrier.wait))
    def verify(client, csrf):
        return client.post("/customer/login/verify", data={"csrf_token": csrf, "login_code": code})
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(verify, first, first_csrf), workers.submit(verify, second, second_csrf)]
        responses = [future.result(timeout=20) for future in futures]
    assert sorted(response.status_code for response in responses) == [302, 400]
    assert sum(client.get_cookie(access.CUSTOMER_COOKIE) is not None for client in (first, second)) == 1
    with pg_app.app_context():
        assert get_db().execute("SELECT used_at FROM customer_login_codes WHERE id = ?", (code_id,)).fetchone()["used_at"]


def test_real_postgres_two_workers_initialize_empty_database(pg_app, monkeypatch):
    import psycopg
    from psycopg import sql
    from tianwai import create_app, db

    # Each run gets a brand-new synthetic database, never an existing app schema.
    database_name = "v32_boot_" + uuid.uuid4().hex
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as native:
        native.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    parsed = urlsplit(os.environ["TEST_DATABASE_URL"])
    isolated_url = urlunsplit((parsed.scheme, parsed.netloc, "/" + database_name, parsed.query, parsed.fragment))
    monkeypatch.setenv("DATABASE_URL", isolated_url)
    connect = db._connect_postgres
    barrier = Barrier(2, timeout=10)
    counter_lock = Lock()
    opened = []
    def synchronized_connect(value):
        connection = connect(value)
        with counter_lock:
            opened.append(True)
            position = len(opened)
        if position <= 2:
            # Both real connections exist before either worker starts DDL.
            barrier.wait()
        return connection
    monkeypatch.setattr(db, "_connect_postgres", synchronized_connect)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(create_app, {"TESTING": True}) for _ in range(2)]
        applications = [future.result(timeout=30) for future in futures]
    for application in applications:
        with application.app_context():
            connection = db.get_db()
            assert connection.execute("SELECT COUNT(*) AS n FROM ideas WHERE published = 1").fetchone()["n"] == 14
            assert connection.execute("SELECT COUNT(*) AS n FROM notification_delivery_windows").fetchone()["n"] == 0
        assert application.test_client().get("/healthz").status_code == 200


def test_real_postgres_full_daily_summary_route_is_deduplicated(pg_app, monkeypatch):
    import traceback
    from pathlib import Path
    from tianwai import notifications as n

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "synthetic-pg-summary-token")
    monkeypatch.setenv("LINE_ADMIN_USER_ID", "U" + "b" * 32)
    secret = "synthetic-summary-secret-at-least-32-characters"
    monkeypatch.setenv("NOTIFICATION_CRON_SECRET", secret)
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("external send forbidden"))
    sent = []
    monkeypatch.setattr(n, "send_line_push", lambda message, **_kwargs: (sent.append(message) or "sent", ""))
    client = pg_app.test_client()
    for _ in range(2):
        try:
            response = client.post(
                "/internal/notifications/daily-summary", json={"slot": "noon"},
                headers={"X-Notification-Secret": secret},
            )
        except Exception as error:
            locations = [f"{Path(frame.filename).name}:{frame.lineno}" for frame in traceback.extract_tb(error.__traceback__)
                         if Path(frame.filename).name in {"notifications.py", "notification_routes.py", "db.py"}]
            pytest.fail(f"summary_route_error={type(error).__name__}; locations={' > '.join(locations)}", pytrace=False)
        assert response.status_code == 200
        assert response.get_json()["channels"]["line"] == "sent"
    assert len(sent) == 1


def _commerce_admin_client(application):
    from conftest import set_public_csrf

    client = application.test_client()
    response = client.post("/admin/login", data={
        "username": "integration-admin",
        "password": "integration-password-not-for-production",
        "csrf_token": set_public_csrf(client),
    })
    assert response.status_code == 302
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    return client, re.search(rb'<meta name="admin-csrf" content="([^"]+)"', dashboard.data).group(1).decode()


def test_real_postgres_commerce_columns_defaults_and_restart_preservation(pg_app):
    from tianwai.db import get_db, init_db, utc_now

    with pg_app.app_context():
        connection = get_db()
        columns = {
            row["column_name"]: dict(row)
            for row in connection.execute(
                "SELECT column_name, column_default, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'ideas' "
                "AND column_name IN ('prepared_price', 'sale_state', 'release_ready')"
            ).fetchall()
        }
        assert set(columns) == {"prepared_price", "sale_state", "release_ready"}
        assert columns["prepared_price"]["column_default"] is None
        assert columns["prepared_price"]["is_nullable"] == "YES"
        assert "preparing" in columns["sale_state"]["column_default"]
        assert columns["release_ready"]["column_default"] == "0"
        slug = "synthetic-commerce-default-" + uuid.uuid4().hex
        inserted = connection.execute(
            "INSERT INTO ideas (slug, title, role, seal, discipline, summary, teaser, paid_content, "
            "deliverables, tags, accent, published, created_at, updated_at) "
            "VALUES (?, 'synthetic', 'synthetic', 'synthetic', 'synthetic', 'synthetic', 'synthetic', "
            "'synthetic', 'synthetic', 'synthetic', 'gold', 0, ?, ?)",
            (slug, utc_now(), utc_now()),
        )
        # The adapter reads connection-level LASTVAL(); startup seeds advance
        # that sequence state even for INSERT ... ON CONFLICT DO NOTHING.
        inserted_id = inserted.lastrowid
        connection.commit()
        default = connection.execute(
            "SELECT prepared_price, sale_state, release_ready FROM ideas WHERE id = ?", (inserted_id,)
        ).fetchone()
        assert dict(default) == {"prepared_price": None, "sale_state": "preparing", "release_ready": 0}
        connection.execute(
            "UPDATE ideas SET prepared_price = 7381, sale_state = 'price_listed' WHERE id = ?",
            (inserted_id,),
        )
        connection.commit()
        init_db()
        preserved = connection.execute(
            "SELECT prepared_price, sale_state, release_ready, published FROM ideas WHERE id = ?",
            (inserted_id,),
        ).fetchone()
        assert dict(preserved) == {"prepared_price": 7381, "sale_state": "price_listed", "release_ready": 0, "published": 0}


def test_real_postgres_commerce_admin_batch_atomicity_and_order_gate(pg_app):
    from test_commerce_public_v37 import FIRST_SLUG, LAST_SLUG, _post_order
    from tianwai.db import get_db

    client, csrf = _commerce_admin_client(pg_app)
    headers = {"X-CSRF-Token": csrf}
    with pg_app.app_context():
        connection = get_db()
        rows = connection.execute(
            "SELECT * FROM ideas WHERE published = 1 ORDER BY sort_order"
        ).fetchall()
        first_id = rows[0]["id"]
        assert rows[0]["slug"] == FIRST_SLUG
        before = [dict(row) for row in rows]
        orders_before = connection.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]
    prepared = [{"slug": row["slug"], "prepared_price": 7400 + row["sort_order"]} for row in rows[:13]]
    invalid = [dict(entry) for entry in prepared]
    invalid[-1]["prepared_price"] = 0
    assert client.post("/admin/api/commerce/prepare", json={"entries": invalid}, headers=headers).status_code == 400
    with pg_app.app_context():
        assert [dict(row) for row in get_db().execute("SELECT * FROM ideas WHERE published = 1 ORDER BY sort_order").fetchall()] == before
    assert client.post("/admin/api/commerce/prepare", json={"entries": prepared}, headers=headers).status_code == 200
    detail = client.get(f"/admin/api/ideas/{first_id}/commerce")
    assert detail.status_code == 200
    assert detail.get_json()["commerce"]["prepared_price"] == prepared[0]["prepared_price"]
    public = pg_app.test_client()
    assert all("price" not in item for item in public.get("/api/ideas").get_json()["ideas"])
    assert _post_order(public).status_code in (403, 409, 503)
    listed = {"prepared_price": prepared[0]["prepared_price"], "sale_state": "price_listed", "release_ready": False, "confirm_publication": True}
    assert client.post(f"/admin/api/ideas/{first_id}/commerce", json=listed, headers=headers).status_code == 200
    assert _post_order(public).status_code in (403, 409, 503)
    listed.update(sale_state="for_sale", release_ready=True)
    assert client.post(f"/admin/api/ideas/{first_id}/commerce", json=listed, headers=headers).status_code == 200
    assert _post_order(public).status_code == 201
    assert _post_order(public, LAST_SLUG).status_code in (403, 409, 503)
    # A mixed-state batch must reject atomically, including the twelve preparing rows.
    before_retry = client.get(f"/admin/api/ideas/{first_id}/commerce").get_json()["commerce"]
    with pg_app.app_context():
        before_retry_rows = [dict(row) for row in get_db().execute("SELECT * FROM ideas WHERE published = 1 ORDER BY sort_order").fetchall()]
    assert client.post("/admin/api/commerce/prepare", json={"entries": prepared}, headers=headers).status_code == 409
    assert client.get(f"/admin/api/ideas/{first_id}/commerce").get_json()["commerce"] == before_retry
    with pg_app.app_context():
        connection = get_db()
        after = [dict(row) for row in connection.execute("SELECT * FROM ideas WHERE published = 1 ORDER BY sort_order").fetchall()]
        assert after == before_retry_rows
        assert after[-1] == before[-1]
        for original, updated in zip(before[:13], after[:13]):
            for field in ("paid_content", "deliverables", "price_override", "published", "workflow_status"):
                assert updated[field] == original[field]
        assert connection.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == orders_before + 1


def _prepare_v38_release_rows(connection):
    from tianwai.commerce import PRICING_BATCH_SLUGS

    for index, slug in enumerate(PRICING_BATCH_SLUGS):
        connection.execute(
            "UPDATE ideas SET prepared_price = ?, sale_state = 'preparing', release_ready = 0 WHERE slug = ?",
            (9131 + index, slug),
        )
    connection.commit()
    placeholders = ",".join("?" for _ in PRICING_BATCH_SLUGS)
    rows = connection.execute(
        f"SELECT * FROM ideas WHERE slug IN ({placeholders}) ORDER BY sort_order", PRICING_BATCH_SLUGS,
    ).fetchall()
    assert len(rows) == 13
    return [dict(row) for row in rows]


def test_real_postgres_v38_single_batch_publication_and_restart_preserve_preparation(pg_app):
    from tianwai.commerce import PRICING_BATCH_SLUGS
    from tianwai.db import get_db, init_db
    from tianwai.release_packages import get_release_package, release_package_structure_gaps

    # Validate the actual final editorial files, never replacement mock packages.
    assert all(not release_package_structure_gaps(get_release_package(slug)) for slug in PRICING_BATCH_SLUGS)
    client, csrf = _commerce_admin_client(pg_app)
    headers = {"X-CSRF-Token": csrf}
    with pg_app.app_context():
        connection = get_db()
        prepared = _prepare_v38_release_rows(connection)
        fourteenth = dict(connection.execute("SELECT * FROM ideas WHERE slug = 'sealed-concept-v14'").fetchone())
        order_count = connection.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]
        # A real application restart must retain private preparation and never list prices.
        init_db()
        after_restart = connection.execute(
            "SELECT * FROM ideas WHERE published = 1 AND sort_order BETWEEN 1 AND 13 ORDER BY sort_order"
        ).fetchall()
        assert [dict(row) for row in after_restart] == prepared
        assert all(row["sale_state"] == "preparing" and row["release_ready"] == 0 for row in after_restart)
    inventory = client.get("/admin/api/release-packages")
    assert inventory.status_code == 200
    assert inventory.json["counts"]["ready"] == 13
    assert inventory.json["can_publish_all"] is True
    assert "no-store" in inventory.headers["Cache-Control"]
    first_id = prepared[0]["id"]
    single = client.post(
        f"/admin/api/ideas/{first_id}/publish-package", json={"confirm_publication": True}, headers=headers,
    )
    assert single.status_code == 200
    assert single.json["published_count"] == single.json["changed_count"] == 1
    batch = client.post("/admin/api/release-packages/publish", json={"confirm_publication": True}, headers=headers)
    assert batch.status_code == 200
    assert batch.json["published_count"] == 13 and batch.json["changed_count"] == 12
    assert all(state["sale_state"] == "price_listed" for state in batch.json["states"])
    repeated = client.post("/admin/api/release-packages/publish", json={"confirm_publication": True}, headers=headers)
    assert repeated.status_code == 200 and repeated.json["changed_count"] == 0
    with pg_app.app_context():
        connection = get_db()
        published = connection.execute(
            "SELECT * FROM ideas WHERE published = 1 AND sort_order BETWEEN 1 AND 13 ORDER BY sort_order"
        ).fetchall()
        for before, after in zip(prepared, published):
            assert after["sale_state"] == "price_listed"
            for field in before.keys() - {"sale_state", "updated_at"}:
                assert after[field] == before[field]
        assert dict(connection.execute("SELECT * FROM ideas WHERE slug = 'sealed-concept-v14'").fetchone()) == fourteenth
        assert connection.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == order_count
    assert all(not idea["can_purchase"] for idea in pg_app.test_client().get("/api/ideas").json["ideas"])


@pytest.mark.parametrize("missing", ["scene_image", "prepared_price"])
def test_real_postgres_v38_missing_last_asset_or_price_blocks_whole_batch(pg_app, missing):
    from tianwai.db import get_db

    client, csrf = _commerce_admin_client(pg_app)
    headers = {"X-CSRF-Token": csrf}
    with pg_app.app_context():
        connection = get_db()
        rows = _prepare_v38_release_rows(connection)
        last = rows[-1]
        value = "brand/synthetic-missing-v38.webp" if missing == "scene_image" else None
        connection.execute(f"UPDATE ideas SET {missing} = ? WHERE id = ?", (value, last["id"]))
        connection.commit()
        before = [dict(row) for row in connection.execute("SELECT * FROM ideas ORDER BY id").fetchall()]
    try:
        inventory = client.get("/admin/api/release-packages")
        assert inventory.status_code == 200
        assert inventory.json["counts"]["blocked"] == 1 and inventory.json["can_publish_all"] is False
        batch = client.post("/admin/api/release-packages/publish", json={"confirm_publication": True}, headers=headers)
        assert batch.status_code == 409
        assert batch.json["gaps"][-1]["id"] == last["id"]
        single = client.post(
            f"/admin/api/ideas/{last['id']}/publish-package", json={"confirm_publication": True}, headers=headers,
        )
        assert single.status_code == 409
        with pg_app.app_context():
            assert [dict(row) for row in get_db().execute("SELECT * FROM ideas ORDER BY id").fetchall()] == before
    finally:
        # This cluster is synthetic, but leave its next independent case intact.
        with pg_app.app_context():
            connection = get_db()
            connection.execute(f"UPDATE ideas SET {missing} = ? WHERE id = ?", (last[missing], last["id"]))
            connection.commit()
