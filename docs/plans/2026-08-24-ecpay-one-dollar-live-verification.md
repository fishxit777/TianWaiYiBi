# 綠界 1 元正式付款閉環驗證實作計畫

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 不改公開仙策售價，以一筆隔離的 NT$6 信用卡訂單完成正式付款、伺服器回呼、Email 交付、內容開通、退款、撤權與對帳驗收。

**2026-08-25 correction:** 原定 NT$1 與其後依公開說明嘗試的 NT$5，都已由綠界正式付款頁實證拒絕。登入本特店的「合約及費率」核對後，信用卡一次付清的實際單筆限制為 NT$6–200,000；國內卡最低手續費 NT$5，另有每筆固定處理費 NT$1。隔離驗證因此固定改為 NT$6，公開仙策仍為 NT$199。綠界公開說明亦要求以廠商後台合約限制為準：https://support.ecpay.com.tw/31408/

**2026-08-25 checkout correction:** 綠界正式頁另實證 `MerchantTradeNo` 不可重複。內部訂單編號與綠界結帳嘗試序號已分離；每次轉送使用新的 20 碼交易序號，簽章保護的 `CustomField1` 映射回原訂單，後台並改為同分頁單次開啟，避免雙擊與重送造成 `10300028`。

**Architecture:** 在既有 Flask 單體與 `orders` 權益來源上新增 `verification` 訂單用途。驗證訂單只能由已登入管理後台建立，只有獨立環境開關啟用時才能送往綠界，且固定使用信用卡一次付清；一般公開結帳仍受既有正式啟用閘門阻擋。退款採綠界官方後台執行，確認外部退款成功後，再由管理後台以單一資料庫交易把本地訂單改為 `refunded`、撤銷未用開通碼與無其他權益的工作階段，並保存不含卡號或憑證的退款稽核紀錄。

**Tech Stack:** Python 3、Flask、SQLite／PostgreSQL、原生 JavaScript、pytest、綠界 AioCheckOut V5。

---

## 已選方案與理由

1. **採用：後台專用隔離驗證訂單。** 不改 `idea_price` 或任何 `price_override`，因此不會讓訪客看到或買到 NT$6 商品；測完也不需要猜原價再回寫。
2. **不採用：暫時把公開商品改為 NT$6。** 部署與 CDN 時差會產生被外人低價下單的窗口，還可能污染營收與客戶權益。
3. **暫不採用：自行呼叫自動退款 API。** 綠界官方要求依已授權、要關帳、已關帳等狀態選擇放棄、取消或退刷；一次性正式驗收以官方後台處理可降低錯誤退款、重複退款與維護成本。網站仍完整處理退款後撤權與稽核。

## 安全與營運邊界

- 驗證訂單金額固定由伺服器寫死為 `1`，前端不可傳入價格。
- 訂單編號保留 `TWYB` 專案前綴並增加驗證辨識碼，仍符合綠界 20 字元限制。
- 僅 `ECPAY_MODE=production`、正式憑證、HTTPS callback、SMTP 與獨立驗證開關同時就緒時，管理後台才能建立驗證訂單。
- 驗證訂單固定 `ChoosePayment=Credit`，金額採本特店合約的信用卡實際最低 NT$6，避免其他付款方式的更高門檻。
- 一般公開結帳仍須 `ECPAY_LIVE_CONFIRMED=true`；啟用驗證模式不會開放正式商品收款。
- 資料庫與 API 不保存或回傳卡號、驗證碼、HashKey、HashIV、CheckMacValue 或綠界登入資料。
- 付款成功只能由通過 MerchantID、StoreID、CheckMacValue、訂單與金額核對的伺服器通知建立權益。
- 本地退款確認只接受 `purpose=verification`、`amount=6`、`status=paid`、正式綠界付款的訂單，且需管理 session、CSRF 與完整訂單編號二次確認。
- 正式退款在綠界後台完成前不得把本地訂單標成 `refunded`；本地撤權完成後還需重新測試原內容網址已拒絕。

### Task 1: 資料模型與遷移

