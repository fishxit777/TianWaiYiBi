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

- SQLite 全套測試：103 passed（正式文件更新後數量可能再增加）。
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

## 尚未冒充完成的項目

1. 正式 GitHub Actions 尚未設定 `NEON_BACKUP_DATABASE_URL` 與 `BACKUP_PUBLIC_KEY_PEM`，也尚未產生／離線保存 RSA 私鑰。
2. 尚未下載正式加密 Artifact 並在隔離 PostgreSQL 完成解密還原與 checksum 核對，因此災難復原仍是待完成。
3. 沒有消耗復原碼做破壞性復原演練；完整復原會撤銷兩把 Passkey 與全部管理 session，不應只為一般驗收在正式站執行。

涉及機密或實體裝置同意的步驟，在真正操作成功前一律標示待完成；任何私鑰、密語、復原碼或資料庫連線值都不得寫入本文件。
