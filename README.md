# 天外一筆・仙策閣

天外一筆工作室的新產品初版：一個原創修仙世界觀的付費想法商城，包含響應式官網、分區公開／私密傳音、數位內容解鎖、LINE 訊息導覽、本機模擬付款、營運後台、分析數據與安全事件紀錄。

專案位置：`C:\Users\bao58\Projects\TianWaiYiBi`

本專案與萬語通、辰新數位、NOWELYO、SoundBank、商機雷達及其他既有專案維持應用層隔離：不共用 LINE Token、資料庫、管理員收件人或部署服務。綠界可沿用同一合法特店的 MerchantID／HashKey／HashIV，但憑證只存放在本專案自己的 Render 環境變數；訂單使用 `TWYB` 前綴、`StoreID=TWYB`、獨立 callback 與獨立權益資料，做法與 NestFM 的多專案共用特店模式一致。

## 目前能做什麼

- 官網已整合核准的 V13 品牌套件：靛紫九霄、青玉靈氣、月金法陣與朱砂神筆，並同時提供深色、淺色與透明 Logo 使用情境。
- 六個想法區塊由六位原創修士代表，每位角色的能力、適用問題與付費內容不同。
- 所有想法目前統一 NT$199；管理後台改一次即可全站調價，舊訂單保留成交價。
- 使用者可建立訂單、執行本機模擬付款、測試 webhook 防重送；付款成功後才寄送專屬開通連結與一次性 12 位開通碼。
- 首次開通碼與重新登入碼都只有效 10 分鐘、只能使用一次、最多嘗試 5 次；失效可重寄，不會取消已付款的購買權限。
- 每位客戶最多保留 2 台 30 天可信裝置；第三台完成驗證時自動撤銷最久未使用的裝置。同一時間只允許 1 個有效內容工作階段，新裝置登入會讓舊工作階段失效。
- 客戶工作階段採 7 天絕對期限、24 小時閒置期限與 HttpOnly Cookie；付費內容含客戶代碼、訂單尾碼與時間的動態浮水印，不顯示完整 Email。
- 存取風險依低／中／高／重大四級記錄；正常換機不直接視為惡意，重複使用已撤銷工作階段或第 5 次錯碼才會升高。事件使用 HMAC 串鏈，可由後台檢查完整性。
- 每日台北時間 08:00、12:00、20:00 各送一次管理員營運摘要；高／重大存取、付款、登入與系統異常則不等排程，立即分別推送至天外一筆自己的管理員 LINE 與 Gmail。
- 通知含訂單營收、開通存取、安全風險、串接狀態、需處理與正常但值得知道等內容；完整客戶 Email、完整 IP、驗證碼、Token 與密鑰不會出現在外部通知，任一通道失敗也不會回滾付款或權益。
- 首頁六卷與仙策詳情頁共用可收合的分區傳音：公開內容所有訪客可讀、已驗證客戶投稿後先審核；私密內容只允許該客戶與守閣者讀取。每位客戶有固定匿名稱呼與識別色，但權限與辨識永遠同時使用名稱、徽章及後端客戶 ID，不靠顏色判斷。
- 新客戶傳音只向管理員外部通知「有新傳音」與區塊，不外送客戶身分或正文；守閣者指定回覆後，客戶 Email 也只收到登入查看提醒，不包含對話內容。寄信失敗不會回滾站內訊息。
- LINE Bot 支援好友加入、靈感目錄、價格、說明與 1～6 導覽；目錄使用六張 LINE Flex Carousel 商品卡，正式憑證未設定時可用本機模擬器完整預覽。
- 管理後台可看營收、訂單、轉換、流量來源、外部串接狀態、安全事件、封鎖 IP、傳音審核與操作稽核，也能公開／隱藏留言、指定公開或私密回覆，以及編輯每項仙策內容、單品價格、排序與上下架。
- 正式資料層已具備 PostgreSQL 相容 schema、SQLite 完整性遷移／核對工具與 PostgreSQL 17 CI；未設定 `DATABASE_URL` 時才退回本機 SQLite。
- 管理後台已具備 WebAuthn Passkey：至少兩把金鑰就緒才可停用密碼；緊急復原需 Argon2id 密碼＋一次性復原碼＋Turnstile，成功後仍須重建兩把 Passkey。
- 每日 PostgreSQL 備份先驗證再以 AES-256-GCM／RSA-OAEP 加密；GitHub 只保存 14 天加密 Artifact，離線私鑰不進雲端。2026-08-24 已完成正式 run、下載、解密、PostgreSQL 17.11 隔離還原與 24 表／164 筆逐表 checksum 驗收。
- V13 Logo 已整合官網、LINE 頭像、favicon 與後台；正式 LINE 官方帳號、Messaging API 與公開 webhook 已完成接線。
- 公開官網只保留六脈仙策、仙閣心訣與真人客服傳音入口；Logo 審稿、本機模擬器與管理後台不出現在公開導覽或頁尾。
- 整個公開官網已統一使用自架「莫大毛筆」繁體書法字系：正文用原筆、主標用同系加粗，保留真實墨邊與飛白；首頁、六脈、結帳、付款、交付、訊息與傳音頁皆一致，放大仍維持向量銳利。後台與開發工具維持清楚的操作字體。
- `/transmission` 是自有「九霄月壇・朱砂傳音詔」修仙轉場頁：桌機顯示八方月壇與高對比官方 QR 法印，手機才直接開啟 LINE，並清楚標示唯一名號與安全傳音守則。
- V16 已完成官網與後台各 20 點專業化重整：官網補齊語意 H1、難題篩選結果、用途層級、交易信任頁尾與 390px 首屏；後台改成高密度營運介面，加入正式站／同步狀態、骨架載入、六欄客戶指標、3＋3 安全旗標、表格 sticky header 與串接下一步。

