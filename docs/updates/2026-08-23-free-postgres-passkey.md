# 2026-08-23 免費 PostgreSQL＋Passkey 安全升級

## 本次交付結果

- 建立 SQLite／PostgreSQL 雙後端，正式環境只要設定 `DATABASE_URL` 即使用 PostgreSQL。
- 建立完整 PostgreSQL schema、additive migration、真實 PostgreSQL 17 CI 驗證工作流。
- 建立 SQLite→PostgreSQL 一次性遷移與獨立核對工具；報告只有筆數與 SHA-256 checksum，不含資料值。
- WebAuthn challenge 使用 32-byte 亂數、五分鐘期限、HMAC 雜湊落庫、IP／User-Agent 綁定及一次性原子消耗。
- 只保存 Passkey credential ID、COSE 公鑰、counter、transport、裝置／備份旗標、標籤與時間，不保存私鑰、指紋、臉部、PIN。
- 正常登入要求 user verification、精確 RP ID 與 HTTPS origin；管理 session 仍為 256-bit server-side token、HttpOnly／Secure／SameSite=Strict。
- 兩把 Passkey 都完成前不能關閉密碼；切換後一般密碼入口回 404，避免揭露後台驗證模式。
- 10 組復原碼各含 128-bit 亂數，資料庫只存 Argon2id；輪替會撤銷舊碼，每組只能使用一次。
- 緊急復原必須同時通過 Argon2id 密碼、未使用復原碼與 Turnstile 伺服器驗證；成功後撤銷全部舊 session／Passkey，並即時排入 LINE＋Gmail 重大告警。
- 復原後的 session 是受限模式，只可登記 Passkey、登出與完成復原；兩把新金鑰就緒前不能進營運資料。
- 每日 PostgreSQL dump 先驗證再以 AES-256-GCM 加密，RSA-4096 私鑰只離線保存；GitHub Artifact 只收加密檔，14 天自動到期，單份 25 MB hard guardrail。

## 自動驗證

- SQLite 全套測試：108 passed、1 skipped；skipped 只在 PostgreSQL 17 CI 提供 `TEST_DATABASE_URL` 時執行。
- Passkey／復原專項：challenge 過期與重播、未知／撤銷 credential、CSRF、雙金鑰門檻、錯誤密碼不消耗復原碼、受限復原 session、Turnstile action／hostname 均有測試。
- 備份專項：加密解密 round-trip、明文不可搜尋、竄改 GCM 驗證失敗、弱 RSA key 拒絕、workflow 只上傳加密檔。
- PostgreSQL CI 工作流已推送：會在 PostgreSQL 17 service container 驗證 schema、seed、參數化 insert、lastrowid、dict row 與健康檢查；本次正式切換另以 Neon 遷移 checksum 與 Render 實際寫入驗證。

## 正式雲端執行結果

