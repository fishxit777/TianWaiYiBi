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
- PostgreSQL CI 工作流已備妥：推送後會在 PostgreSQL 17 service container 驗證 schema、seed、參數化 insert、lastrowid、dict row 與健康檢查；實際雲端 run 尚待分支推送。

## 尚未冒充完成的帳號持有人動作

1. 建立 Neon Free 新加坡正式專案與獨立備份帳號。
2. 建立 Cloudflare Turnstile widget，hostname 只允許 `tianwai-yibi.onrender.com`。
3. 設定 Render／GitHub secrets 與 GitHub `$0` Actions hard-stop budget。
4. 執行正式資料遷移、checksum 核對、Render 切換與付款／權益回歸。
5. 由持有人親自登記 Windows Hello 與手機 Passkey，實際登出／登入兩次。
6. 下載並離線保存復原碼及 RSA 私鑰，完成一次測試還原後再啟用 Passkey-only／緊急復原。

這六項涉及第三方帳號、機密或實體裝置同意，在真正操作成功前一律標示待完成。
