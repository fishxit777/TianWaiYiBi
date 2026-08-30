import os
import re
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, g


def database_backend(database_url=None):
    """Return the configured durable database backend without exposing its URL."""
    configured = os.environ.get("DATABASE_URL", "") if database_url is None else database_url
    return "postgresql" if str(configured).strip() else "sqlite"


def _postgres_sql(statement):
    """Translate the small SQLite-compatible SQL subset used by this application."""
    converted = str(statement).replace("?", "%s")
    if re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", converted, flags=re.IGNORECASE):
        converted = re.sub(
            r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            converted,
            count=1,
            flags=re.IGNORECASE,
        )
        converted = converted.rstrip()
        if converted.endswith(";"):
            converted = converted[:-1].rstrip()
        converted = f"{converted} ON CONFLICT DO NOTHING"
    return converted


class PostgresCursor:
    """Expose the cursor attributes used by the existing SQLite-oriented code."""

    def __init__(self, cursor, connection):
        self._cursor = cursor
        self._connection = connection

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        row = self._connection.execute("SELECT LASTVAL() AS id").fetchone()
        return int(row["id"])


class PostgresConnection:
    """Minimal connection adapter shared by the current query layer."""

    backend = "postgresql"

    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=()):
        cursor = self._connection.execute(_postgres_sql(statement), tuple(parameters or ()))
        return PostgresCursor(cursor, self._connection)

    def executescript(self, script):
        return self._connection.execute(str(script), prepare=False)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    @property
    def in_transaction(self):
        from psycopg.pq import TransactionStatus

        return self._connection.info.transaction_status != TransactionStatus.IDLE

    def close(self):
        self._connection.close()