正式入口：

- 官網：`https://tianwai-yibi.onrender.com/`
- LINE 官方帳號：`@279plitu`（天外一筆｜仙策靈使）

## 一鍵啟動

在 PowerShell 執行：

```powershell
cd C:\Users\bao58\Projects\TianWaiYiBi
.\run_local.ps1
```

啟動腳本會為本次程序產生隨機 `APP_SECRET_KEY`、支付 webhook secret與 32 bytes／43 位／256-bit 管理密碼，並在終端顯示臨時登入資料。服務只綁定 `127.0.0.1:5088`。

開啟：

- 官網：`http://127.0.0.1:5088/`
- LINE Bot 模擬器：`http://127.0.0.1:5088/dev/line`
- 管理後台：`http://127.0.0.1:5088/admin`

本機模擬器與管理入口僅供開發／營運使用，不得放入公開官網導覽或頁尾。

若 Windows 阻擋執行腳本，可在目前 PowerShell 視窗只放寬這一次：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run_local.ps1
```

## 測試

```powershell
.\run_tests.ps1
```

或分別執行：

```powershell
python -m compileall -q app.py tianwai tests
node --check static\app.js
node --check static\admin.js
python -m pytest -q
```

目前本機自動驗證結果為 `135 passed、1 skipped`；略過項目只在 PostgreSQL 17 CI 提供 `TEST_DATABASE_URL` 時執行。

## 公開部署

專案根目錄的 `render.yaml` 已建立獨立 Render Web Service，正式程序使用 Gunicorn，健康檢查為 `/healthz`。機密值只放在 Render 環境變數，不得提交到 Git：

- `ADMIN_PASSWORD_HASH`（正式建議；由 `scripts/generate_admin_credential.py` 產生的 Argon2id verifier）
- `DATABASE_URL`（Neon PostgreSQL pooled connection string；不得輸出到日誌或命令列）
- `WEBAUTHN_RP_ID=tianwai-yibi.onrender.com`
- `WEBAUTHN_ORIGIN=https://tianwai-yibi.onrender.com`
- `TURNSTILE_SITE_KEY`、`TURNSTILE_SECRET_KEY`（只供管理緊急復原，正式 hostname 限制為官網）
- `ADMIN_RECOVERY_ENABLED`（只有兩把 Passkey、離線復原碼與 Turnstile 均已正式驗收後才可設為 `true`；目前正式站已啟用）
- `ADMIN_PASSWORD`（只作首次輪替前或本機臨時相容；Hash 驗收後應從正式環境移除）
- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_ADMIN_USER_ID`（天外一筆管理員本人的 LINE userId；不得沿用其他專案）
- `ADMIN_ALERT_EMAIL`（天外一筆管理員本人的收件地址；不得使用客戶 Email）
- `NOTIFICATION_CRON_SECRET`（至少 32 字元，Render 與 GitHub Actions 使用同一獨立值）
- `ECPAY_MERCHANT_ID`
- `ECPAY_HASH_KEY`
- `ECPAY_HASH_IV`
- `ECPAY_STORE_ID`（固定使用 `TWYB`，供綠界後台對帳及 callback 隔離）
- `ECPAY_VERIFICATION_ENABLED`（只在執行隔離 NT$5 正式驗收時暫設為 `true`；不會開放一般商品收款）
- `PAYMENT_VERIFICATION_EMAIL`（只供管理員本人接收 NT$5 驗證開通信）
- `SMTP_HOST`、`SMTP_PORT`、`SMTP_SECURITY`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`MAIL_FROM`

GitHub Actions 已設定 `NEON_BACKUP_DATABASE_URL` 與 `BACKUP_PUBLIC_KEY_PEM`；前者是唯讀備份角色，後者只有公鑰。離線私鑰不得上傳。完整金鑰、備份與還原流程見 `docs/postgres-backup-recovery.md`。

`APP_SECRET_KEY` 與 `PAYMENT_WEBHOOK_SECRET` 由 Render 產生。設定 `DATABASE_URL` 時正式服務改用 PostgreSQL；未設定時才使用 `DATABASE_PATH` 指定的 SQLite。未設定 `BASE_URL` 時，LINE 卡片連結會自動使用目前公開請求的 HTTPS 網域。

SQLite 遷移到 PostgreSQL 時，不要把連線網址放在指令參數。先在目前 PowerShell 程序設定 `DATABASE_URL`，再執行：

```powershell
python -m scripts.migrate_sqlite_to_postgres --source data\tianwai.db --report migration-report.json
python -m scripts.verify_postgres_migration --source data\tianwai.db --report verification-report.json
```

兩份報告只包含各表筆數與 SHA-256 校驗碼，不包含 Email、訂單內容、Token 或連線字串。目的端若已有訂單、權益、工作階段或稽核資料，遷移預設拒絕覆寫。

正式管理憑證輪替請在可信任的本機終端執行：

```powershell
py -3 scripts\generate_admin_credential.py
```

產生器只在終端顯示一次 43 位 Base64url 明文與 Argon2id verifier，不會寫檔。請先將明文保存到密碼管理器，再把 verifier 設為 Render `ADMIN_PASSWORD_HASH`；確認新密碼登入成功後，移除舊 `ADMIN_PASSWORD`。不要把任何一個值貼進 Git、文件、Email、LINE 或對話紀錄。

不希望明文出現在終端時，改用本機一次性交接視窗：

```powershell
py -3 scripts\admin_credential_handoff.py
```

視窗會要求先複製並保存密碼，再把剪貼簿改成 Render 所需的 Argon2id verifier。
視窗會保留到正式登入驗收成功，期間可再次複製真正登入密碼，避免部署後鎖死；
未交付 verifier 前 30 分鐘自動失效，明文不會寫入磁碟。

本機未設定 `DATABASE_URL` 時仍可使用 SQLite 開發資料庫；SQLite 不得當成 Render 正式持久化資料。正式站目前使用 Neon PostgreSQL，且已完成加密異地備份與實際還原驗收。

## 資料與價格

- 本機資料庫：`data\tianwai.db`，第一次啟動自動建立。
- 初始六筆商品由 `tianwai\db.py` 寫入空資料庫。
- 全域價格在 `settings.idea_price`；訂單的 `orders.amount` 是不可回溯修改的成交快照。
- 專屬開通連結使用 HMAC 派生的高熵 token，網址不含 Email 或姓名；12 位開通／登入碼只保存用途隔離的 HMAC 雜湊。
- 訂單 paid 權益、短效驗證碼與客戶 session 分開保存；驗證碼失效不會刪除訂單權益。
- `customers.public_id` 是內部穩定匿名代碼；可信裝置只保存伺服器雜湊後的隨機識別，不蒐集 IMEI、廣告 ID、相機、麥克風、精準定位或其他網站資料。

重建乾淨資料庫時，請先關閉服務，再把 `data\tianwai.db` 移到備份位置；下次啟動會重建。不要在未備份時直接刪除正式資料。

## 安全邊界

- 正式管理密碼採 32 bytes／256-bit 安全亂數；伺服器優先驗證 Argon2id（19 MiB、2 次、平行度 1）環境 verifier，不寫入資料庫或日誌。舊 `ADMIN_PASSWORD` 只作輪替相容且不得在 Argon2id 存在時降級使用。
- Passkey challenge 為 32-byte、五分鐘、一次性，並綁定 IP／User-Agent；網站只保存 COSE 公鑰與必要中繼資料，不保存私鑰、生物辨識內容或 PIN。
- Passkey-only 至少兩把金鑰；復原後工作階段受限，重新登記兩把金鑰前無法讀取後台營運資料。
- 一次性復原碼各為 128-bit，資料庫只存 Argon2id；明文只在管理員主動輪替時顯示一次，不得經 LINE、Gmail 或日誌傳送。
- 管理 session 原始 token 只在 HttpOnly、SameSite=Strict Cookie 中；資料庫只保存 SHA-256 雜湊。
- 管理變更需有效 session 與 CSRF token，並寫入 `audit_logs`。
- 仙策內容欄位採伺服器端長度、型別與色系白名單驗證，前台以 Jinja escaping 輸出，不開放任意 HTML。
- 連續管理登入失敗會暫時封鎖來源 IP。
- 支援 `ADMIN_IP_ALLOWLIST_REQUIRED`、`ADMIN_ALLOWED_IPS` 與 `ADMIN_SESSION_BIND_IP`。
- LINE 與支付 webhook 使用 HMAC 驗簽，並以事件 ID 防止重複處理。
- 綠界 AioCheckOut V5 回呼驗證 CheckMacValue、MerchantID、訂單編號、金額、狀態與重送；前端返回頁不是唯一付款依據。
- 開通與登入碼最多嘗試 5 次，寄送請求限流；正式頁不顯示明文驗證碼。
- 2 台可信裝置上限、單一有效內容工作階段、7 天絕對／24 小時閒置 session，並偵測已撤銷工作階段重播。
- 客戶存取事件使用 HMAC 串鏈；後台可看匿名客戶／裝置代碼、風險分數、案件、LINE／Gmail 通知送達狀態，並可撤銷裝置、處理案件或重試告警。
- 每日摘要由 GitHub Actions 以獨立密鑰呼叫只接受 POST 的內部端點；日期、時段及通道均有唯一防重送鍵，人工重跑不會重複建立通知。
- 安全預檢攔截 `.env`、`.git`、WordPress 掃描、路徑穿越與常見注入探測；不記錄 Cookie、token 或訊息全文。
- CSP 禁止第三方腳本與 inline script；後台禁止快取與 frame 嵌入。
- 加入 COOP、CORP、Origin-Agent-Cluster、`object-src 'none'` 與跨網域政策標頭。
- `APP_SECRET_KEY` 非測試環境至少需 32 字元；正式 HTTPS 環境請設 `APP_ENV=production` 或 `COOKIE_SECURE=true`，讓公開 session Cookie 加上 Secure。

這些措施能降低常見風險，但不能宣稱「絕對防駭」。正式公開前仍需 HTTPS、Cloudflare／WAF、依賴掃描、資料備份、金流供應商正式驗證、真實退款流程與外部滲透測試。

## 已接入

- 獨立 LINE 官方帳號 `天外一筆｜仙策靈使`，Basic ID `@279plitu`。
- 獨立 LINE Provider `天外一筆工作室`、Messaging API、長期 Channel Access Token。
- Render 免費 Web Service 與 HTTPS webhook：`https://tianwai-yibi.onrender.com/line/webhook`。
- LINE Developers webhook 驗證成功，`Use webhook` 已開啟。
- LINE 內建歡迎訊息與自動回應已關閉，避免與程式回覆重複。
- V13 圓形安全區頭像、狀態消息與正式官網連結已公開。