**Files:**
- Modify: `tianwai/schema.sql`
- Modify: `tianwai/schema_postgres.sql`
- Modify: `tianwai/db.py`
- Test: `tests/test_database_migration.py`

1. 先寫既有資料庫升級測試，驗證舊訂單預設為 `sale`，並存在退款稽核表。
2. 在 `orders` 新增 `purpose`、`payment_method`、`refunded_at`。
3. 新增 `refund_events`，只保存事件 ID、訂單、provider、金額、處理方式、結果與時間，不保存原始外部回應。
4. 驗證 SQLite 與 PostgreSQL fresh schema／migration。

### Task 2: 建立隔離的 NT$6 訂單

**Files:**
- Modify: `tianwai/payments.py`
- Modify: `tianwai/admin.py`
- Modify: `templates/admin_dashboard.html`
- Modify: `static/admin.js`
- Test: `tests/test_integrations.py`
- Test: `tests/test_admin_security.py`

1. 先寫測試，證明未登入、缺 CSRF、缺驗證開關、非 production 或缺交付 Email 時均不得建單。
2. 新增管理端建單 API；金額固定 NT$6，Email 只從 Render 私密環境設定取得。
3. 讓驗證訂單可在 `ECPAY_LIVE_CONFIRMED` 尚未開啟時送綠界，但公開商品仍維持關閉。
4. 驗證送往綠界的 `TotalAmount=6`、`ChoosePayment=Credit`、`StoreID=TWYB`，且頁面與 API 不洩露正式憑證。
5. 後台顯示最新驗證訂單狀態與必要動作，不把驗證金額計入正式營收。

### Task 3: 回呼、開通與撤權

**Files:**
- Modify: `tianwai/payments.py`
- Modify: `tianwai/access.py`
- Modify: `tianwai/admin.py`
- Test: `tests/test_integrations.py`
- Test: `tests/test_customer_access.py`

1. 先寫 NT$6 合法回呼、錯誤金額、錯誤 StoreID、重送與模擬付款不得開通測試。
2. 保存非敏感付款方式，維持 payment reference 與本機訂單關聯。
3. 以既有一次性開通碼實際開通驗證訂單，確認內容可讀。
4. 新增退款後本地確認 API：只處理符合驗證條件的已付款訂單，改為 `refunded`、撤銷開通碼與無其他已付款權益的 session，寫入退款與管理稽核。
5. 重送本地退款確認必須冪等；退款後原內容網址必須拒絕。

### Task 4: 完整驗證與正式操作

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/updates/2026-08-23-free-postgres-passkey.md`

1. 執行目標測試、完整 pytest、Python compile、JavaScript syntax、依賴與機密掃描。
2. 部署前只核對 Render 設定是否存在，不顯示任何值；缺少機密時才交還本人安全輸入。
3. 部署後確認公開 NT$199 未改、一般結帳仍關閉、後台顯示 NT$6 驗證入口。
4. 在送出正式信用卡付款前取得當下確認；完成 NT$6 實刷、伺服器回呼、Email、一次性開通與內容讀取。
5. 在綠界官方後台查到相同 `TWYB` 驗證訂單與 NT$6 金額；退款送出前再次取得當下確認。
6. 外部退款成功後執行本地撤權，確認訂單 `refunded`、內容拒絕、正式營收不含驗證訂單、退款稽核存在。
7. 關閉獨立驗證開關；不變更公開價格。更新文件、測試、檢查機密、commit 並 push。

## 完成標準

- 只有正式綠界後端通知能把驗證訂單由 `pending` 改為 `paid`。
- NT$6 實際出現在綠界與本地相同的驗證訂單上，Email、開通碼與內容讀取實測成功。
- 綠界退款／放棄授權成功，且本地訂單改為 `refunded` 後舊內容入口無法再讀取。
- 正式商品售價、正式營收、一般客戶權益、兩把 Passkey、復原碼與備份均未被修改。
- 驗證開關已關閉、工作樹乾淨、測試通過、文件與遠端 `main` 同步。