def _connect_postgres(database_url):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:  # pragma: no cover - exercised only on a misbuilt deploy
        raise RuntimeError("PostgreSQL 已啟用，但 psycopg 尚未安裝") from error

    connection = psycopg.connect(
        str(database_url),
        row_factory=dict_row,
        connect_timeout=10,
        application_name="tianwai-yibi",
    )
    return PostgresConnection(connection)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        database_url = str(current_app.config.get("DATABASE_URL", "")).strip()
        if database_url:
            connection = _connect_postgres(database_url)
        else:
            database = Path(current_app.config["DATABASE"])
            database.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(database, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
        g.db = connection
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


IDEA_SEEDS = [
    {
        "slug": "mvp-sword-cut",
        "title": "一頁破局試煉",
        "role": "破局劍修",
        "seal": "劍",
        "discipline": "最小可行解・問題切割",
        "summary": "把看似龐大的念頭，斬成七天內能驗證的一次行動。",
        "teaser": "適合卡在『想很多、做不完』的創作者與小型團隊。先找最大限制，再決定唯一要測的假設。",
        "paid_content": "七日破局劍譜\n\n第一式｜鎖定一名真正付款者，不以所有人為客戶。\n第二式｜寫下客戶現在用的替代方案，以及它最痛的一個缺口。\n第三式｜只保留一個可量化承諾，例如省下兩小時或多拿到三個詢問。\n第四式｜用一頁說明、表單或人工服務完成第一次交付。\n第五式｜邀請十位目標客戶看見方案，記錄拒絕原因。\n第六式｜只修正最多人卡住的那一步。\n第七式｜以付款、訂金或明確預約作為繼續投入門檻。",
        "deliverables": "7 日驗證表｜單一假設卡｜十人訪談問題",
        "tags": "MVP,驗證,創業",
        "accent": "cinnabar",
        "sort_order": 1,
    },
    {
        "slug": "brand-world-forge",
        "title": "品牌世界觀鍛造",
        "role": "造境符師",
        "seal": "符",
        "discipline": "品牌敘事・視覺世界觀",
        "summary": "把散落的品牌感覺，畫成客戶一眼能進入的完整世界。",
        "teaser": "適合名稱已經有了，卻仍像一般商店或缺乏記憶點的品牌。",
        "paid_content": "七日品牌世界觀鍛造表\n\n一、定義品牌守護的唯一價值：客戶在這裡不必再承受什麼？\n二、選一個主世界，不同頁面都從同一套隱喻延伸。\n三、建立三個視覺母題：形狀、材質、動態。\n四、建立角色規則：每位角色代表一項能力，不重複。\n五、建立語言規則：標題有世界觀，按鈕仍要讓人看得懂。\n六、刪除所有不能增加辨識或轉換的裝飾。\n七、用五秒測試確認陌生人能說出你賣什麼。",
        "deliverables": "7 日鍛造表｜三母題畫布｜品牌語氣檢核表",
        "tags": "品牌,命名,視覺",
        "accent": "jade",
        "sort_order": 2,
    },
    {
        "slug": "conversion-elixir",
        "title": "微轉換煉丹局",
        "role": "增長丹師",
        "seal": "丹",
        "discipline": "轉換設計・低成本實驗",
        "summary": "把流量、內容與優惠煉成一顆能被數字驗證的小丹。",
        "teaser": "適合有人看、有人按讚，卻沒有詢問或付款的內容與商品。",
        "paid_content": "微轉換丹方\n\n先只選一個轉換：留下 Email、登記匿名意願、預約或付款。\n將承諾改寫成『對象＋結果＋時間』。\n刪除 CTA 前所有與決策無關的資訊。\n準備 A/B 兩版，只改一個變數。\n每版至少取得 100 次有效瀏覽再判斷。\n若兩版都低，先換受眾或痛點，不先換按鈕顏色。",
        "deliverables": "轉換診斷表｜A/B 實驗卡｜七日數據記錄表",
        "tags": "成長,轉換,行銷",
        "accent": "gold",
        "sort_order": 3,
    },
    {
        "slug": "automation-puppet",
        "title": "一人門派自動化",
        "role": "機關偃師",
        "seal": "機",
        "discipline": "流程自動化・AI 槓桿",
        "summary": "把重複工作交給機關，讓一個人也能守住整套營運。",
        "teaser": "適合每天複製貼上、追單、整理表格或重複回覆的個人品牌。",
        "paid_content": "機關偃術藍圖\n\n列出一週內重複三次以上的工作。\n以『觸發 → 判斷 → 動作 → 例外』畫出流程。\n先用現成服務串接，不自行重造排程、通知或付款。\n每個自動化保留人工覆核點與錯誤佇列。\n記錄節省時間、失敗率與維護時間；兩週沒有正 ROI 就拆除。",
        "deliverables": "自動化盤點表｜流程圖模板｜例外處理清單",
        "tags": "自動化,AI,流程",
        "accent": "azure",
        "sort_order": 4,
    },
    {
        "slug": "community-echo",
        "title": "回聲社群節奏",
        "role": "回聲樂修",
        "seal": "音",
        "discipline": "內容節奏・社群回訪",
        "summary": "讓內容不是一次發散，而是形成會把人帶回來的回聲。",
        "teaser": "適合發文斷斷續續、主題分散，或粉絲看完就離開的品牌。",
        "paid_content": "回聲七拍\n\n第一拍提出未解問題，第二拍展示真實過程，第三拍公開一次失敗。\n第四拍給可立刻使用的小工具，第五拍回應社群選出的問題。\n第六拍展示前後差異，第七拍邀請加入下一輪共同創作。\n每一拍只服務同一個核心承諾，並留下下一拍的未完句。",
        "deliverables": "七拍內容表｜回訪鉤子清單｜社群提問庫",
        "tags": "內容,社群,回訪",
        "accent": "violet",
        "sort_order": 5,
    },
    {
        "slug": "opportunity-stars",
        "title": "商機觀星盤",
        "role": "觀星策士",
        "seal": "星",
        "discipline": "趨勢判讀・競品缺口",
        "summary": "不追最亮的流星，只找需求、時機與能力真正重疊的星位。",
        "teaser": "適合選項太多、容易追熱門，卻不知道哪一個值得投入的人。",
        "paid_content": "商機觀星盤\n\n以需求強度、付費意願、觸達成本、交付能力、毛利與可重複性各評 1 至 5 分。\n先淘汰沒有付款者、低頻且低痛、需要大量教育的題目。\n再找現有替代方案中被反覆抱怨，且你能在 14 天內提供更好結果的缺口。\n只允許最高分題目進入訪談與預售，其他放入觀察名單。",
        "deliverables": "六維評分表｜競品缺口表｜14 日預售門檻",
        "tags": "商機,策略,競品",
        "accent": "silver",
        "sort_order": 6,
    },
]

BLINDBOX_SEEDS = [
    {
        "slug": "sealed-twin-tire-safety",
        "public_title": "封印盲策・第壹卷",
        "title": "雙生續行輪：可拆分式雙輪胎概念",
        "role": "守護造物",
        "seal": "守",
        "discipline": "道路安全・模組化移動",
        "primary_vein": "守護脈",
        "secondary_vein": "造物脈",
        "topic": "可拆分式雙輪胎",
        "maturity": "概念提案・未經工程驗證",
        "workflow_status": "published",
        "raw_idea": "在一個正常輪位設置兩個可獨立承載的窄型輪胎模組；其中一側爆胎時，另一側暫時支撐車輛駛離危險路段。",
        "summary": "當單一輪胎突然失效，能否多留一段安全離場的時間？",
        "teaser": "這一卷封存一種同輪位、雙承載單元的道路安全構想。它不承諾讓車輛繼續高速行駛，而是試圖降低駕駛人在車流旁立即換胎的暴露風險。",
        "paid_content": "概念原點\n道路爆胎的風險不只來自輪胎本身，也來自駕駛被迫停在快速車流旁處理故障。這份概念把問題重新定義為：如何在一個輪位部分失效後，保留短距離、低速、可控制的離場能力。\n\n概念機制\n將傳統單一寬胎的承載角色，拆成同一輪位內兩個並列、可獨立維持基本形狀與承載的窄型輪胎模組。當其中一個模組失壓，另一個模組提供有限支撐，讓駕駛以低速移至安全處等待道路救援。兩個模組仍共用車輪位置，但輪胎腔體與主要失效路徑彼此隔離。\n\n使用者價值\n一、把「立刻在路邊換胎」轉成「先離開高暴露位置再處理」。\n二、把單點輪胎失效改為部分承載能力下降，爭取反應時間。\n三、讓胎壓監測可分別識別兩個模組，較早提示偏載與異常。\n\n可能情境\n高速道路爆胎後低速駛入避車彎；夜間或雨天先移至照明較好的安全位置；偏遠道路先離開彎道或視線死角再等待救援。\n\n已知限制與未知\n這只是概念提案，尚未完成結構、熱衰退、操控、制動、輪圈、懸吊、法規、製造成本與道路測試。並列雙模組可能帶來不均勻磨耗、轉向偏移、散熱、噪音、重量及維修複雜度。任何原型都必須由輪胎、車輛動力與法規專業人員驗證。\n\n安全邊界\n任一輪胎模組失壓後，只能把剩餘承載視為協助駛離立即危險位置的暫時能力；不可高速續行、不可延後專業檢查，也不能取代道路救援與合格維修。",
        "deliverables": "概念全卷｜結構視覺｜使用情境圖｜限制與未知清單",
        "tags": "汽車,爆胎,道路安全,模組化輪胎,未驗證",
        "accent": "jade",
        "hero_image": "brand/blindbox-twin-tire-hero-v1.webp",
        "diagram_image": "brand/blindbox-twin-tire-cutaway-v1.webp",
        "scene_image": "brand/blindbox-twin-tire-scene-v1.webp",
        "classification_confidence": 94,
        "sort_order": 1,
    }
]


def seed_database(connection):
    now = utc_now()
    connection.execute(
        "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ("idea_price", "199", now),
    )
    for idea in IDEA_SEEDS:
        connection.execute(
            """
            INSERT OR IGNORE INTO ideas
                (slug, title, role, seal, discipline, summary, teaser, paid_content,
                 deliverables, tags, accent, workflow_status, sort_order, published,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'archived', ?, 0, ?, ?)
            """,
            (
                idea["slug"], idea["title"], idea["role"], idea["seal"], idea["discipline"],
                idea["summary"], idea["teaser"], idea["paid_content"], idea["deliverables"],
                idea["tags"], idea["accent"], idea["sort_order"], now, now,
            ),
        )
    for idea in BLINDBOX_SEEDS:
        connection.execute(
            """
            INSERT OR IGNORE INTO ideas
                (slug, title, public_title, role, seal, discipline, primary_vein,
                 secondary_vein, topic, maturity, workflow_status, raw_idea,
                 summary, teaser, paid_content, deliverables, tags, accent,
                 hero_image, diagram_image, scene_image, classification_confidence,
                 sort_order, published, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                idea["slug"], idea["title"], idea["public_title"], idea["role"],
                idea["seal"], idea["discipline"], idea["primary_vein"],
                idea["secondary_vein"], idea["topic"], idea["maturity"],
                idea["workflow_status"], idea["raw_idea"], idea["summary"],
                idea["teaser"], idea["paid_content"], idea["deliverables"],
                idea["tags"], idea["accent"], idea["hero_image"],
                idea["diagram_image"], idea["scene_image"],
                idea["classification_confidence"], idea["sort_order"], now, now,
            ),
        )
    connection.commit()


def _column_names(connection, table):
    if getattr(connection, "backend", "sqlite") == "postgresql":
        return {
            row["name"]
            for row in connection.execute(
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = ?
                """,
                (str(table),),
            ).fetchall()
        }
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate_database(connection):
    """Apply additive SQLite migrations for databases created by earlier releases."""
    idea_columns = _column_names(connection, "ideas")
    idea_migrations = {
        "public_title": "TEXT NOT NULL DEFAULT ''",
        "primary_vein": "TEXT NOT NULL DEFAULT ''",
        "secondary_vein": "TEXT NOT NULL DEFAULT ''",
        "topic": "TEXT NOT NULL DEFAULT ''",
        "maturity": "TEXT NOT NULL DEFAULT '概念提案・未經工程驗證'",
        "workflow_status": "TEXT NOT NULL DEFAULT 'draft'",
        "raw_idea": "TEXT NOT NULL DEFAULT ''",
        "hero_image": "TEXT NOT NULL DEFAULT ''",
        "diagram_image": "TEXT NOT NULL DEFAULT ''",
        "scene_image": "TEXT NOT NULL DEFAULT ''",
        "classification_confidence": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in idea_migrations.items():
        if column not in idea_columns:
            connection.execute(f"ALTER TABLE ideas ADD COLUMN {column} {definition}")

    migration_now = utc_now()
    catalog_migration = connection.execute(
        "SELECT value FROM settings WHERE key = ?", ("blindbox_catalog_v1_migrated",)
    ).fetchone()
    if catalog_migration is None:
        legacy_slugs = tuple(idea["slug"] for idea in IDEA_SEEDS)
        placeholders = ",".join("?" for _ in legacy_slugs)
        connection.execute(
            f"UPDATE ideas SET published = 0, workflow_status = 'archived', updated_at = ? "
            f"WHERE slug IN ({placeholders})",
            (migration_now, *legacy_slugs),
        )
        connection.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("blindbox_catalog_v1_migrated", "1", migration_now),
        )
    if "activation_token_hash" not in _column_names(connection, "orders"):
        connection.execute("ALTER TABLE orders ADD COLUMN activation_token_hash TEXT")
    if "customer_id" not in _column_names(connection, "orders"):
        connection.execute("ALTER TABLE orders ADD COLUMN customer_id INTEGER REFERENCES customers(id)")
    order_columns = _column_names(connection, "orders")
    if "purpose" not in order_columns:
        connection.execute("ALTER TABLE orders ADD COLUMN purpose TEXT NOT NULL DEFAULT 'sale'")
    if "payment_method" not in order_columns:
        connection.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT")
    if "refunded_at" not in order_columns:
        connection.execute("ALTER TABLE orders ADD COLUMN refunded_at TEXT")
    if "analytics_session_id" not in order_columns:
        connection.execute("ALTER TABLE orders ADD COLUMN analytics_session_id TEXT")

    analytics_columns = _column_names(connection, "analytics_events")
    if "event_value" not in analytics_columns:
        connection.execute("ALTER TABLE analytics_events ADD COLUMN event_value TEXT NOT NULL DEFAULT ''")
    if "event_version" not in analytics_columns:
        connection.execute("ALTER TABLE analytics_events ADD COLUMN event_version INTEGER NOT NULL DEFAULT 1")
    if "dedupe_key" not in analytics_columns:
        connection.execute("ALTER TABLE analytics_events ADD COLUMN dedupe_key TEXT")
    if "is_automated" not in analytics_columns:
        connection.execute("ALTER TABLE analytics_events ADD COLUMN is_automated INTEGER NOT NULL DEFAULT 0")
    if "page_path" not in analytics_columns:
        connection.execute("ALTER TABLE analytics_events ADD COLUMN page_path TEXT NOT NULL DEFAULT ''")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_analytics_idea_funnel "
        "ON analytics_events (idea_id, event_name, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_analytics_session_time "
        "ON analytics_events (session_id, created_at DESC)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_dedupe "
        "ON analytics_events (dedupe_key) WHERE dedupe_key IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_analytics_session "
        "ON orders (analytics_session_id, created_at DESC)"
    )

    session_columns = _column_names(connection, "customer_sessions")
    if "customer_id" not in session_columns:
        connection.execute("ALTER TABLE customer_sessions ADD COLUMN customer_id INTEGER REFERENCES customers(id)")
    if "device_id" not in session_columns:
        connection.execute("ALTER TABLE customer_sessions ADD COLUMN device_id INTEGER REFERENCES customer_devices(id)")
    if "ip" not in session_columns:
        connection.execute("ALTER TABLE customer_sessions ADD COLUMN ip TEXT")
    if "idle_expires_at" not in session_columns:
        connection.execute("ALTER TABLE customer_sessions ADD COLUMN idle_expires_at TEXT")
    if "replay_attempts" not in session_columns:
        connection.execute("ALTER TABLE customer_sessions ADD COLUMN replay_attempts INTEGER NOT NULL DEFAULT 0")
    if "last_replay_at" not in session_columns:
        connection.execute("ALTER TABLE customer_sessions ADD COLUMN last_replay_at TEXT")

    admin_session_columns = _column_names(connection, "admin_sessions")
    if "auth_method" not in admin_session_columns:
        connection.execute("ALTER TABLE admin_sessions ADD COLUMN auth_method TEXT NOT NULL DEFAULT 'password'")
    if "restricted" not in admin_session_columns:
        connection.execute("ALTER TABLE admin_sessions ADD COLUMN restricted INTEGER NOT NULL DEFAULT 0")

    migration_now = utc_now()
    code_cap = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="seconds")
    connection.execute(
        """
        UPDATE activation_codes SET expires_at = ?
        WHERE used_at IS NULL AND revoked_at IS NULL AND expires_at > ?
        """,
        (code_cap, code_cap),
    )
    connection.execute(
        """
        UPDATE customer_login_codes SET expires_at = ?
        WHERE used_at IS NULL AND revoked_at IS NULL AND expires_at > ?
        """,
        (code_cap, code_cap),
    )
    connection.execute(
        """
        UPDATE customer_sessions
        SET revoked_at = ?, revoked_reason = 'security_upgrade_relogin_required'
        WHERE revoked_at IS NULL AND (customer_id IS NULL OR device_id IS NULL OR idle_expires_at IS NULL)
        """,
        (migration_now,),
    )

    from .security import derive_activation_token, hash_token

    rows = connection.execute(
        "SELECT id, order_no FROM orders WHERE activation_token_hash IS NULL"
    ).fetchall()
    for row in rows:
        token = derive_activation_token(row["order_no"])
        connection.execute(
            "UPDATE orders SET activation_token_hash = ? WHERE id = ?",
            (hash_token(token), row["id"]),
        )

    emails = connection.execute(
        "SELECT DISTINCT LOWER(TRIM(customer_email)) AS email FROM orders WHERE customer_email <> ''"
    ).fetchall()
    for row in emails:
        email = row["email"]
        existing = connection.execute(
            "SELECT id FROM customers WHERE normalized_email = ?", (email,)
        ).fetchone()
        if existing is None:
            public_id = f"TYB-{secrets.token_hex(6).upper()}"
            cursor = connection.execute(
                """
                INSERT INTO customers
                    (public_id, normalized_email, status, risk_level, created_at, updated_at)
                VALUES (?, ?, 'active', 'low', ?, ?)
                """,
                (public_id, email, utc_now(), utc_now()),
            )
            customer_id = cursor.lastrowid
        else:
            customer_id = existing["id"]
        connection.execute(
            "UPDATE orders SET customer_id = ? WHERE LOWER(TRIM(customer_email)) = ? AND customer_id IS NULL",
            (customer_id, email),
        )
        connection.execute(
            "UPDATE customer_sessions SET customer_id = ? WHERE LOWER(TRIM(customer_email)) = ? AND customer_id IS NULL",
            (customer_id, email),
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_activation_token ON orders (activation_token_hash)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders (customer_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_purpose_status ON orders (purpose, status, id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_refund_events_order ON refund_events (order_id, created_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_session_customer_expiry ON customer_sessions (customer_id, expires_at DESC)"
    )
    connection.commit()


def init_db():
    connection = get_db()
    schema_name = "schema_postgres.sql" if getattr(connection, "backend", "sqlite") == "postgresql" else "schema.sql"
    schema_path = Path(__file__).with_name(schema_name)
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    migrate_database(connection)
    seed_database(connection)


def get_setting_int(key, default=0):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return int(default)
    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return int(default)


def init_app(app):
    app.teardown_appcontext(close_db)
