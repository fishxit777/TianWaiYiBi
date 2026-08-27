# 管理員每日摘要與即時雙通道告警更新紀錄

日期：2026-08-23  
版本：`admin-notifications-v1`

## 完成內容

1. 建立兩條獨立通知線：每日營運摘要與即時異常告警。
2. 每日摘要固定在台北時間 08:00、12:00、20:00 由 GitHub Actions 觸發。
3. 高／重大存取事件會立即同時建立 LINE 與 Gmail 通知，不等待每日摘要。
4. 高／重大一般安全事件（管理登入封鎖、敏感路徑掃描、LINE／付款簽章錯誤、金額不符等）接入同一即時通知流程。
5. 客戶開通信、登入碼信等交易郵件寄送失敗時，立即建立管理告警。
6. Gmail 告警本身寄送失敗時不再衍生下一層 Gmail 告警，避免無限遞迴；LINE 仍可獨立送達。
7. 原本只支援 LINE 的 `notification_queue` 改為 LINE／Gmail 共用佇列，每個通道分別保存收件人遮罩、狀態、嘗試次數、失敗原因與送達時間。
8. 原有後台「重試未送達」功能已擴充為同時重試 LINE 與 Gmail。
9. 每個事件及每日日期／時段／通道都有唯一防重送鍵；排程重試或手動重跑不會建立重複通知。
10. 排程端點只接受 POST、固定三種時段，並使用至少 32 字元獨立密鑰及常數時間比對；驗證失敗統一回 404，避免暴露內部端點資訊。
11. 每日摘要包含訂單與營收、付款狀態、瀏覽與熱門仙策、開通與存取、活躍工作階段、可信裝置、未結風險案件、封鎖、證據鏈、整合狀態、通知／交易信失敗、需要處理及正常但值得知道。
12. 即時告警包含白話事件名稱、嚴重度、台北時間、事件／案件編號、匿名客戶代碼、風險分數、遮罩 IP、路徑、系統動作與建議處置。
13. 外部通知集中清理完整 Email、完整 IP、驗證碼、Token、Cookie、密碼、Authorization 與簽章值；完整紀錄只留在受保護後台。
14. 管理員收件 Gmail 使用獨立 `ADMIN_ALERT_EMAIL`，不會從訂單或客戶 Email 推論。
15. 後台「系統串接」新增管理員通知卡，顯示 LINE、Gmail 與每日摘要排程是否完整就緒。
16. 後台「安全旗標」新增管理員 Gmail 告警與每日三次營運摘要狀態。
17. 後台通知佇列標題改為 LINE＋Gmail，並區分「營運摘要」與「即時告警」。
18. Render Blueprint 新增 `ADMIN_ALERT_EMAIL` 與 `NOTIFICATION_CRON_SECRET` 私密變數宣告。
19. 新增 GitHub Actions 手動觸發選項，可選晨間、午間或晚間摘要做實際收件驗收。
20. 健康檢查版本更新為 `admin-notifications-v1`，便於確認正式部署。

## 排程與送達規則

- 晨間：08:00 Asia/Taipei（00:00 UTC）
- 午間：12:00 Asia/Taipei（04:00 UTC）
- 晚間：20:00 Asia/Taipei（12:00 UTC）
- GitHub Actions 排程可能因平台佇列延後數分鐘，通知內容會標示實際產生時間。
- LINE 與 Gmail 個別送出；其中一個失敗，另一個不受影響。
- 失敗或未設定會留在後台佇列；2026-08-28 起只允許重試仍有時效的近期通知，不會洪水式重送舊摘要。

## 驗證

