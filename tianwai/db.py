import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
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
        "paid_content": "微轉換丹方\n\n先只選一個轉換：留下 Email、加入 LINE、預約或付款。\n將承諾改寫成『對象＋結果＋時間』。\n刪除 CTA 前所有與決策無關的資訊。\n準備 A/B 兩版，只改一個變數。\n每版至少取得 100 次有效瀏覽再判斷。\n若兩版都低，先換受眾或痛點，不先換按鈕顏色。",
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
                 deliverables, tags, accent, sort_order, published, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                idea["slug"], idea["title"], idea["role"], idea["seal"], idea["discipline"],
                idea["summary"], idea["teaser"], idea["paid_content"], idea["deliverables"],
                idea["tags"], idea["accent"], idea["sort_order"], now, now,
            ),
        )
    connection.commit()


def init_db():
    connection = get_db()
    schema_path = Path(__file__).with_name("schema.sql")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
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

