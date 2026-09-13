# V32 後續修正｜LINE 摘要 PostgreSQL 500 與排程驗收

日期：2026-09-13。使用者確認「不新增按鈕，但一定要有推播」，並回報今天未收到、最後一則為昨日22:26。本文件是V32後續修復證據；同提交重新部署後，正式新摘要已取得LINE API接受證據，手機收訊仍待本人確認。

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
- 第三輪：一般全套266 passed、6 skipped；六項跳過者已於全新PostgreSQL17.11另行全過。驗證器26項再次通過；Python編譯及diff檢查通過。隔離PostgreSQL已停止，未連正式DB、未消耗復原碼或試刷。但本輪首次正式補送仍500，因此「正式LINE接受／本人收訊」不得判為通過；下述部署排查與後續結果分開記錄，不把本機通過充作整體驗收完成。

## 正式首次補送與部署落差

- 修復提交`73cb03f`已push，Render首次建置日誌確認checkout此提交，13:23:10（台北）顯示Live。
- GitHub既有工作第64次、run `34740342892`使用同提交與`morning`，13:27仍三次HTTP500；新驗證器輸出固定`invalid_json`且工作失敗，沒有假綠勾，也沒有證據表示此時已呼叫LINE。
- 最新錯誤仍是同一`%:`例外，堆疊在舊版`notifications.py:715`；修正版該execute已移到716。日誌錯誤實例標記與首次新版啟動標記不同。這支持「執行程序／日誌版本不一致」的判斷，但尚不把平台內部原因當成已證實。
- 只讀核對repo沒有追蹤pyc或自訂舊程式載入流程，遠端main也確為`73cb03f`。未因此再改SQL；使用同服務既有Deploy latest commit重新部署同一提交，不清資料／快取、不升級方案。
- 首次部署後只讀正式檢查：health200／V32、13卷公開頁與關閉收款頁200、0收款表單、0付費網址外露；75個退役圖址及3個未授權新入口皆404。這些不代表通知已送達。

## 同版本重新部署與正式推播結果

- 使用同服務既有Deploy latest commit重新部署`73cb03f`，13:37:00（台北）顯示Live；本次沒有新增任何程式修改、改設定或清資料。
- 重試原GitHub第64次工作的失敗job，不建立新日期／時段、不啟用debug logging。第二次attempt成功，job `103680008222`，全工作11秒；通知步驟7秒。
- 固定白名單結果：`result=new_summary_api_accepted`、`slot=morning`、`queued=1`、`deduplicated=0`、`line_status=sent`。這是本次新摘要被LINE API接受的證據，不是僅有GitHub綠勾。
- 重試統計：processed=0、sent=0、deferred_unconfigured=0、ignored_stale=17、ignored_legacy_email=11。沒有補送過期通知／舊Email；只新送本時段一則摘要。
- 重新部署後正式health再次200、status=ok、release=independent-content-security-v32。release沿用V32，精確程式提交必須搭配Render checkout／Live紀錄核對。
- 「重新部署相同提交後恢復」支持前次程序版本落差的判斷，但沒有平台內部調查證據，仍不宣稱已證明其底層原因。
- [GitHub摘要第64次](https://github.com/fishxit777/TianWaiYiBi/actions/runs/34740342892)保留首次失敗及第二次成功證據。
- 手機實際收訊仍須本人確認，只需收到與時間，不需要貼訊息全文或含私人資料的截圖。
- GitHub排程可能排隊延遲；08／12／20是設定時段，不是準點送達保證。昨日22:26收到不能反推設定為22:26。

## 三條合格標準結論

1. **部分通過／手機收訊待確認**：真PostgreSQL完整路由與去重通過；正式新摘要取得LINE API接受證據。不能將API接受等同手機實際收到，也不把一般摘要成功當成新版高風險事件正式推播的獨立驗收。
2. **通過**：失敗／略過／待送／格式錯誤的回應不會假綠；正式首次500確實紅燈，第二次只有line=sent的新摘要通過，日誌僅固定欄位。
3. **通過**：無新增按鈕／排程／服務，無修改萬語通，13案內部價格、官網外觀與公開收款關閉狀態不變；未觸及正式付款、退刷、復原碼或其他破壞性測試。

## 技術依據

- [psycopg參數與百分號規則](https://www.psycopg.org/psycopg3/docs/basic/params.html)：模式作為綁定值傳送，避免SQL文字中的百分號被解析為佔位符。
- [GitHub schedule限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)：排程可因負載延遲，不承諾精確牆鐘送達。