- 排程端點未帶密鑰／錯誤密鑰：404。
- 正確密鑰與合法時段：建立 LINE、Gmail 各一筆。
- 同日期、同時段重跑：兩通道均防重送。
- 高風險存取事件：建立兩通道通知，含事件編號與遮罩 IP。
- 高風險一般安全事件：建立兩通道通知，敏感 detail 已清理。
- 交易郵件失敗：LINE 告警仍能送出，Gmail 失敗不產生遞迴佇列。
- Python compileall：通過。
- JavaScript syntax check：通過。
- `pip check`：無相依問題。
- pytest：58 passed。
- 正式 Render：commit `197740d` 已上線，`/healthz` 回傳 `release=admin-notifications-v1`。
- 正式安全檢查：官網與後台登入回 200；未帶排程密鑰的 POST 回 404；後台登入維持 `no-store` 與 `X-Frame-Options: DENY`；公開頁沒有後台或內部排程連結。
- GitHub Actions：`Daily admin summary` workflow 已被 GitHub 正確載入，沒有 invalid workflow。

## 正式環境仍需驗收的外部設定

下列值只存在外部平台，不得寫入 Git：

- Render：`ADMIN_ALERT_EMAIL`
- Render：SMTP 全組設定
- Render：天外一筆專屬 `LINE_ADMIN_USER_ID` 與 Messaging API Token
- Render：`NOTIFICATION_CRON_SECRET`
- GitHub Actions Secret：同值的 `NOTIFICATION_CRON_SECRET`

設定完成後手動執行一次 workflow，確認本人 LINE 與 Gmail 均收到相同時段摘要，再於後台檢查兩筆佇列狀態為 `sent`。

2026-08-23 正式部署後只核對變數名稱、不讀取密鑰值：首次檢查時 Render 尚未出現管理員通知設定，GitHub Actions 也尚未建立排程密鑰。

取得當下同意後已完成：

- Render 新增管理員收件地址與 64 字元獨立 `NOTIFICATION_CRON_SECRET`，密鑰未顯示於對話、終端或 Git。
- GitHub Actions 新增同值加密 Secret。
- 正式受保護端點回 200，建立 LINE／Gmail 各一筆佇列。
- `Daily admin summary #1` 手動執行成功，證明 GitHub 排程、兩端密鑰與正式端點已接通。
- 首次驗收當時 Gmail 因寄送服務尚未設定而回報 `failed`；LINE 因 `LINE_ADMIN_USER_ID` 尚未設定而回報 `skipped`。沒有誤送，也沒有沿用萬語通或其他專案收件人；後續 Gmail 已由 Brevo 實際送達，LINE 私訊仍待設定。

## 2026-08-28 訊號品質 V2

- 管理 Gmail 摘要已透過正式 Brevo 寄送服務實際送達；信件抵達本身證明本次 Gmail 通道可用。
- 原「未送達管理通知」會累計全部歷史 `failed`／`skipped`，現已拆成今日失敗、今日略過及歷史稽核存量。只有今日真正失敗會列入需要處理。
- 歷史紀錄不刪除、不改寫；摘要明示保留供稽核，且不自動重送。
- 每日摘要最多重試 24 小時內資料，其他管理通知最多重試 7 天內資料；缺少收件設定的通道會延後，不會反覆增加嘗試次數。
- LINE 狀態拆成官方帳號頻道與管理員私訊收件人。正式 webhook 已連線不再被誤寫成整個 LINE 故障；目前仍只缺天外一筆專屬 `LINE_ADMIN_USER_ID`。
- 金流狀態拆成公開開放、安全關閉及設定缺失。已驗收的綠界設定加上關閉的公開閘門會顯示「公開收款關閉」，不列異常；NT$199 維持關閉。
- 流量改為不重複真人工作階段，排除機器及 `admin-preview`，首頁與仙策詳情分列；熱門仙策未達 10 位時明示樣本不足。
- 本機驗證：159 passed、1 skipped；Python、JavaScript、套件、差異格式與新增行機密掃描全部通過。
- 正式部署：提交 `8bd3b3d` 的 `/healthz` 回報 `admin-summary-signal-v2`；首頁仍為摘要模式且沒有結帳入口。部署驗收未觸發摘要、通知重試、訂單或任何正式資料寫入。
