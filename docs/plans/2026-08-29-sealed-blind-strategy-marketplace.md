# 天外盲策付費盲盒改版 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 將既有「仙策商品＋公開傳音」改造成「天外盲策」付費概念盲盒，保留天外一筆主品牌、既有正式金流與存取安全，取消公開留言，並上架第一卷「可拆分式雙輪胎」概念。

**Architecture:** 延續既有 Flask 模組化單體與 PostgreSQL/SQLite 雙資料庫介面。以 additive migration 擴充 `ideas`，歷史留言資料只封存、不刪除；公開 API 僅輸出封印線索，付款後的受保護頁面才輸出完整標題、圖文與限制。後台新增規則式六脈分類、草稿工作流與發布完整性檢查，不依賴外部 AI 金鑰。

**Tech Stack:** Python 3 / Flask、PostgreSQL/SQLite、原生 JavaScript、HTML/CSS、pytest、Render、Neon。

## Product decisions

- 主品牌與 Logo 保持「天外一筆工作室」，商品世界稱「天外盲策／仙策閣」。
- 六脈為守護、造物、靈機、破局、人間、傳音；主分類依客戶價值，副分類依實現媒介。
- 商品採非專屬閱讀權；公開頁只顯示封印名稱、主脈、情境線索、成熟度與拆封內容類型。
- 付款後才揭示真實概念標題、完整概念、三幅視覺、限制與未知。
- 不提供工程圖、執行服務、專利／獲利／安全保證。
- 取消公開留言、匿名留言、評分與買家討論；僅保留付款／開通問題的私人支援入口。
- 公開 NT$199 收款維持關閉，待本次改版驗收後另行決定是否開放。

## Task 1: Lock the retired conversation surface

**Files:**
- Modify: `tianwai/__init__.py`
- Modify: `tianwai/admin.py`
- Modify: `tianwai/analytics.py`
- Modify: `templates/base.html`
- Modify: `templates/admin_dashboard.html`
- Modify: `static/app.js`
- Modify: `static/admin.js`
- Rewrite: `tests/test_conversations.py`

1. 先寫測試，要求公開與後台留言路由皆為 404，頁面不載入留言腳本與 Turnstile 留言設定。
2. 保留 `section_messages` 歷史資料表與 migration，但不註冊 blueprint、不查詢、不顯示、不通知。
3. 從導航、首頁、商品頁、後台工作區、需求雷達與通知摘要移除留言訊號。
4. 執行：`python -m pytest tests/test_conversations.py tests/test_database_migration.py -q`。

## Task 2: Add the six-vein blind-box domain model

**Files:**
- Create: `tianwai/ideas.py`
- Modify: `schema.sql`
- Modify: `schema_postgres.sql`
- Modify: `tianwai/db.py`
- Create: `tests/test_blindbox_catalog.py`

1. 先寫分類測試：安全／爆胎內容應以守護脈為主、造物脈為副；軟體自動化應落入靈機脈。
2. 新增 `public_title`、`primary_vein`、`secondary_vein`、`topic`、`maturity`、`workflow_status`、`raw_idea`、三個圖像欄位與分類信心值。
3. migration 只補欄位；以一次性 setting 將六個舊商品取消發布，絕不刪除歷史資料。
4. 建立可解釋的關鍵字分類器、分類理由與信心分數。
5. 執行：`python -m pytest tests/test_blindbox_catalog.py tests/test_database_migration.py -q`。

## Task 3: Seed the first sealed concept scroll

**Files:**
- Modify: `tianwai/db.py`
- Modify: `tests/test_blindbox_catalog.py`

1. 新增公開名稱「封印盲策・第壹卷」，真實標題僅在付費內容顯示。
2. 完整內容包含問題情境、概念機制、價值、使用情境、限制與未知。
3. 主脈守護、副脈造物；標記「概念提案・未經工程驗證」。
4. 明確警語：爆胎後只能輔助駛離危險位置，不可高速續行，不能替代專業維修。
5. 執行種子資料與公開洩漏測試。

## Task 4: Rebuild the public blind-box storefront

**Files:**
- Modify: `tianwai/public.py`
- Rewrite: `templates/home.html`
- Rewrite: `templates/idea_detail.html`
- Modify: `templates/base.html`
- Create: `static/v18.css`
- Modify: `static/app.js`
- Modify: `tianwai/line_bot.py`
- Modify: public route/API tests

1. 先寫測試，公開 HTML/API/LINE 不得出現真實概念標題或付費內容。
2. 首頁改為天外盲策主視覺、六脈篩選、封印卷卡片與購買前說明。
3. 詳情頁只顯示封印線索、取得內容、成熟度、非專屬閱讀權與風險揭露。
4. 付款關閉時只允許興趣登記，不建立正式訂單。
5. 桌面與行動版皆不得依賴滑鼠 hover 才能理解內容。

## Task 5: Upgrade paid reveal and owner workflow

**Files:**
- Modify: `tianwai/access.py`
- Rewrite: `templates/order_access.html`
- Modify: `tianwai/admin.py`
- Modify: `templates/admin_dashboard.html`
- Modify: `static/admin.js`
- Modify: admin/access tests

1. 受保護內容頁顯示真實標題、主副脈、圖文內容、成熟度、限制與買家浮水印。
2. 後台加入「新增原始想法」動作，自動分類並建立草稿。
3. 編輯器可調整封印名稱、六脈、狀態、圖像與完整內容。
4. 發布前檢查完整性；未達標不得上架。
5. 後台需求雷達改以瀏覽、興趣、結帳、付款與內容讀取判斷，不再使用留言量。

## Task 6: Produce and integrate three original visuals

**Files:**
- Create: `static/brand/blindbox-twin-tire-hero-v1.webp`
- Create: `static/brand/blindbox-twin-tire-cutaway-v1.webp`
- Create: `static/brand/blindbox-twin-tire-scene-v1.webp`

1. 產生一張雙窄胎同輪位的概念主圖、一張結構剖視圖、一張爆胎後安全駛離情境圖。
2. 圖中不放文字、品牌、商標或工程認證暗示。
3. 人工檢視輪胎結構、車輛姿態與安全訊息；不合格即針對單一問題重生。
4. 在公開頁使用主圖的模糊／裁切預覽；完整三圖只在付款後清晰顯示。

## Task 7: Verify, document, ship

**Files:**
- Modify: `HANDOFF.md`
- Create: `docs/updates/2026-08-29-sealed-blind-strategy-marketplace.md`

1. 執行 `python -m py_compile` 於所有 Python 檔。
2. 執行完整 `python -m pytest -q`，修到全綠。
3. 掃描 tracked files 的密碼、Token、私鑰、連線字串與客戶識別資料；不得在輸出顯示命中值。
4. 以桌面與行動 viewport 驗證首頁、封印詳情、後台草稿流程、付款後內容頁與 `/healthz`。
5. 確認公開收款仍關閉；不建立或消耗任何正式交易。
6. 更新交接與安全紀錄後 commit、push，等待 Render 部署完成。
7. 確認 `main` 與 `origin/main` 同步、正式 `/healthz` 正常，且公開頁沒有付費內容洩漏。
