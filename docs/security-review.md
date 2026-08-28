# 仙策閣初版安全複查

日期：2026-08-23；更新：2026-08-28

## 結論

PostgreSQL 正式切換、兩把實機 Passkey、三因素緊急復原設定與加密異地備份實際還原均已完成，但不宣稱「絕對防盜或防駭」。綠界真實小額付款、退款、SMTP 交付與法律文字尚未完成前，仍不得視為正式收款閉環驗收完成。

## 2026-08-24 分區混合傳音安全增補

- 公開傳音只回傳 `published`；客戶本人的 `pending` 只在有效客戶工作階段下額外回傳，匿名訪客與其他客戶不可見。
- 私密傳音查詢固定要求有效客戶 session，並在 SQL 同時限制 `visibility='private'` 與目前 `customer_id`；前端頁籤或 CSS 不承擔權限。
- 公開身分只由匿名客戶代碼產生 `同道・XXXX` 與固定色票，不顯示真名、Email 或內部客戶 ID。顏色不作權限依據，名稱與文字徽章永遠同時存在。
- 客戶寫入需 CSRF、有效 active 客戶狀態、允許區塊白名單、2～800 字純文字與速率限制。疑似 HTML 一律拒絕，公開網址也先拒絕；前端以 `textContent` 顯示正文。
- 公開留言採先審後發；管理核准、隱藏、公開與私密回覆都要求 Passkey 後台 session、管理 CSRF，並只記錄訊息代碼與狀態到 audit log，不記錄正文。
- 新留言的管理員 LINE 通知不包含客戶身分或正文；指定回覆的客戶 Email 只包含登入查看提醒。通知失敗不回滾資料庫訊息。
- 傳音 API 回應 `no-store`；付款、登入、開通、付費內容與管理安全頁面不嵌入傳音元件。

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
- 開通碼與登入碼均為 12 位、一次性、伺服器端 10 分鐘有效、用途隔離 HMAC 雜湊、最多嘗試 5 次，舊碼在重寄後立即撤銷。
- 每位客戶最多 2 台 30 天可信裝置；裝置使用隨機第一方 HttpOnly Cookie，資料庫只保存 HMAC，不使用侵入式瀏覽器指紋。
- 同一時間只保留 1 個有效客戶工作階段；session 為 7 天絕對期限與 24 小時閒置期限。新裝置登入撤銷舊 session，第三台裝置撤銷最久未使用裝置。
- 已撤銷工作階段第一次重播為中度，第二次升為高風險；第 5 次錯誤驗證碼升為高風險。正常換機本身不直接判定為惡意。
- `access_events` 採逐筆 HMAC 串鏈，後台可驗證前一筆與本筆雜湊，降低事後無痕修改風險。
- 高／重大事件即時推送管理員私人 LINE；訊息包含案件、事件、匿名客戶代碼、遮罩 IP、系統動作與建議處置，不含完整 Email、完整 IP、驗證碼、session、Token 或付款憑證。
- LINE 先寫入佇列再送出；通知失敗不回滾付款、權益、裝置或 session，管理員可在後台檢視與重試。舊管理 Gmail 佇列只保留稽核且停止重試。
- 每日 08:00、12:00、20:00 摘要使用獨立至少 32 字元的排程密鑰與常數時間比對；日期、時段、通道有唯一防重送鍵。
- 客戶交易郵件失敗會建立即時 LINE 管理告警；客戶交易 Email 本身仍保留原交付與失敗紀錄。
- 付費頁有匿名客戶代碼、訂單尾碼與顯示時間浮水印；不把完整個資放進畫面。
- WebAuthn 只保存 credential ID、COSE 公鑰、counter 與必要中繼資料；challenge 為 32-byte、五分鐘、HMAC 雜湊落庫並一次性消耗。
- Passkey-only 至少需要兩把已驗證金鑰；撤銷保護不允許刪除最後一把。網站無法取得 Windows Hello／手機內的指紋、臉部、PIN 或私鑰。
- 緊急復原要求 Argon2id 密碼、128-bit 一次性復原碼及 Turnstile server-side 驗證；成功後撤銷舊 session／Passkey，只開放受限重新登記。
- PostgreSQL 備份使用 pg custom format 驗證、AES-256-GCM 加密及離線 RSA-4096 key wrapping；CI 只上傳 14 天的加密 Artifact。

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
- 驗證碼固定 600 秒、失效不刪除 paid 權益、一次性不可重用。
- 三個獨立瀏覽器客戶驗證：只保留 2 台可信裝置與 1 個有效 session；最舊裝置被撤銷。
- 已撤銷 session 連續重播能由中度升為高風險並建立私人告警佇列。
- 告警 payload 不含完整 Email、完整 IP、驗證碼、Token 或排程密鑰；證據鏈逐筆驗證通過。
- 後台可看匿名裝置清單、撤銷裝置、處理風險案件與重試 LINE 告警，所有 mutation 仍需管理 session 與 CSRF。
- 最新自動測試共 120 項通過、1 項只在 PostgreSQL 17 CI 執行；傳音的公開審核、私密隔離、CSRF、限流、匿名身分、管理操作與通知正文防外洩均有自動測試。Python／JavaScript 語法檢查、`pip check`、加密竄改測試與秘密值靜態掃描通過。

## 正式公開前 P0

1. 將 `APP_ENV=production`、`COOKIE_SECURE=true`、`ADMIN_IP_ALLOWLIST_REQUIRED=true`。
2. PostgreSQL、最小權限 Neon 備份角色、checksum 遷移與實際還原演練已完成；持續監看每日加密 Artifact，並每季重做隔離還原。
3. 正式支付回呼改用供應商規格，驗證商店編號、金額、狀態、時間、簽章與事件重播。
4. 部署到 HTTPS，前置 Cloudflare／WAF，限制管理路徑、Bot 流量與請求大小。
5. Windows Hello 與手機兩把 Passkey、Passkey-only 及登出後重新登入均已實測；後續只做非破壞性登入確認，不為測試撤銷兩把金鑰或消耗復原碼。
6. 建立退款、電子發票、隱私、數位內容交付與資料刪除規則；正式隱私政策需載明裝置、IP 概略資訊、session 與內容事件類別。
7. 做依賴弱點掃描、SAST、備份演練與外部滲透測試。

## 已知風險

- 本機 SQLite 未做檔案層加密，會保存交付所需 Email；電腦帳號與磁碟必須有基本防護。
- 記憶體與 SQLite 型速率限制只適合單程序；多節點部署需改 Redis 或邊緣限流。
- Passkey、Turnstile、Neon 與加密還原已正式驗收；正式退款撤權、發票、支付對帳排程、SMTP 與綠界仍需實際設定驗收。
- 傳音限流目前以 PostgreSQL 依客戶與時間窗查詢，適合現有單一 Render 服務；若日後改成多區域高流量部署，應在 Cloudflare／Redis 增加分散式邊緣限流與垃圾訊息評分。
- `LINE_ADMIN_USER_ID` 或排程密鑰若尚未設定，管理事件仍會進 LINE 佇列與後台，但狀態會是 `skipped`／`failed`，不代表事件遺失。交易 Email 服務設定獨立判讀。
- SQLite HMAC 串鏈能顯示資料被改動，但 APP secret 與資料庫同時失守時無法提供獨立第三方時間戳；正式證據保存仍需遠端不可變日誌／備份。
- 本機 Flask development server 只供預覽，不得直接暴露到 Internet。
