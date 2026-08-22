# 天外一筆・仙策閣

天外一筆工作室的新產品初版：一個原創修仙世界觀的付費想法商城，包含響應式官網、數位內容解鎖、LINE Bot 邏輯、本機模擬付款、營運後台、分析數據與安全事件紀錄。

專案位置：`C:\Users\bao58\Projects\TianWaiYiBi`

本專案與萬語通、辰新數位、NOWELYO、SoundBank、商機雷達及其他既有專案完全分離。沒有共用 Token、資料庫、管理員收件人、金流帳號或部署服務。

## 目前能做什麼

- 官網已整合核准的 V13 品牌套件：靛紫九霄、青玉靈氣、月金法陣與朱砂神筆，並同時提供深色、淺色與透明 Logo 使用情境。
- 六個想法區塊由六位原創修士代表，每位角色的能力、適用問題與付費內容不同。
- 所有想法目前統一 NT$199；管理後台改一次即可全站調價，舊訂單保留成交價。
- 使用者可建立訂單、執行本機模擬付款、測試 webhook 防重送，並取得專屬內容連結。
- LINE Bot 支援好友加入、靈感目錄、價格、說明與 1～6 導覽；目錄使用六張 LINE Flex Carousel 商品卡，正式憑證未設定時可用本機模擬器完整預覽。
- 管理後台可看營收、訂單、轉換、流量來源、外部串接狀態、安全事件、封鎖 IP 與操作稽核，也能編輯每項仙策內容、單品價格、排序與上下架。
- V13 Logo 已整合本機官網、LINE 模擬頭像、favicon 與後台；正式 LINE 官方帳號已建立，頭像與 Messaging API 仍待完成接線。

## 一鍵啟動

在 PowerShell 執行：

```powershell
cd C:\Users\bao58\Projects\TianWaiYiBi
.\run_local.ps1
```

啟動腳本會為本次程序產生隨機 `APP_SECRET_KEY`、支付 webhook secret 與管理密碼，並在終端顯示臨時登入資料。服務只綁定 `127.0.0.1:5088`。

開啟：

- 官網：`http://127.0.0.1:5088/`
- Logo 評估：`http://127.0.0.1:5088/logo-review`
- LINE Bot 模擬器：`http://127.0.0.1:5088/dev/line`
- 管理後台：`http://127.0.0.1:5088/admin`

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
python -m py_compile app.py tianwai\*.py
node --check static\app.js
node --check static\admin.js
python -m pytest -q
```

目前自動驗證結果為 `26 passed`。

## 公開部署

專案根目錄的 `render.yaml` 可建立獨立 Render Web Service，正式程序使用 Gunicorn，健康檢查為 `/healthz`。機密值只放在 Render 環境變數，不得提交到 Git：

- `ADMIN_PASSWORD`
- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`

`APP_SECRET_KEY` 與 `PAYMENT_WEBHOOK_SECRET` 由 Render 產生。`DATABASE_PATH` 可指定資料庫檔案位置；未設定 `BASE_URL` 時，LINE 卡片連結會自動使用目前公開請求的 HTTPS 網域。

免費 Render 初版的 SQLite 檔案不是正式持久化資料庫，重新部署或重建執行個體時可能重建。可用於真人 LINE Bot、官網與需求驗證，但正式收款前必須換成持久化 PostgreSQL 或付費磁碟並建立備份。

## 資料與價格

- 本機資料庫：`data\tianwai.db`，第一次啟動自動建立。
- 初始六筆商品由 `tianwai\db.py` 寫入空資料庫。
- 全域價格在 `settings.idea_price`；訂單的 `orders.amount` 是不可回溯修改的成交快照。
- 已付款內容透過 HMAC 派生的高熵 access token 存取，網址不含 Email 或姓名；資料庫只存 token 雜湊。

重建乾淨資料庫時，請先關閉服務，再把 `data\tianwai.db` 移到備份位置；下次啟動會重建。不要在未備份時直接刪除正式資料。

## 安全邊界

- 管理密碼只讀環境變數，不寫入資料庫或日誌。
- 管理 session 原始 token 只在 HttpOnly、SameSite=Strict Cookie 中；資料庫只保存 SHA-256 雜湊。
- 管理變更需有效 session 與 CSRF token，並寫入 `audit_logs`。
- 仙策內容欄位採伺服器端長度、型別與色系白名單驗證，前台以 Jinja escaping 輸出，不開放任意 HTML。
- 連續管理登入失敗會暫時封鎖來源 IP。
- 支援 `ADMIN_IP_ALLOWLIST_REQUIRED`、`ADMIN_ALLOWED_IPS` 與 `ADMIN_SESSION_BIND_IP`。
- LINE 與支付 webhook 使用 HMAC 驗簽，並以事件 ID 防止重複處理。
- 安全預檢攔截 `.env`、`.git`、WordPress 掃描、路徑穿越與常見注入探測；不記錄 Cookie、token 或訊息全文。
- CSP 禁止第三方腳本與 inline script；後台禁止快取與 frame 嵌入。
- 加入 COOP、CORP、Origin-Agent-Cluster、`object-src 'none'` 與跨網域政策標頭。
- `APP_SECRET_KEY` 非測試環境至少需 32 字元；正式 HTTPS 環境請設 `APP_ENV=production` 或 `COOKIE_SECURE=true`，讓公開 session Cookie 加上 Secure。

這些措施能降低常見風險，但不能宣稱「絕對防駭」。正式公開前仍需 HTTPS、Cloudflare／WAF、依賴掃描、資料備份、金流供應商正式驗證、真實退款流程與外部滲透測試。

## 尚未接入／待完成

- 已建立獨立 LINE 官方帳號 `天外一筆｜仙策靈使`（Basic ID：`@279plitu`）；Messaging API、公開 webhook 與正式頭像尚待完成。
- 綠界、LINE Pay 或其他正式金流商店資料。
- 電子發票、退款、付款失敗補單與 Email 交付。
- PostgreSQL、持久化備份與監控；Render Blueprint 已備妥但尚未建立正式服務。
- 會員帳號與跨裝置訂單查詢。

正式接線前先決定支付供應商、單次購買／訂閱模式、退款規則、電子發票與正式網域。這些選擇會影響資料模型與法務文案，不應在沒有帳號與政策確認時假設。

## 文件

- `docs/architecture-v13.md`
- `docs/adr/0001-keep-modular-monolith-for-v13.md`
- `docs/plans/2026-08-22-v13-product-integration.md`
- `docs/plans/2026-08-22-xiance-pavilion-design.md`
- `docs/plans/2026-08-22-xiance-pavilion-implementation.md`
- `docs/security-review.md`
- `HANDOFF.md`
- `assets/brand-kit-v13/README.md`