1. 已建立 Neon Free 新加坡 PostgreSQL 17 正式專案，並將 Render 正式站切換至 Neon。
2. SQLite→Neon 遷移 21 張表、111 筆資料；逐表筆數與 SHA-256 checksum 全數核對，正式瀏覽資料亦持續寫入 Neon。
3. 已建立 Cloudflare Turnstile Managed widget，hostname 只允許 `tianwai-yibi.onrender.com`，pre-clearance 關閉。
4. 已將資料庫、Turnstile、WebAuthn RP／Origin 與復原開關以 Render 私密環境變數部署；正式 `/healthz` 回 200、`release=free-postgres-passkey-v1`。
5. 持有人已親自登記 `Windows Hello（主要）` 與 `手機備援（第二把）`；正式 Neon 確認 2 把 active，兩者皆為 `multi_device`。
6. 已產生 10 組一次性復原碼；正式資料庫只存 Argon2id 雜湊，持有人下載保留一份並刪除兩份重複下載副本。
7. 已啟用 `ADMIN_RECOVERY_ENABLED=true` 與 Passkey 專用模式；未登入視角確認一般密碼表單消失，Passkey 按鈕、專用模式告知與緊急復原入口均存在，頁面不洩漏機密。
8. Windows Hello 實機重新登入通過：先由 `/admin` 安全登出，確認 `/admin/login` 只有 Passkey，再完成本人驗證並成功回到 `/admin`；今日總覽與 Neon 營運資料正常載入。
9. 2026-08-24 完成外部攻擊者威脅模型下的備份接線：RSA-4096 私鑰只存在實體離線 USB，GitHub 只取得公鑰；備份角色 `twyb_backup_ro` 為非 elevated member，預設交易 read-only，具備讀取但沒有資料異動／建物件權限。
10. GitHub Actions `Encrypted PostgreSQL backup` run `32696239051`（#3）於提交 `cfc23e7` 成功，耗時 1 分鐘，只產生 Artifact `tianwai-yibi-postgres-32696239051-1`。下載 ZIP 為 77,382 bytes，GitHub 與本機 SHA-256 均為 `2C0D72C6ADC2789DB29BC40510B61C7E63C8F446E6428D342F30A326B2FBB303`。
11. ZIP 只有 `tianwai-yibi-32696239051-1.twybenc`；加密檔 77,200 bytes、檔頭 `TWYBPG01`，沒有明文 dump。離線解密後的 PostgreSQL custom archive 為 76,375 bytes，`pg_restore --list` 取得 192 行 TOC 且驗證成功。
12. PostgreSQL 17.11 隔離叢集只監聽 `127.0.0.1:55432`；還原至全新資料庫時 `pg_restore --no-owner --no-privileges` exit code 0、零診斷錯誤。正式來源與還原端均為 24 張表、164 筆，24 張表逐表筆數與 canonical SHA-256 全部一致，報告狀態為 `verified`。
13. 驗收後已停止並刪除隔離叢集、明文 dump 與日誌；只在 Git 忽略的 `_local` 保留加密 Artifact 與不含資料列的校驗報告。正式兩把 Passkey、10 組復原碼與管理 session 全程未撤銷、未消耗。
14. 最小權限收尾完成：未使用且不擁有任何資料庫的臨時角色 `twyb_backup` 已永久刪除；production 只保留正式擁有者與 `twyb_backup_ro` 唯讀備份角色。
15. 公開管理入口完成情報最小化：畫面與直接載入的 JavaScript／CSS 不再顯示驗證技術、裝置種類、憑證數量、密碼模式或復原入口；公開端點改為中性路由與錯誤訊息，舊路由回 404。因登記時已強制使用 discoverable credential，authentication options 不再下發 `allowCredentials`，避免公開 credential ID 與數量；challenge 起始另限制每 IP 每分鐘 10 次。伺服器端 RP、origin、一次性 challenge、user verification、CSRF、Session、IP 檢查與失敗封鎖全部保留。

## 防護分類

| 類別 | 已完成防線 | 主要作用 |
| --- | --- | --- |
| 防盜／帳號遭竊 | Windows Hello 與手機兩把 Passkey、Passkey-only、安全 session、10 組離線復原碼 | 降低密碼釣魚、重放與單一裝置遺失造成的帳號接管風險 |
| 防駭／遠端攻擊 | Turnstile、登入限速與封鎖、CSRF、CSP 與安全標頭、Webhook 簽章、唯讀備份角色、機密隔離、稽核與告警 | 阻擋機器人、偽造請求、權限濫用與常見 Web 攻擊，並縮小入侵後權限 |
| 防破壞／災難復原 | 每日 `pg_dump`、AES-256-GCM、RSA-4096、GitHub 只持有公鑰、離線 USB 私鑰、14 天加密 Artifact、實際隔離還原與 checksum | 即使正式站、後台或雲端資料遭破壞，仍保有可驗證的異地復原副本 |

Passkey 同時具有防盜與防駭效果；加密備份主要是防破壞後無法復原，不等同於阻止入侵。依持有人目前的外部攻擊者威脅模型，離線私鑰未另加密，因此可隔離遠端雲端攻擊，但不防持有該實體 USB 的人；若日後要防 USB 遺失或實體竊取，必須輪替為有密語私鑰並重新完成正式還原驗收。

## 2026-08-24 備份接線問題與修正

1. 初次手動 run `32694432751`（#2）因手動組合的 Neon 主機名稱缺少目前叢集識別段而安全失敗；沒有 Artifact、沒有上傳明文。修正後規定備份主機名稱必須直接取自 Neon 當下 Connect 面板，不得依舊格式猜測。
2. SQL 動態區塊產生的密碼雖可寫入 PostgreSQL verifier，但不作為 Neon 外部代理認證的可靠設定流程；實際採用 Neon 控制層輪替密碼，並在更新 GitHub Secret 前以目前正式端點實測 `twyb_backup_ro|on`。
3. 還原驗收抓到 `verify_postgres_backup_restore.py` 直接執行時的套件匯入缺口；已補上專案根目錄 fallback 與 CLI 回歸測試，直接執行和 `python -m` 均可使用。

## 2026-08-24 卷二限定傳音 V2

