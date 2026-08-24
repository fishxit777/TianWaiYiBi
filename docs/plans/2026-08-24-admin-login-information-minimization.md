# Admin Login Information Minimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 讓未登入訪客無法從管理登入畫面直接得知驗證技術、裝置種類、憑證數量、密碼模式或復原入口，同時維持既有強驗證與復原能力。

**Architecture:** 公開頁改用中性「身分驗證」介面與獨立最小化 JavaScript；驗證流程仍由伺服器產生一次性 WebAuthn challenge 並要求 user verification。既有憑證在登記時已強制為 discoverable credential，因此公開驗證不再下發 `allowCredentials` 清單，避免暴露憑證 ID 與數量；公開 API 同時改用中性路由與錯誤訊息，新增每 IP 的 challenge 起始速率限制。完整憑證管理資訊只在已驗證後台顯示。

**Tech Stack:** Flask、Jinja2、原生 JavaScript、WebAuthn、SQLite／PostgreSQL、pytest。

---

### Task 1: 鎖定公開資訊邊界

**Files:**
- Modify: `tests/test_admin_passkeys.py`
- Modify: `tests/test_admin_security.py`

**Step 1:** 新增失敗測試，要求 Passkey-only 未登入頁包含中性「驗證身分」，且不得包含 Passkey、Windows Hello、手機、硬體金鑰、兩把、密碼停用、緊急復原連結或設定用 JavaScript。

**Step 2:** 新增公開驗證錯誤不得洩漏內部驗證種類的測試。

**Step 3:** 執行 `python -m pytest tests/test_admin_passkeys.py tests/test_admin_security.py -q`，確認舊介面使新測試失敗。

### Task 2: 最小化公開登入介面

**Files:**
- Modify: `templates/admin_login.html`
- Create: `static/admin-identity.js`
- Modify: `static/admin-passkey.js`
- Modify: `tianwai/admin.py`

**Step 1:** 將公開標題、按鈕、狀態與說明改為中性用語，移除復原連結與憑證拓撲資訊。

**Step 2:** 把公開登入程式從已登入設定程式拆開；公開頁只載入最小化身分驗證程式。

**Step 3:** 將公開驗證端點改為 `/admin/identity/options` 與 `/admin/identity/verify`，所有未登入錯誤使用中性訊息；舊公開路由不保留別名。

**Step 4:** 不再在公開 authentication options 送出 `allowCredentials` 清單，由裝置依 RP 自行選擇 discoverable credential，伺服器仍以收到的 credential ID 精確核對正式公開金鑰。

**Step 5:** 保留伺服器端 RP／origin／challenge／user verification、Session、CSRF、IP 檢查與登入失敗封鎖，不修改正式憑證或復原資料。

### Task 3: 限制 challenge 起始濫用

**Files:**
- Modify: `tianwai/passkeys.py`
- Modify: `tianwai/schema.sql`
- Modify: `tianwai/schema_postgres.sql`
- Modify: `tests/test_admin_passkeys.py`

**Step 1:** 新增每 IP 每分鐘最多 10 次 authentication challenge 的測試，超限預期 HTTP 429。

**Step 2:** 實作時間窗計數與過期 challenge 清理，並為 purpose／IP／建立時間加入索引。

**Step 3:** 執行 Passkey 與安全專項測試，確認限速與正常登入均通過。

### Task 4: 驗證、文件與部署

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/updates/2026-08-23-free-postgres-passkey.md`

**Step 1:** 記錄公開登入資訊最小化、challenge 限速及安全邊界；不得記錄任何憑證或復原碼。

**Step 2:** 執行完整 pytest、Python compile、JavaScript syntax、依賴、diff 與機密掃描。

**Step 3:** 本機以未登入視角檢查 HTML 與畫面，確認技術字樣及復原連結消失。

**Step 4:** Commit、push，等待 Render 自動部署後核對正式 `/admin/login` 與 `/healthz`。
