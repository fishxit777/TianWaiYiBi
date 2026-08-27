# Admin Summary Signal Quality Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 讓管理摘要只呈現可行動的近期異常，並正確區分 LINE 私訊未設定、公開金流關閉及有效真人流量。

**Architecture:** 保留 `notification_queue` 作為不可刪除的送達稽核來源，在查詢與重試層增加時間窗與用途分類。付款狀態由既有 readiness 加上營運狀態，流量摘要沿用需求雷達的真人、去重與機器排除原則。

**Tech Stack:** Flask、SQLite／PostgreSQL 共用 SQL、原生 JavaScript、pytest。

---

### Task 1: 鎖定摘要規則

**Files:**
- Modify: `tests/test_admin_notifications.py`
- Modify: `tests/test_integrations.py`

**Step 1:** 新增歷史失敗不列今日待辦、近期失敗列待辦的測試。

**Step 2:** 新增有效真人工作階段去重、機器與後台預覽排除、熱門仙策樣本門檻測試。

**Step 3:** 新增正式金流設定完整但公開閘門關閉時為 `closed` 的測試。

**Step 4:** 執行專項測試並確認新測試先失敗。

### Task 2: 實作後端狀態與安全重試

**Files:**
- Modify: `tianwai/notifications.py`
- Modify: `tianwai/payments.py`
- Modify: `tianwai/admin.py`

**Step 1:** 將通知指標拆成今日失敗、今日略過與歷史稽核存量。

**Step 2:** 將 LINE 官方頻道與管理員私訊 readiness 分開。

**Step 3:** 為付款狀態增加 `state`、`configuration_ready` 與安全關閉標籤。

**Step 4:** 將流量改為有效真人不重複工作階段並增加樣本門檻。

**Step 5:** 將批次重試限制為 24 小時內每日摘要及 7 天內其他通知。

**Step 6:** 執行專項測試並確認通過。

### Task 3: 修正後台呈現

**Files:**
- Modify: `static/admin.js`
- Modify: `templates/admin_dashboard.html`

**Step 1:** 讓付款卡片把 `closed` 顯示為設定完整、公開收款關閉。

**Step 2:** 讓管理員通知卡片明確指出 LINE 私訊收件人缺失。

**Step 3:** 將按鈕改為「重試近期未送達」，結果提示加入過期排除數。

**Step 4:** 執行 JavaScript 語法檢查。

### Task 4: 完整驗證與發布

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/updates/2026-08-23-admin-dual-channel-notifications.md`

**Step 1:** 執行完整 pytest、Python compileall、JavaScript syntax、`pip check` 與 `git diff --check`。

**Step 2:** 執行新增行機密掃描，確認沒有任何憑證或私密識別碼。

**Step 3:** 更新交接與通知升級紀錄。

**Step 4:** Commit、push，確認 `main` 與 `origin/main` 同步。

**Step 5:** 核對正式 `/healthz`、首頁公開收款仍關閉；不建立通知、訂單或付款。
