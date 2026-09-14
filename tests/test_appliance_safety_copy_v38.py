"""Exact historical-copy correction; synthetic SQLite and isolated loopback PG."""

import hashlib
import os

import pytest

from test_postgres_integration import pg_app
from tianwai.db import get_db, init_db
from tianwai.v30_catalog import V30_BLINDBOX_SEEDS, V38_APPLIANCE_COPY_UPDATES


SLUG = "sealed-concept-v11"
FIELD, PREVIOUS, CURRENT = V38_APPLIANCE_COPY_UPDATES[0]


def test_appliance_seed_changes_only_micro_mvp_and_freezes_exact_legacy_copy(app):
    # Digest was independently compared with the complete pre-V38 Git seed.
    assert hashlib.sha256(PREVIOUS.encode()).hexdigest() == "7c5472e69d1d32f64f1f2ce43ac1e89302fb4611000bb9e22d2e994c1ae823a9"
    assert FIELD == "paid_content" and len(V38_APPLIANCE_COPY_UPDATES) == 1
    old_parts, new_parts = PREVIOUS.split("\n\n"), CURRENT.split("\n\n")
    assert len(old_parts) == len(new_parts)
    changed = [index for index, pair in enumerate(zip(old_parts, new_parts)) if pair[0] != pair[1]]
    assert len(changed) == 1 and new_parts[changed[0]].startswith("Micro-MVP\n")
    assert "安全加裝不平衡配重" not in CURRENT
    assert "原廠封閉、未經改裝的低電壓正常裝置" in CURRENT
    assert "合成聲音" in CURRENT and "合法取得" in CURRENT and "既有異常錄音" in CURRENT
    assert "不得破壞、拆解或改裝馬達" in CURRENT
    assert "不加裝配重" in CURRENT
    assert "不把重播異常聲與正常功率配成故障耗能證據" in CURRENT
    assert next(seed["paid_content"] for seed in V30_BLINDBOX_SEEDS if seed["slug"] == SLUG) == CURRENT
    with app.app_context():
        assert get_db().execute("SELECT paid_content FROM ideas WHERE slug = ?", (SLUG,)).fetchone()["paid_content"] == CURRENT


def _verify_exact_copy_update(application, original):
    with application.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE ideas SET paid_content = ?, prepared_price = 9347, sale_state = 'price_listed', "
            "release_ready = 0, updated_at = '2001-01-01T00:00:00+00:00' WHERE slug = ?",
            (original, SLUG),
        )
        connection.commit()
        before = dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (SLUG,)).fetchone())
        other_ideas = [dict(row) for row in connection.execute("SELECT * FROM ideas WHERE slug <> ? ORDER BY id", (SLUG,)).fetchall()]
        settings = [dict(row) for row in connection.execute("SELECT * FROM settings ORDER BY key").fetchall()]
        init_db()
        after = dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (SLUG,)).fetchone())
        assert after["paid_content"] == (CURRENT if original == PREVIOUS else original)
        if original == PREVIOUS:
            assert all(before[key] == after[key] for key in before.keys() - {"paid_content", "updated_at"})
        else:
            assert before == after
        assert [dict(row) for row in connection.execute("SELECT * FROM ideas WHERE slug <> ? ORDER BY id", (SLUG,)).fetchall()] == other_ideas
        assert [dict(row) for row in connection.execute("SELECT * FROM settings ORDER BY key").fetchall()] == settings
        init_db()
        assert dict(connection.execute("SELECT * FROM ideas WHERE slug = ?", (SLUG,)).fetchone()) == after


@pytest.mark.parametrize("original", [PREVIOUS, PREVIOUS + "\n\n自訂補充：保留編輯內容。", PREVIOUS + " ", "已由管理者獨立編寫的合規研究內容。"], ids=["exact-original", "custom-append", "custom-whitespace", "custom-rewrite"])
def test_sqlite_safety_upgrade_preserves_every_custom_manuscript_and_commercial_field(app, original):
    _verify_exact_copy_update(app, original)


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").strip(), reason="Requires the isolated loopback PostgreSQL test runner")
def test_real_postgres_appliance_safety_copy_upgrade_and_custom_preservation(pg_app):
    _verify_exact_copy_update(pg_app, PREVIOUS)
    _verify_exact_copy_update(pg_app, PREVIOUS + "\n\nPostgreSQL 合成自訂備註，禁止覆寫。")
