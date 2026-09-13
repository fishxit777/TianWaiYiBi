# V32 後續修正｜LINE 摘要 PostgreSQL 500 與排程驗收

日期：2026-09-13。使用者確認「不新增按鈕，但一定要有推播」，並回報今天未收到、最後一則為昨日22:26。本文件是V32後續修復證據；正式補送與本人收訊尚待本輪部署後追加，不先宣稱完成。

## 已確認原因

- GitHub `Daily admin summary`第63次排程，來源提交`3f8c1d9`，今日12:28（台北）觸發；通知步驟於12:40三次收到HTTP500而失敗。
- Render正式日誌確認psycopg參數佔位符錯誤，`%:`不合法，與全新PostgreSQL17.11完整路由測試的失敗一致。
- `retry_private_alerts()`將`LIKE '%:daily-summary:%'`字面百分號與psycopg綁定參數混用。錯誤發生於摘要建立及LINE呼叫之前，不是已證實的權杖失效，也不是使用者設定錯誤。
- 前一輪真PostgreSQL測試只涵蓋佇列認領等個別路徑，沒有跑完整摘要路由，導致此回歸漏檢。先前本機通過不等於正式推播完成，這次補上缺失測試。

## 本次修改

1. 兩段重試SQL的LIKE／NOT LIKE模式改用綁定參數，不改adapter、schema、通知配額、重試政策或資料。
2. 真PostgreSQL回歸完整執行摘要路由兩次，驗證回200、LINE模擬接受且同時段只送一次。
3. 既有三時段工作新增回應驗證器；只有合法時段、合理佇列／去重數及`channels.line=sent`才通過。`failed`、`pending`、`skipped`、無效JSON、錯誤編碼、過大／過深回應皆失敗。只輸出固定狀態及白名單統計，不輸出原始HTTP本文、憑證或收件資料。
4. curl保留失敗傳遞、不跟隨轉址；驗證器由本repo的鎖定版本checkout取得，停用憑證持久保存。憑證僅提供給請求步驟，沒有讀取／复制其值。

## 保持不變

- 不新增測試按鈕、客服、客戶聊天、公開入口、排程或其他通知服務。
- 既有目標時段仍是台北08:00／12:00／20:00，高／重大事件仍走私人LINE即時告警。
- 官網圖文／外觀、13案內部價格與公開收款關閉狀態不變；萬語通沒有任何修改或同步。
- 已確認Render免費方案無Shell，不升級、不付款、不藉機取得機密。改用既有工作流程核對與補送正常摘要。
- 正常摘要端點會沿用既有最多10筆近期佇列重試；不是新造一則假攻擊，也不全量重送歷史告警。

## 自我驗收循環

- 第一輪：新PostgreSQL完整路由測試重現失敗，5 passed／1 failed；JSON驗證器測試先因尚未實作失敗。
- 第二輪：窄SQL修復後，全新PostgreSQL6 passed；回應驗證測試通過。獨立複查發現重試統計欄位名與極深JSON例外需修正，均已補齊。
- 第三輪：一般全套266 passed、6 skipped；六項跳過者已於全新PostgreSQL17.11另行全過。驗證器26項再次通過；Python編譯及diff檢查通過。隔離PostgreSQL已停止，未連正式DB、未消耗復原碼或試刷。

## 正式驗收待追加

- 等待本次修正部署及精確提交核對後，使用既有摘要工作處理今天失敗的時段；保留日期／時段去重，不更換新識別值強制重送。
- 工作綠勾搭配`new_summary_api_accepted`才可證明本次新摘要被LINE接受；`summary_previously_api_accepted`只表示該時段先前接受，不能當本次新投遞或手機收到。
- 手機實際收訊仍須本人確認，只需收到與時間，不需要貼訊息全文或含私人資料的截圖。
- GitHub排程可能排隊延遲；08／12／20是設定時段，不是準點送達保證。昨日22:26收到不能反推設定為22:26。

## 技術依據

- [psycopg參數與百分號規則](https://www.psycopg.org/psycopg3/docs/basic/params.html)：模式作為綁定值傳送，避免SQL文字中的百分號被解析為佔位符。
- [GitHub schedule限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)：排程可因負載延遲，不承諾精確牆鐘送達。
