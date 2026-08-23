# PostgreSQL 免費加密備份與還原

## 已採用的安全邊界

- 每日 03:25（台北）執行 `pg_dump --format=custom`。
- 先用 `pg_restore --list` 驗證封存檔，再以隨機 AES-256-GCM 金鑰串流加密。
- AES 金鑰只以離線 4096-bit RSA 公鑰（OAEP-SHA256）包裝；GitHub 不持有私鑰。
- 工作流程只上傳 `.twybenc`，明文 dump 在工作結束前刪除。
- Artifact 保留 14 天，單份加密檔超過 25 MB 就停止上傳，避免免費額度被意外吃完。
- Workflow 權限只有 `contents: read`，官方 Actions 以完整 commit SHA 固定版本。

## 一次性設定（帳號持有人親自完成）

1. 在 OneDrive 與 Git 儲存庫以外的離線位置產生金鑰。私鑰密語至少 16 字元，建議由密碼管理器產生：

   ```powershell
   python scripts/generate_backup_keypair.py --private-key D:\TWYB-Offline\backup-private.pem --public-key D:\TWYB-Offline\backup-public.pem
   ```

2. 將 `backup-private.pem` 與密語分開保存，至少保留兩份離線副本。不得上傳私鑰、不得寄 Email、不得傳 LINE。
3. 在 GitHub repository secrets 設定：
   - `NEON_BACKUP_DATABASE_URL`：唯讀／備份專用 PostgreSQL 連線。
   - `BACKUP_PUBLIC_KEY_PEM`：`backup-public.pem` 完整內容（公鑰可公開，但仍集中管理）。
4. GitHub「Billing and licensing → Budgets and alerts」為 Actions 建立 `$0` metered budget，勾選 **Stop usage when budget limit is reached**，並開啟 included usage 90%／100% 通知。
5. 手動執行一次 `Encrypted PostgreSQL backup`，確認 Artifact 只有 `.twybenc`。

## 離線還原演練（每季一次）

1. 下載一份 `.twybenc` 到 OneDrive 以外的隔離資料夾。
2. 在離線環境輸入私鑰密語解密：

   ```powershell
   python scripts/decrypt_backup.py --input .\backup.twybenc --output .\restore.dump --private-key-file D:\TWYB-Offline\backup-private.pem
   ```

3. 先列出內容，再還原到全新的測試資料庫，禁止直接覆寫正式庫：

   ```powershell
   pg_restore --list .\restore.dump
   createdb tianwai_restore_drill
   pg_restore --clean --if-exists --no-owner --dbname tianwai_restore_drill .\restore.dump
   ```

4. 核對資料表筆數、訂單／權限關聯與抽樣校驗碼。演練結束後安全刪除明文 `restore.dump` 與測試資料庫。

## 免費額度保護

GitHub Free 的 Actions 目前含每月 2,000 分鐘與 500 MB artifact storage；本工作預估每天少於 3 分鐘，14 份各自受 25 MB 上限約束。`$0` hard-stop budget 是最後防線，但首次建立預算前已發生的用量不會回溯納入，因此仍要檢查當月既有用量。
