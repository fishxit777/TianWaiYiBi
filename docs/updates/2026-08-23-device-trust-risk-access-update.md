# 2026-08-23｜可信裝置、單一存取與風險分級更新表

## 核准決策

採用「2 台可信裝置＋1 台同時存取＋10 分鐘驗證碼＋風險分級」。設計原則是先保留已付款權益，再以短效驗證、裝置信任、單一 session、事件證據與管理端處置降低盜用；系統不把正常換機直接標成犯罪。

## 完整客戶流程

1. 客戶在結帳頁輸入稱呼與 Email，付款前視窗明確顯示金額、數位內容、10 分鐘驗證碼、2 台可信裝置、1 台同時存取及安全事件記錄類別。
2. 付款必須由伺服器通知確認；只有訂單轉為 `paid` 才建立並寄送專屬開通頁與 12 位開通碼。
3. 開通碼只保存用途隔離 HMAC，建立後 10 分鐘失效，只能成功使用一次，重寄會撤銷舊碼，最多錯 5 次。
4. 首次驗證成功後建立匿名客戶代碼、可信裝置及客戶 session，轉入該訂單的付費內容；驗證碼失效不會刪除 `paid` 訂單或內容權益。
5. 日後以購買 Email 申請另一組 12 位登入碼。登入碼同樣 10 分鐘、一次性、最多錯 5 次。
6. 裝置以伺服器產生的第一方隨機 HttpOnly Cookie 識別；伺服器只存 HMAC。信任 30 天，不讀 IMEI、廣告 ID、相機、麥克風、精準位置或其他網站資料。
7. 每位客戶最多保留 2 台有效可信裝置。第三台完成有效 Email 驗證後，系統撤銷最久未使用的裝置與該裝置 session，再加入新裝置。
8. 任何時間只保留 1 個有效內容 session。新裝置驗證成功後，其他 session 以 `single_session_transfer` 撤銷；手機沒電改用電腦屬正常切換，不會單因換機發高風險警示。
9. 客戶 session 最長 7 天，連續 24 小時未使用也會失效；登出會立即撤銷目前 session，但可信裝置仍保留至 30 天到期或被替換／管理員撤銷。
10. 付費內容顯示匿名客戶代碼、遮罩訂單尾碼與時間浮水印；不顯示完整 Email、IP、驗證碼或 session token。

## 風險處理矩陣

| 事件 | 分數／級別 | 系統動作 | 管理員通知 |
|---|---:|---|---|
| 首次建立 session | 5／低 | 記錄、放行 | 不推播 |
| 新增第二台可信裝置 | 10／低 | 記錄、放行 | 不推播 |
| 同裝置重新驗證並切換 session | 15／低 | 舊 session 撤銷 | 不推播 |
| 錯碼第 1～2 次 | 25～30／低至中 | 拒絕、累計次數 | 中度只在後台 |
| 換到另一台裝置 | 30／中 | 舊 session 撤銷、新 session 生效 | 後台案件，不私訊 |
| 第三台取代最舊裝置 | 40／中 | 最舊裝置與其 session 撤銷 | 後台案件，不私訊 |
| 已撤銷 session 第一次再用 | 35／中 | 拒絕、累計重播 | 後台案件 |
| 已撤銷 session 第二次以上再用 | 70／高 | 拒絕、建立案件 | 私下 LINE＋後台 |
| 驗證碼第 5 次錯誤 | 65／高 | 撤銷該碼、建立案件 | 私下 LINE＋後台 |
| 分數 85 以上 | 重大 | 依事件拒絕／保留證據 | 私下 LINE＋後台 |

高／重大 LINE 只含事件類型、案件編號與 `TYB-...` 匿名客戶代碼。完整 Email、完整 IP、驗證碼、付款憑證、Cookie 與 token 都不進 LINE 訊息。

## 程式與資料更新表