## 待完成

- 綠界程式介面已完成；仍缺正式特店資料與 stage／正式小額驗收。
- SMTP 程式介面已完成；仍缺寄信帳號、寄件網域與實際收信驗收。
- 電子發票、退款後撤銷權益、付款失敗補單與客服 SOP。
- Neon PostgreSQL、Turnstile、兩把 Passkey、10 組復原碼、Passkey-only、GitHub 加密備份與隔離還原均已正式驗收；不得重做或以破壞性方式消耗復原碼。後續只需監控每日排程並每季做一次非正式庫還原演練。
- Render 與 GitHub Actions 的獨立 `NOTIFICATION_CRON_SECRET`、管理員收件地址及手動排程測試已完成；目前 Gmail 只缺 SMTP 寄件組態。
- 在 Render 設定天外一筆專屬 `LINE_ADMIN_USER_ID` 後，實測一筆高風險私下推播；未設定時事件仍會完整留在後台佇列。

正式接線前先決定支付供應商、單次購買／訂閱模式、退款規則、電子發票與正式網域。這些選擇會影響資料模型與法務文案，不應在沒有帳號與政策確認時假設。

## 文件

- `docs/architecture-v13.md`
- `docs/adr/0001-keep-modular-monolith-for-v13.md`
- `docs/adr/0002-separate-paid-entitlements-from-short-lived-codes.md`
- `docs/adr/0003-free-postgres-passkey-authentication.md`
- `docs/postgres-backup-recovery.md`
- `docs/updates/2026-08-23-free-postgres-passkey.md`
- `docs/plans/2026-08-23-paid-activation-and-ecpay.md`
- `docs/plans/2026-08-22-v13-product-integration.md`
- `docs/plans/2026-08-22-xiance-pavilion-design.md`
- `docs/plans/2026-08-22-xiance-pavilion-implementation.md`
- `docs/plans/2026-08-22-transmission-v2-20-point-audit.md`
- `docs/plans/2026-08-22-crisp-calligraphy-typography.md`
- `docs/plans/2026-08-22-sitewide-ink-brush-typography.md`
- `docs/plans/2026-08-23-logo-aligned-calligraphy.md`
- `docs/plans/2026-08-23-white-gold-xianxia-type-treatment.md`
- `docs/plans/2026-08-23-v14-illustrated-title-hierarchy.md`
- `docs/plans/2026-08-23-readable-public-typography.md`
- `docs/plans/2026-08-23-v15-xianxia-site-audit-and-design.md`
- `docs/plans/2026-08-23-device-trust-risk-access.md`
- `docs/plans/2026-08-23-public-admin-40-point-professionalization.md`
- `docs/plans/2026-08-23-admin-notification-design.md`
- `docs/plans/2026-08-23-admin-notifications-implementation.md`
- `docs/updates/2026-08-23-device-trust-risk-access-update.md`
- `docs/updates/2026-08-23-public-admin-40-point-professionalization.md`
- `docs/updates/2026-08-23-admin-dual-channel-notifications.md`
- `docs/security-review.md`
- `HANDOFF.md`
- `assets/brand-kit-v13/README.md`
