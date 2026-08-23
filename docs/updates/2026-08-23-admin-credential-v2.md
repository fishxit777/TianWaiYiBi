# 管理員憑證 V2：256-bit＋Argon2id

日期：2026-08-23  
版本：`admin-credential-v2`

## 結論

後台管理憑證已具備 32 bytes／43 位 Base64url／256-bit 安全亂數產生能力，伺服器新增 Argon2id 慢雜湊驗證。舊 `ADMIN_PASSWORD` 暫時保留為部署輪替相容；只要 `ADMIN_PASSWORD_HASH` 存在，系統就強制使用 Argon2id，舊明文即使正確也不能降級登入。

## 安全計算

- 亂數來源：Python `secrets`／作業系統 CSPRNG。
- 原始亂數：32 bytes＝256 bits。
- 顯示格式：無 padding 的 Base64url，固定 43 位，只含 `A-Z a-z 0-9 - _`。
- 搜尋空間：`2^256`；這是精確亂數熵，不是依字元種類推測的密碼強度分數。
- Argon2id：19 MiB memory cost、2 iterations、parallelism 1、16-byte salt、32-byte hash。
- 本機實測：單次雜湊約 24 ms；正常登入無明顯延遲，離線大量猜測成本顯著高於快速 SHA 類雜湊。

## 已完成

- `tianwai/security.py`：安全密碼產生、Argon2id 雜湊／驗證、Hash 優先與禁止明文降級。
- `scripts/generate_admin_credential.py`：一次性顯示新密碼與 verifier，不寫檔。
- `run_local.ps1`：臨時管理密碼由 96-bit 升級為 256-bit。
- `render.yaml`／`.env.example`：新增私密 `ADMIN_PASSWORD_HASH` 設定與輪替說明。
- 後台安全稽核：新增「管理員 Argon2id 憑證」狀態，不回傳密碼或雜湊。
- 保留 15 分鐘內錯誤 5 次即封鎖 15 分鐘、通用錯誤訊息、HttpOnly／SameSite=Strict session、IP 綁定與 CSRF。
- 客戶 12 位開通碼與 10 分鐘登入碼維持單次、短效、限次；未錯誤套用管理員長密碼規則。

## 驗證

- 43 位格式、20 組唯一亂數與 256-bit 常數：通過。
- 正確密碼／錯誤密碼 Argon2id 驗證：通過。
- Hash 存在時拒絕舊明文降級：通過。
- 後台只回傳布林狀態、不洩漏 verifier：通過。
- `py -3 -m pytest -q`：63 passed。
- `py -3 -m pip check`：無相依衝突。
- `pip-audit -r requirements.txt`：No known vulnerabilities found。

## 正式輪替邊界

程式部署不等於正式密碼已輪替。為避免新明文出現在 Git、部署日誌、對話或交接文件，正式擁有者需在可信任終端執行產生器，把明文直接保存到密碼管理器，再將 verifier 設入 Render `ADMIN_PASSWORD_HASH`。新密碼驗收成功後移除 `ADMIN_PASSWORD`。在此之前後台會以安全稽核警示顯示「待設定」。

## 下一階段

密碼無法抵抗釣魚、瀏覽器惡意外掛或已入侵裝置。若要再高一級，應新增 Passkey／硬體安全金鑰作為管理員第二因素，而不是繼續把密碼延長到 100 位。
