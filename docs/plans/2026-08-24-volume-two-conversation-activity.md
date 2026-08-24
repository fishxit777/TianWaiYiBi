# 卷二限定傳音與活動提示 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 將站內留言嚴格收斂到卷二六脈仙策的六個獨立對話，並以不洩漏私密內容的狀態提示呈現已有傳音、新傳音與客戶新回覆。

**Architecture:** 公開首頁不再掛載通用卷別留言元件，只在六張仙策卡片與卷二導覽顯示活動狀態；完整公開／私密對話仍位於各仙策詳情頁。後端新增只回傳統計與最新訊息流水號的活動 API，瀏覽器只在 localStorage 保存各仙策的已讀流水號，不保存留言內容、客戶身分或任何機密。

**Tech Stack:** Flask、Jinja2、SQLite／PostgreSQL 共用 SQL、原生 JavaScript、CSS、pytest。

---

### Task 1: 鎖定卷二留言範圍

**Files:**
- Modify: `tianwai/conversations.py`
- Modify: `tianwai/admin.py`
- Test: `tests/test_conversations.py`

**Step 1:** 將既有對話測試改為使用 `idea-detail` 與實際仙策 slug，新增其他首頁卷別 API 回 404 的失敗測試。

**Step 2:** 執行 `python -m pytest tests/test_conversations.py -q`，確認新範圍測試在舊程式上失敗。

**Step 3:** 讓公開投稿、讀取與後台新回覆只接受已上架仙策的 `idea-detail`；後台統計、清單與選單只顯示卷二六脈。舊資料列保留，不做物理刪除。

**Step 4:** 重跑傳音專項，確認權限、審核、私密隔離與 CSRF 行為不退步。

### Task 2: 建立不含內容的活動摘要

**Files:**
- Modify: `tianwai/conversations.py`
- Test: `tests/test_conversations.py`

**Step 1:** 新增測試，要求活動 API 只計入已公開傳音，匿名訪客看不到私密活動，已登入客戶只能取得自己的守閣者私密回覆狀態。

**Step 2:** 實作 `GET /api/conversations/idea-activity`，每脈只回傳 slug、公開數量、最新公開訊息 ID，以及當前客戶自己的私密回覆數量與最新 ID；回應強制 `no-store`。

**Step 3:** 在單一留言清單回應加入該範圍的 `latest_activity_id`，供詳情頁正確寫入已讀位置。

### Task 3: 改造首頁與詳情頁提示

**Files:**
- Modify: `templates/home.html`
- Modify: `templates/base.html`
- Modify: `templates/idea_detail.html`
- Modify: `static/app.js`
- Modify: `static/conversations.js`
- Modify: `static/v16.css`
- Test: `tests/test_conversations.py`

**Step 1:** 新增頁面結構測試，要求首頁沒有完整留言元件、六張卡片各有活動提示位置、導覽有卷二彙總提示，而詳情頁保留唯一完整留言元件。

**Step 2:** 移除卷首、卷一、卷二總區、卷三、卷四、卷五的完整留言元件，只保留六個仙策詳情頁的獨立元件。

**Step 3:** 首頁載入活動摘要，以「已有傳音／新傳音／有新回覆」三種文字狀態呈現；不顯示 0，不以顏色作為唯一資訊。卷二導覽只顯示彙總狀態，不暴露私密數量或內容。

**Step 4:** 詳情頁成功載入公開或私密傳音後，只將對應最新流水號寫入 localStorage；首頁在返回或重新載入時依流水號更新狀態。

**Step 5:** 補齊桌機、手機、鍵盤焦點、讀取失敗與減少動態效果樣式；API 失敗時隱藏提示，不阻塞六脈瀏覽。

### Task 4: 驗證、文件與發布

**Files:**
- Modify: `tianwai/__init__.py`
- Modify: `tests/test_app.py`
- Modify: `HANDOFF.md`
- Modify: `docs/updates/2026-08-23-free-postgres-passkey.md`

**Step 1:** 更新 release 名稱及健康檢查測試。

**Step 2:** 執行傳音專項、完整 pytest、Python compileall、兩支 JavaScript `node --check`、`git diff --check`、相依與機密檢查。

**Step 3:** 在桌機與 390px 手機視窗檢查卷二提示、六張卡片、詳情頁錨點及無水平溢位；不建立正式留言、不使用真實客戶資料。

**Step 4:** 更新交接與安全升級紀錄，說明本次只改留言範圍與活動提示，沒有碰觸 Passkey、復原碼、備份或資料庫機密。

**Step 5:** 檢查 staged diff 後 commit、push，等待 Render 正式健康版本更新，再做公開匿名煙霧測試。
