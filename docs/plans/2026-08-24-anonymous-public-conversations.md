# 卷二匿名公開傳音實作計畫

> **執行要求：** 依序落實並在每個階段以自動化測試與安全檢查驗證；不得改動正式 Passkey、復原碼或備份機制。

**目標：** 只在卷二六脈仙策的六個策略詳情頁，允許訪客免登入送出公開留言；所有訪客留言一律先審核，私密傳音仍只限已驗證客戶。

**架構：** 延伸既有 `section_messages`，新增不含原始 IP、Email 的訪客識別雜湊與來源雜湊。後端以 HttpOnly 隨機 Cookie 辨識訪客自己的待審留言，並以 Turnstile、CSRF、蜜罐欄位、網址/HTML 禁止及雙層限速防止濫用。前端沿用每個策略獨立留言區，明確標示「訪客」與穩定匿名代號，不在首頁或卷一、卷三新增留言框。

**技術：** Flask、SQLite/PostgreSQL、原生 JavaScript、Cloudflare Turnstile、pytest。

---

## 工作一：先建立匿名權限與濫用防護測試

**檔案：**
- 修改：`tests/test_conversations.py`
- 修改：`tests/test_admin_recovery.py`
- 修改：`tests/test_database_migration.py`

1. 測試訪客只可送公開留言，且必須有有效 CSRF 與 Turnstile。
2. 測試訪客留言固定為待審、僅同一訪客可看自己的待審內容，其他訪客不可見。
3. 測試訪客代號穩定、不洩漏 Cookie/IP 雜湊，並拒絕網址、HTML、超長內容與蜜罐命中。
4. 測試短期與每日限速同時依訪客與來源雜湊生效。
5. 測試管理員核准及公開回覆訪客後，公開頁正確顯示訪客徽章與回覆對象。
6. 測試舊資料庫可安全升級，而既有客戶/管理員訊息不變。

## 工作二：擴充資料庫與訪客身分模型

**檔案：**
- 修改：`schema.sql`
- 修改：`schema.postgres.sql`
- 修改：`tianwai/db.py`
- 修改：`tianwai/conversations.py`
- 修改：`tianwai/admin.py`

1. 新增 `visitor_token_hash`、`source_hash` 欄位及必要索引。
2. 更新約束，允許 `visitor` 作者但禁止訪客私密留言。
3. 為既有 SQLite/PostgreSQL 提供可重複執行的安全遷移。
4. 以伺服器金鑰 HMAC 處理訪客 Token 與來源 IP；不得保存或回傳原值。
5. 讓管理員可核准、拒絕及公開回覆訪客，私密回覆仍需真實客戶。

## 工作三：接入 Turnstile、限速與安全驗證

**檔案：**
- 修改：`tianwai/turnstile.py`
- 修改：`tianwai/security.py`
- 修改：`tianwai/conversations.py`

1. 將 Turnstile 驗證函式泛化為指定 action，保留管理員復原既有行為。
2. 新增訪客公開傳音 action，正式環境未設定 Turnstile 時採失敗關閉。
3. 訪客每則上限 500 字、禁止網址與 HTML，並檢查蜜罐欄位。
4. 訪客限速採來源與訪客雙重約束；既有客戶限速不變。
5. 僅在策略詳情頁 CSP 放行 Cloudflare Turnstile 所需來源。

## 工作四：完成卷二六策前端匿名體驗

**檔案：**
- 修改：`templates/base.html`
- 修改：`templates/idea_detail.html`
- 修改：`templates/_conversation_widget.html`
- 修改：`static/js/conversations.js`
- 修改：`static/css/site.css`

1. 訪客在公開分頁直接看到簡短留言表單，私密分頁仍顯示客戶登入要求。
2. 加入顯式 Turnstile、送出狀態與逾時/失敗復原。
3. 顯示穩定的「訪客・代號」與文字徽章，顏色只作輔助辨識。
4. 自己的待審留言標示「等待公開」，核准前不讓其他訪客看到。
5. 維持首頁僅有六策留言活動提示；零留言時不顯示數字。

## 工作五：驗證、文件與正式發佈

**檔案：**
- 修改：`HANDOFF.md`
- 修改：`docs/updates/2026-08-23-free-postgres-passkey.md`

1. 執行針對性測試、完整 pytest、編譯檢查及機密掃描。
2. 本機瀏覽器驗收六個策略詳情頁、匿名公開/客戶私密分流與行動版。
3. 更新交接與安全升級紀錄，清楚區分已驗收、推論與未完成事項。
4. 檢查 diff 與 Git 狀態後 commit、push。
5. 驗證正式 `/healthz`、部署版本與匿名送出/待審/核准/公開回覆流程；不得以破壞性方式測試正式資料。
