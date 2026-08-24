# PostgreSQL 免費加密備份與還原

## 已採用的安全邊界

- 每日 03:25（台北）執行 `pg_dump --format=custom`。
- 備份使用只讀專用 PostgreSQL 角色；角色預設交易為 read-only，沒有資料庫／schema 建立權，也沒有資料異動權。
- 先用 `pg_restore --list` 驗證封存檔，再以隨機 AES-256-GCM 金鑰串流加密。
- AES 金鑰只以離線 4096-bit RSA 公鑰（OAEP-SHA256）包裝；GitHub 只持有公鑰，不持有私鑰。
- 工作流程只上傳 `.twybenc`，明文 dump 在工作結束前刪除。
- Artifact 保留 14 天，單份加密檔超過 25 MB 就停止上傳，避免免費額度被意外吃完。
- Workflow 權限只有 `contents: read`，官方 Actions 以完整 commit SHA 固定版本。

## 目前的外部攻擊者威脅模型

本專案的主要目標是防止官網、後台、GitHub 或雲端帳號遭外部攻擊後，同時失去正式資料與備份。持有人已明確選擇不增加人工密語關卡，因此離線 RSA 私鑰採未加密 PKCS#8，只存在實體離線 USB；這避免災難時因遺失密語而無法還原，但代價是持有該 USB 的人即可解密備份。USB 必須離線、實體保管，不能接到不可信任電腦，也不能上傳、寄信或傳訊。

若日後威脅模型改成需要防範 USB 遺失或遭竊，應重新產生有密語的私鑰、輪替 GitHub 公鑰，並重新完成一次正式還原演練；不能只替現有檔案加密後就宣稱輪替完成。

## 一次性設定（已於 2026-08-24 完成）

1. 在 OneDrive 與 Git 儲存庫以外的實體離線位置產生 RSA-4096 金鑰：

   ```powershell
   python scripts/generate_backup_keypair.py --offline-passwordless --private-key D:\TWYB-Offline\backup-private.pem --public-key D:\TWYB-Offline\backup-public.pem
   ```

2. 私鑰只留在離線 USB；不得上傳 GitHub、Render、LINE、Gmail 或專案目錄。公鑰可交給 GitHub Actions。
3. GitHub repository secrets 已設定：
   - `NEON_BACKUP_DATABASE_URL`：只讀備份專用 PostgreSQL 連線；主機名稱必須從 Neon 當下的 Connect 面板取得，不得手動猜測或省略叢集識別段。
   - `BACKUP_PUBLIC_KEY_PEM`：離線 RSA-4096 公鑰。
4. 正式手動工作流 #3（run `32696239051`）已成功，只產生加密 Artifact；完整證據記錄於 `docs/updates/2026-08-23-free-postgres-passkey.md`。
5. GitHub「Billing and licensing → Budgets and alerts」仍建議為 Actions 建立 `$0` metered budget、勾選 **Stop usage when budget limit is reached**，並開啟 included usage 90%／100% 通知。

## 離線還原演練（每季一次）

1. 下載一份 Artifact 到 OneDrive 以外的隔離資料夾，先確認 ZIP 只有一個 `.twybenc`，並比對 GitHub 顯示的 Artifact SHA-256 digest。
2. 使用離線私鑰解密到 Windows 暫存區：

   ```powershell
   python scripts/decrypt_backup.py --input .\backup.twybenc --output $env:TEMP\tianwai-restore.dump --private-key-file D:\TWYB-Offline\backup-private.pem
   ```

3. 先列出內容，再還原到全新的隔離資料庫；禁止直接覆寫正式庫：

   ```powershell
   pg_restore --list $env:TEMP\tianwai-restore.dump
   createdb tianwai_restore_drill
   pg_restore --no-owner --no-privileges --dbname tianwai_restore_drill $env:TEMP\tianwai-restore.dump
   ```

4. 將來源與還原資料庫連線只放入目前程序的環境變數，不要放在指令參數或文件，然後核對所有 ordinary tables 的表數、總筆數與逐表 canonical SHA-256：

   ```powershell
   python scripts/verify_postgres_backup_restore.py --report restore-verification.json
   ```

5. 必須看到 `status=verified` 才算通過。演練結束後停止隔離 PostgreSQL，刪除明文 dump、隔離資料庫與日誌；只保留加密 Artifact 及不含資料列的驗證報告。

## 2026-08-24 正式驗收基準

- GitHub Actions run：`32696239051`，成功，提交 `cfc23e7`。
- Artifact：`tianwai-yibi-postgres-32696239051-1`，ZIP 只有一個 `.twybenc`。
- GitHub Artifact SHA-256：`2C0D72C6ADC2789DB29BC40510B61C7E63C8F446E6428D342F30A326B2FBB303`；本機下載值完全一致。
- PostgreSQL 17.11 隔離還原：`pg_restore` exit code 0，沒有診斷錯誤。
- 正式來源與還原結果：24 張表、164 筆；24 張表逐表筆數與 SHA-256 全部一致。
- 隔離叢集、明文 dump 與日誌已在核對後刪除；正式 Passkey、復原碼與管理 session 均未被撤銷或消耗。

## 免費額度保護

GitHub Free 的 Actions 與 Artifact 額度可能調整，不能把文件中的數字當成永久保證。現行工作預估每天少於 3 分鐘，14 份各自受 25 MB 上限約束；仍應定期查看 GitHub 當月用量與預算通知。
