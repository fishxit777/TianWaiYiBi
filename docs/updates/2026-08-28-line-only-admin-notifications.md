# 管理推播 LINE Bot 化更新紀錄

日期：2026-08-28

## 目的

管理員不再同時收到 Gmail 與 LINE 的重複營運通知。管理推播統一由天外一筆
LINE Bot 傳送；客戶付款、開通及登入所需的交易 Email 完整保留。

## 已實作

- 台北時間 08:00、12:00、20:00 三次摘要維持不變。
- 每個固定摘要只建立一筆 LINE 佇列，不再建立管理 Gmail 佇列。
- 高／重大風險、付款與 LINE 驗簽異常、客戶交易郵件失敗仍立即推送 LINE。
- 相同日期／時段／事件的防重送鍵維持有效。
- 舊管理 Gmail 佇列保留供稽核，但自動與人工批次重試都只處理 LINE。
- 今日管理通知失敗／略過只計算 LINE；舊 Gmail 失敗不再冒充今日待辦。
- 後台「系統串接」與「安全稽核」改為 LINE 管理推播就緒狀態，Email 卡只代表
  客戶交易郵件。
- Render Blueprint 不再要求 `ADMIN_ALERT_EMAIL`；GitHub Actions 工作流名稱改為
  LINE summary，排程仍固定三次。
- 健康版本更新為 `line-admin-notifications-v3`。

## 不變的安全邊界

- LINE 訊息仍遮罩客戶 Email／IP，並移除驗證碼、Token、Cookie、密碼與簽章值。
- 客戶交易 Email 仍由既有寄送服務處理；管理推播切換不會中斷付款交付與登入。
- 舊通知資料不刪除、不竄改，避免破壞稽核證據。
- 公開 NT$199 收款維持關閉；本次不建立訂單、不動正式客戶權限、不使用復原碼，
  也不撤銷 Passkey。

## 驗證

- 通知、風險與健康專項：24 passed。
- 全套：167 passed、1 skipped；skipped 只在 PostgreSQL 17 CI 執行。
- Python compileall、全部 JavaScript syntax、`pip check`、`git diff --check`、三時段
  排程檢查與不回印內容的新增行機密掃描均通過。
- 正式部署狀態另記於 `HANDOFF.md`。