| 區域 | 更新內容 | 驗證方式 |
|---|---|---|
| `activation_codes` | 首次碼改為 600 秒、一次性、5 次上限、重寄撤舊 | 精確比較 `expires_at-created_at=600` |
| `customer_login_codes` | 登入碼改為 600 秒、一次性、5 次上限 | 過期與重用測試 |
| `customers` | 新增匿名 `public_id`、狀態、最高風險級別 | 付款後自動建立／舊訂單遷移 |
| `customer_devices` | 2 台上限、30 天信任、HMAC token、最後使用、撤銷原因 | 三個獨立測試瀏覽器登入 |
| `customer_sessions` | 綁定客戶與裝置、7 天絕對／24 小時閒置、單一有效、重播次數 | 舊裝置被轉址登入頁、DB 只剩 1 筆 active |
| `access_events` | 事件 ID、分數、級別、匿名關聯、HMAC 前後串鏈 | `verify_access_event_chain()` |
| `risk_incidents` | 中／高／重大案件、處理狀態、稽核更新 | 後台開始檢視／標記完成 |
| `notification_queue` | LINE 先入列後寄送、去重、送達／失敗／略過、手動重試 | 未設定時為 skipped，事件仍保留 |
| 付費內容頁 | 動態匿名浮水印、no-store、禁止 frame | HTML、標頭與瀏覽器檢查 |
| 結帳頁 | 消費者明確說明裝置、session、IP 概略與事件記錄 | 同意版本 `2026-08-23-v2-device-risk` |
| 管理後台 | 可信裝置表、撤銷、風險事件、證據鏈、案件處理、LINE 佇列重試 | 管理 session＋CSRF 測試 |
| 私下 LINE | 新環境變數 `LINE_ADMIN_USER_ID`，只對高／重大推播 | 設定後以測試案件驗收 |
| 部署識別 | `/healthz` 回傳 `release=trusted-device-risk-v1` | 公開部署可明確核對新版本 |

## 後台處置流程

1. 「今日總覽」只把高／重大事件列為立即注意。
2. 「客戶開通」查看匿名客戶代碼、風險級別與可信裝置數；裝置表只顯示遮罩網路資訊。
3. 發現不明裝置時按「撤銷裝置」，系統同時撤銷該裝置的有效 session 並寫入管理稽核。
4. 「安全稽核」先確認證據鏈顯示完整，再查看事件分數與風險案件。
5. 案件可標成 `reviewing` 或 `resolved`；狀態改變寫入 `audit_logs`，不刪除原始事件。
6. 私下 LINE 未送達時按「重試未送達」；是否送達不會改變客戶付款或內容權益。

## 完整驗證步驟

1. 執行 `python -m compileall -q app.py tianwai tests`。
2. 執行 `node --check static/app.js` 與 `node --check static/admin.js`。
3. 執行 `python -m pytest -q`，預期 `51 passed`。
4. 執行 `python -m pip check`，預期 `No broken requirements found`。
5. 用瀏覽器 A 建單、模擬付款、取得碼並開通，確認 Email 文案與頁面均為 10 分鐘。
6. 用瀏覽器 B 對同 Email 申請登入碼並登入，確認 A 再讀 `/customer/library` 會回登入頁。
7. 用瀏覽器 C 登入，確認後台有效可信裝置仍為 2、有效 session 為 1，最舊裝置標示 `device_limit_replacement`。
8. 讓已撤銷的 B 連續存取兩次，確認第一次為中度、第二次為高風險，並建立去識別 LINE 告警。
9. 在付費內容頁確認浮水印包含 `TYB-...`、`ORD-***尾碼` 與時間，不含完整 Email。
10. 登入後台撤銷目前裝置，確認客戶立即失去 session；再更新案件與重試告警，確認全部寫入稽核。
11. 確認 `/healthz`、官網與登入頁回 200，未登入 `/admin/api/dashboard` 回 401，付費與管理頁維持 no-store／frame deny。

本次實際結果：51 passed；舊版 SQLite 副本原地 migration 通過；桌機 1280 與手機 390 × 844 無水平溢位；付費內容顯示 12 組動態匿名浮水印；後台證據鏈顯示完整；瀏覽器 console 0 error、0 warning。

## 公開部署紀錄

- 實作 commit：`85bf87c feat: add trusted device risk access controls`。
- 部署識別 commit：`0337e9e chore: expose release health marker`。
- GitHub：`main` 已推送，Render `autoDeploy` 已完成上線。
- 正式 `/healthz`：HTTP 200，`status=ok`，`release=trusted-device-risk-v1`。
- 正式 `/`、`/customer/login`、`/admin/login`：HTTP 200。
- 客戶／後台登入頁：`Cache-Control: no-store`、`X-Frame-Options: DENY`。
- `/logo-review`、正式 `/dev/line`：HTTP 404，私密／開發入口未重新出現在公開站。

## 尚需外部設定／不可假裝完成

- `LINE_ADMIN_USER_ID` 必須填天外一筆管理員本人的 LINE userId；目前程式不會沿用萬語通或其他專案收件人。未填時告警為 `skipped`，但後台事件、案件與佇列仍完整保留。
- Render 免費方案的 SQLite 不具正式持久性。這套證據鏈只能在資料仍存在時驗證；正式收款前必須改 PostgreSQL 或付費持久磁碟，並建立異地備份／還原演練。
- HMAC 串鏈可偵測資料被改動，但不是第三方公證；高爭議證據需要遠端不可變日誌、可信時間戳與正式保全流程。
- 綠界、SMTP、退款撤權、電子發票及正式隱私政策仍需各自的真實帳號與法務／營運驗收。
