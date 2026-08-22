# 仙策閣初版安全複查

日期：2026-08-22

## 結論

初版已具備適合本機 MVP 的防護基線，但不宣稱「絕對防盜或防駭」。正式公開前仍需 HTTPS、WAF、PostgreSQL 權限隔離、備份、監控、正式支付商驗簽與外部安全測試。

## 已實作

- 管理密碼只來自環境變數，沒有預設密碼，也不寫入資料庫、URL 或日誌。
- 管理 session 使用高熵隨機 token；資料庫只存 SHA-256 雜湊，Cookie 為 HttpOnly、SameSite=Strict、限 `/admin`。
- 管理 session 預設綁定來源 IP，支援強制 IP allowlist。
- 管理 mutation 需要 CSRF，價格、仙策內容、上架、解封與安全測試都有稽核紀錄。
- 仙策內容編輯有伺服器端必填、長度、整數範圍與色系 enum 白名單；slug 不開放後台修改，前台也不接受任意 HTML。
- 15 分鐘內 5 次登入失敗會暫時封鎖 IP，訊息不揭露帳號是否存在。
- LINE webhook 使用 `X-Line-Signature` HMAC-SHA256 驗證，以 `webhookEventId` 防重送。
- 支付 webhook 使用 HMAC-SHA256，核對 event ID、訂單、金額、付款狀態與 payment reference，交易採冪等處理。
- 付費內容網址 token 由付款 capability 以 HMAC 派生；資料庫只存雜湊，不存可直接開啟內容的明文 token。
- SQL 全部使用參數，不以字串拼接使用者輸入。
- 客戶輸入限制長度與格式；分析事件採事件名及來源白名單。
- CSP 只允許 self，不允許 inline script、第三方 script 或 object；另有 nosniff、frame protection、COOP、CORP、Origin-Agent-Cluster、Referrer-Policy、Permissions-Policy、後台 no-store 與 HTTPS HSTS。
- 攔截 `.env`、`.git`、phpMyAdmin、WordPress、路徑穿越、script 與 union-select 探測，並記錄安全事件。
- 日誌不保存 Cookie、管理 token、支付 secret、LINE token 或訊息全文。
- 非測試環境的 `APP_SECRET_KEY` 至少 32 字元；正式環境可自動啟用 Secure public session Cookie。

## 已驗證

- 未登入後台 API 回 401。
- 管理價格變更缺少 CSRF 回 403。
- `.env` 探測回 404 並寫入 `sensitive_path_probe`。
- 支付簽章錯誤回 401；金額錯誤回 400；相同事件只處理一次。
- LINE 簽章錯誤回 401；相同 LINE event 只處理一次。
- LINE payload 外形不符回 400；六脈目錄輸出一個 text 與一個含六張 bubble 的 Flex Carousel。
- 仙策內容 API 缺少 CSRF 回 403；不允許的 accent 回 400；成功更新會保存內容並寫入 audit log。
- 連續錯誤登入會出現 429。
- 原始管理 session token 不存在資料庫。
- 靜態掃描未發現 `eval`、動態 SQL 拼接、`innerHTML` 或 shell execution。
- 自動測試共 24 項通過；瀏覽器 console 無 error 或 warning。

## 正式公開前 P0

1. 將 `APP_ENV=production`、`COOKIE_SECURE=true`、`ADMIN_IP_ALLOWLIST_REQUIRED=true`。
2. SQLite 換成有獨立最小權限帳號的 PostgreSQL，設定加密備份與還原演練。
3. 正式支付回呼改用供應商規格，驗證商店編號、金額、狀態、時間、簽章與事件重播。
4. 部署到 HTTPS，前置 Cloudflare／WAF，限制管理路徑、Bot 流量與請求大小。
5. 加入管理員第二因素；不要只依賴密碼與 IP。
6. 建立退款、電子發票、隱私、數位內容交付與資料刪除規則。
7. 做依賴弱點掃描、SAST、備份演練與外部滲透測試。

## 已知風險

- 本機 SQLite 未做檔案層加密，會保存交付所需 Email；電腦帳號與磁碟必須有基本防護。
- 記憶體與 SQLite 型速率限制只適合單程序；多節點部署需改 Redis 或邊緣限流。
- 目前沒有管理員 2FA、Email 交付、退款、發票或支付對帳排程。
- 本機 Flask development server 只供預覽，不得直接暴露到 Internet。