- 站內留言範圍已由首頁各卷收斂為卷二六脈的六個仙策詳情頁；首頁其他卷、卷二總區與舊首頁卷別 API 不再接受讀寫。歷史資料不做物理刪除，避免破壞稽核或備份一致性。
- 新增的活動摘要只提供仙策 slug、已公開數量與最新訊息流水號，不傳留言正文、作者、Email、客戶 ID 或待審內容；匿名回應完全省略私密活動欄位。
- 已登入客戶的「有新回覆」只計算該客戶自己的守閣者私密回覆。伺服器以 HMAC 產生不可逆的 20 位匿名活動範圍，使同一瀏覽器切換不同客戶時不會互相覆蓋私密已讀狀態。
- localStorage 只保存仙策 slug、公開／私密範圍與最新流水號；不保存站內留言內容、身分、登入憑證或其他機密。沒有留言時不顯示 0；提示使用「已有傳音／新傳音／有新回覆」文字，不以顏色作為唯一辨識。
- `python -m pytest -q` 為 121 passed、1 skipped，Python／JavaScript 語法、相依、diff 與機密樣式檢查通過。桌機及 390×844 隔離瀏覽器驗證沒有水平溢位；正式提交 `f9f4c70` 已部署為 `volume-two-conversations-v2`，匿名活動 API 無私密欄位，舊首頁卷別 API 回 404。
- 本次沒有變更 PostgreSQL schema、Neon 連線、備份角色、RSA／AES 金鑰、Passkey、復原碼、Turnstile、付款或管理登入；正式煙霧測試也沒有建立留言或使用真實客戶資料。

## 2026-08-24 卷二匿名公開傳音 V3

- 匿名只代表官網不要求登入及不公開真實身分，不代表無限制。訪客只可投稿公開傳音，而且每則固定為 `pending`；私密傳音仍需有效客戶 session，訪客端無法選擇或繞過。
- 訪客第一次投稿時取得 256-bit 隨機 HttpOnly／SameSite=Lax Cookie；資料庫只保存以 `APP_SECRET_KEY` 分域 HMAC 後的訪客雜湊。來源 IP 也只以另一用途分域的 HMAC 保存於留言列，原始 Cookie、原始 IP、Email 與內部客戶 ID 都不會進入公開／管理傳音 API。
- 同一訪客可看自己的待審留言，其他匿名訪客在核准前看不到。公開後顯示穩定的 `訪客・XXXXXX`、識別色與「訪客」文字徽章；管理員公開回覆時會顯示回覆該匿名代號，但訪客沒有私密收件權限。
- 防濫用採 CSRF、Cloudflare Turnstile 獨立 `public-conversation` action、精確 hostname、蜜罐、2～500 字、純文字、網址／HTML 拒絕、訪客與來源雙重限速（10 分鐘 3 則、24 小時 10 則）。Turnstile 未設定或驗證失敗時採失敗關閉，不會降級成無驗證匿名投稿。
- SQLite 舊表因 CHECK constraint 無法原地修改，採交易式重建並保留既有 ID／內容／回覆關聯；PostgreSQL 採 additive columns 後更新明確命名的作者與可見性約束，並以交易 advisory lock 防止 Gunicorn 多 worker 同時啟動時競爭遷移。SQLite 舊資料升級與 PostgreSQL worker 鎖定防線已有自動測試；正式 PostgreSQL 遷移仍以部署健康檢查作最後證據。
- `python -m pytest -q` 為 127 passed、1 skipped；Python compileall、JavaScript syntax、`pip check`、diff 與機密樣式檢查通過。桌機及 390×844 本機瀏覽器實看匿名公開、手機 Turnstile 窄版與私密登入分流；正式站未建立測試留言，也沒有消耗復原碼、撤銷 Passkey 或重跑備份還原。
- 本次只重用既有正式 Turnstile widget 的公鑰／私密設定，不新增或傳送任何機密；沒有變更 Neon 連線、備份角色、RSA／AES 金鑰、Passkey、復原碼、付款或管理登入。

## 刻意未執行的破壞性操作

- 沒有在正式站消耗復原碼做管理帳號災難復原；該流程會撤銷兩把 Passkey 與全部管理 session，不應只為資料庫備份驗收而執行。
- 沒有撤銷或重建任何正式 Passkey；本次證明的是資料庫備份可解密、可還原、資料完整，不等同於要觸發管理身分復原。
- GitHub 帳號層級 Actions budget 沒有擅自修改，避免影響同帳號其他儲存庫；它是可選帳務成本控制，不是本專案防盜、防駭或災難復原的未完成項目。

涉及機密或實體裝置同意的步驟，在真正操作成功前一律標示待完成；任何私鑰、密語、復原碼或資料庫連線值都不得寫入本文件。
