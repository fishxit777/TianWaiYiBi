# 天外一筆 V13 初版系統設計

日期：2026-08-22

## 結論

本階段維持 Flask 模組化單體與 SQLite，不改成微服務，也不先導入外部 SaaS。現有骨架已能完成商品瀏覽、下單、模擬付款、內容解鎖、LINE webhook 與後台登入；最高 ROI 是補齊品牌一致性、LINE 導購訊息與每項仙策的內容管理能力。

## 需求與限制

- 官網：套用已核准的 V13 無字 Logo、深淺背景版本與仙氣飄逸主視覺；六個想法維持獨立技能與統一試行價。
- LINE Bot：保留原始 webhook 簽章驗證與事件防重送，增加歡迎、目錄、價格、編號與說明等可直接導購的訊息。
- 後台：管理全站價格、每項仙策內容、上下架、訂單、營收、安全事件與稽核紀錄。
- 金流：本機版只提供 mock adapter，不冒充正式金流；成交金額保存於訂單快照。
- 安全：伺服器端管理 Session、CSRF、登入限速、IP 封鎖、參數化 SQL、敏感路徑攔截、安全標頭與稽核紀錄。
- 本機優先：不需要 LINE、銀行或雲端憑證即可完成驗收；正式整合留在 adapter 邊界。

## 架構

```text
瀏覽器 / LINE Platform
        |
        v
Flask application factory
  |-- public blueprint    官網、商品、下單、內容交付
  |-- line blueprint      webhook、Flex/Text 組裝、本機模擬器
  |-- payments blueprint  mock payment、簽章 webhook、冪等處理
  |-- admin blueprint     登入、內容管理、訂單/分析/安全資料
  |-- security layer      CSRF、Session、限速、IP、Headers、Audit
        |
        v
SQLite（本機 MVP）
  ideas / orders / events / sessions / security / audit
```

## 關鍵資料流

1. 訪客在官網或 LINE 目錄選擇仙策。
2. 官網顯示公開摘要，結帳時由伺服器重新查價並建立訂單快照。
3. mock payment 或未來正式 provider webhook 驗簽後，使用 event id 防止重複入帳。
4. 付款完成後使用雜湊保存的專屬 token 解鎖內容。
5. 後台所有異動需有效管理 Session 與 CSRF，並寫入 audit log。

## 重要決策

- 採模組化單體：單人維護成本低，現有測試與資料可直接沿用；目前流量與團隊規模不支持微服務複雜度。
- 保留 SQLite：本機初版足夠，並以 adapter 與 SQL 邊界保留日後遷移 PostgreSQL 的路徑。
- LINE 目錄使用 Flex carousel、其他回答使用 text：兼顧辨識、導購與維護，且每次 reply 維持在官方上限內。
- 不做真正會員系統：目前沒有足夠需求證據，專屬 token 交付先驗證付款與內容價值。
- 後台先做完整欄位編輯，不做自由排版 CMS：降低 XSS 與內容結構失控風險。

## 失敗模式與控制

| 風險 | 控制 |
| --- | --- |
| 偽造 LINE webhook | 對原始 body 做 HMAC-SHA256 驗簽後才解析 |
| 重送 LINE 或金流事件 | 事件 id 唯一索引與冪等回應 |
| 後台帳密暴力嘗試 | 時窗計數、暫時封鎖、通用錯誤訊息 |
| CSRF 或 Session 竊用 | 雙層 CSRF、伺服器 Session、HttpOnly/Strict cookie、可選 IP 綁定 |
| 訂單被改價 | 價格只由伺服器查詢，成交額寫入訂單快照 |
| 內容輸入造成 XSS | Jinja 預設 escaping、純文字欄位、白名單與長度限制 |
| 本機被誤認正式服務 | 全站與付款頁明示 mock；後台顯示整合狀態 |

## 後續才做

正式公開 HTTPS、LINE Developers 憑證、正式金流、電子發票、退款、Email 交付、PostgreSQL、備份與監控都屬下一階段；需要外部帳號或商業條件確認後再接入。
