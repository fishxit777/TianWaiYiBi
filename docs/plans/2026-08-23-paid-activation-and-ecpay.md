# 付款後開通與綠界介接實作紀錄

## 目標

付款成功前不能取得付費內容；付款後以 Email、一次性開通碼與短效重新登入碼完成交付，同時保留客戶已購權益。

## 已完成

- 付款前明確告知彈窗與雙重同意紀錄。
- 付款成功提示彈窗與專屬開通頁。
- 12 位首次開通碼：24 小時、單次使用、5 次嘗試上限。
- 12 位重新登入碼：7 分鐘、單次使用、可重新申請。
- 30 天 HttpOnly 客戶 session 與已購內容庫。
- SMTP 交易信介面與本機安全預覽 outbox。
- 綠界 AioCheckOut V5 表單、CheckMacValue、ReturnURL、OrderResultURL、金額核對及冪等處理。
- 正式綠界啟用閘門，避免缺少 Email、HTTPS 回呼或人工確認時意外收款。
- 桌機與 390 × 844 手機版流程驗收。

## 正式上線前仍需

1. 綠界正式 MerchantID、HashKey、HashIV。
2. SMTP 寄信帳號、寄件網域與實際收信測試。
3. PostgreSQL 或 Render 持久化磁碟與備份。
4. 退款後撤銷權益、電子發票與客服補單 SOP。
5. 綠界 stage 實刷測試、ReturnURL 重送測試與正式小額驗收。
