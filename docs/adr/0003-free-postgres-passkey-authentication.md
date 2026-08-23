# ADR 0003：免費 PostgreSQL、Passkey 與離線復原

- 狀態：已接受，程式完成；正式雲端切換待帳號持有人驗收
- 日期：2026-08-23

## 決策

1. 正式交易資料使用 Neon Free PostgreSQL；SQLite 只留本機開發與切換前唯讀來源。
2. 管理員日常登入改用 WebAuthn Passkey，至少登記 Windows Hello 與手機／硬體金鑰兩把，才允許停用一般密碼登入。
3. 原 Argon2id 密碼只作緊急復原因素，必須再搭配一組 128-bit 一次性復原碼與 Cloudflare Turnstile 伺服器驗證。
4. 緊急復原會撤銷全部舊管理工作階段與舊 Passkey，只建立受限工作階段；重新登記兩把 Passkey 前不能進入營運後台。
5. 每日備份使用 `pg_dump` custom format，驗證後以 AES-256-GCM 加密；資料金鑰由離線 4096-bit RSA-OAEP-SHA256 公鑰包裝，雲端不保存私鑰。

## 理由

- 真正瓶頸是 Render 免費服務的 SQLite 不持久，而非密碼長度。
- Passkey 抵抗釣魚與重複密碼風險，Windows Hello 與手機備援不需另付月費。
- 雙 Passkey 避免單一裝置故障；三因素緊急復原避免只靠密碼或 Email。
- 同一 Flask 模組化單體可保留既有付款、權益與稽核邏輯，降低重寫風險與維護成本。

## 取捨與限制

- 免費雲端服務可能休眠、調整額度或政策；必須保留可還原的加密備份。
- Passkey 建立一定需要裝置持有人同意並完成 Windows Hello／手機解鎖，不能由部署程式暗中代辦。
- `$0` 預算、Neon 專案、Turnstile widget、GitHub secrets 與兩把 Passkey 都屬帳號／實體裝置動作，只有實際驗收後才算完成。
- 復原碼明文只顯示一次；遺失兩把 Passkey、管理密碼、所有復原碼與離線備份將無法安全繞過。

## 不採用

- 每次登入寄隨機密碼：增加 Email 被接管、延遲與供應商故障風險，且不抗釣魚。
- 只依賴超長固定密碼：沒有裝置持有證明，外洩後可直接重播。
- 將生物辨識資料傳到網站：WebAuthn 不需要也不允許此設計，網站只保存公開金鑰。
- 未加密 GitHub artifact：即使 repository 私有，仍不應把完整交易資料交給單一雲端權限邊界。
