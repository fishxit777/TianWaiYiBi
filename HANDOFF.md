# 天外一筆・仙策閣交接

更新：2026-08-23

## 目前狀態

本機初版已 commit 並推送至獨立私人 GitHub 儲存庫，Render 免費 HTTPS 服務與 LINE Messaging API 已完成接線。

已完成：

- Flask 應用工廠與 SQLite 自動建表／種子資料。
- V13 修仙品牌響應式官網、六個原創想法商品、深淺 Logo、透明 Logo、favicon 與 LINE 圓形頭像。
- 統一價格設定、訂單成交價快照、專屬內容連結。
- 本機模擬付款、HMAC webhook、事件冪等與金額核對。
- LINE webhook 簽章、防重送、好友加入、文字指令、六脈 Flex Carousel 與共用訊息模型的本機模擬器。
- 管理後台登入、server-side session、CSRF、全站／單品價格、仙策完整內容編輯、排序、上下架、訂單、營收、流量來源、串接狀態、安全事件、封鎖與稽核。
- 敏感路徑防護、安全標頭、管理登入失敗暫時封鎖。
- 核准的 V13 修仙 Logo 已套用官網、LINE 模擬器與後台，並有深淺背景與圓形裁切評估頁。
- 自動測試、Python 語法檢查與 JavaScript 語法檢查。
- Render Blueprint、Gunicorn 啟動命令、可設定資料庫路徑與依公開請求自動產生 LINE 卡片連結。
- 獨立 LINE 官方帳號：`天外一筆｜仙策靈使`，Basic ID `@279plitu`。
- GitHub 私人儲存庫：`fishxit777/TianWaiYiBi`，`main` 由 Render Blueprint 自動部署。
- 正式官網：`https://tianwai-yibi.onrender.com/`；健康檢查、官網與管理登入頁皆回 200。
- 正式 webhook：`https://tianwai-yibi.onrender.com/line/webhook`，LINE 驗證成功並已啟用。
- LINE Provider：`天外一筆工作室`；長期 Access Token 與 Channel Secret 僅存在 Render 環境變數。
- LINE V13 頭像、狀態消息與官網連結已公開；內建歡迎訊息與自動回應已關閉。
- 公開官網已移除 Logo 審稿、管理後台與本機模擬器連結，改以「仙閣心訣」補足品牌理念，並以「傳音閣」連到真人守閣者客服。
- `/transmission` 已重製為「九霄月壇・朱砂傳音詔」V2：全頁統一楷書／書法字系，加入滿月、雲海、浮峰、八方卦位、朱砂符線、三息入閣與守閣安全誓約；桌機掃描原始高對比 QR，手機才直接開啟 LINE 官方帳號。
- V14 已依使用者指定的仙俠小說封面重新建立三張專屬題字：導覽列「天外一筆」、首頁「一筆開天／靈感成案」、傳音頁「一筆啟月門／一念渡靈音」。導覽列法筆印放大至 72px；全站收斂為品牌、主視覺、區段／頁面與卡片四級，不再讓每個 H1／H2 都套七層立體效果。
- 三張 V14 題字已壓成 WebP（各自低於 650 KB）；首頁題字使用 luminance mask 與九霄背景無縫融合，語意標題與替代文字仍保留。
- `run_local.ps1` 的亂數十六進位產生方式已改為 Windows PowerShell 5.1 可用的 `BitConverter`，可重新直接啟動本機服務。
- V14.1 已完成公開站清晰字級修正：正文基準提高至桌機 18px／手機 17px，主要說明 19px，導覽與卷標 13–15px；LOGO 英文副標改為清楚的粗體英文襯線字，桌機 12px，手機 10–10.5px 且不再隱藏。後台與開發工具維持原密度。

## 驗證結果

- `python -m py_compile ...`：通過。
- `node --check static\app.js`：通過。
- `node --check static\admin.js`：通過。
- `python -m pytest -q`：33 passed，0 failed。
- `python -m pip check`：No broken requirements found。
- 新建本機資料庫：6 筆仙策、0 筆訂單；`orders` 只有 `access_token_hash`，沒有明文 `access_token` 欄位。
- 桌機瀏覽器：V13 官網、分類篩選、商品詳情、建單、模擬付款、內容解鎖、Logo 評估、LINE 六張卡片、後台登入、KPI、串接狀態與內容編輯器均通過。
- 手機 390 × 844：官網、V13 主視覺、LINE 模擬器、後台與內容編輯 dialog 都沒有根頁面水平溢位。
- 傳音頁 V2：桌機 1440 × 960 與手機 390 × 844 已分段檢視；手機根頁面寬度 390／內容寬度 390，無水平溢位；導覽、題字、內文、按鈕與頁尾的 computed font 均為書法字系。
- V14 視覺 QA：桌機實看首頁頂部、六脈區與傳音頁；導覽列品牌組合約 304px 寬，首頁與傳音主標皆正確顯示專屬封面題字，首頁深藍矩形底已由 luminance mask 消除；其餘 H2／H3 已收斂為一致月金層級。
- V14.1 可讀性 QA：桌機 computed style 確認 LOGO 副標 12px／700、導覽 15px／700、首頁卷標 14px／700、首屏說明 19px；另以 390 × 844 真實 iframe viewport 實看首頁與傳音頁，副標、主標、正文與按鈕均完整顯示且沒有水平擠壓。
- 瀏覽器 console：0 error、0 warning。
- HTTP smoke：`/healthz`、`/` 回 200；`/logo-review` 與正式環境 `/dev/line` 回 404；健康狀態為 `ok`。

瀏覽器驗收使用的假訂單與假 Email 已從正式本機資料庫清除；可復原 QA 副本暫存於 Windows Temp，不屬專案交付資料。

## 入口

- `/`：官網與六脈仙策
- `/transmission`：自有修仙傳音頁與官方加好友 QR 法印
- `/ideas/<slug>`：免費摘要
- `/checkout/<slug>`：建立訂單
- `/pay/mock/<token>`：本機模擬付款
- `/orders/<access_token>`：付費內容
- `/dev/line`：LINE Bot 模擬器
- `/line/webhook`：正式 LINE webhook 入口
- `/payments/webhook/mock`：支付 webhook 範例
- `/admin`：管理後台

`/dev/line` 與 `/admin` 為非公開營運入口，不得從公開頁面連結；Logo 評估路由已撤除。

## 下一個最高 ROI 決策

先讓 10～20 位目標客戶看六脈仙策，記錄哪一脈被點擊、哪一脈進入結帳，以及客戶是否願意為「想法＋模板」付款。若沒有付費訊號，不應先投入正式支付、會員系統或更多角色。

需求有訊號後，建議依序：

1. 用目前 V13 與六脈頁面做 10～20 人需求驗證，選出首發 1～2 個仙策。
2. 把首發仙策內容補強到正式可交付品質，定案價格、退款、授權與電子發票規則。
3. 為既有的獨立 LINE 官方帳號啟用 Messaging API，部署公開 HTTPS，填入本專案自己的 Channel Secret／Access Token。
4. 選擇綠界或 LINE Pay，使用獨立商店資料與正式 webhook 驗收。
5. 正式公開前換 PostgreSQL，加入備份、監控、WAF、管理員 2FA 與部署檢查。

## 禁止混用

不得沿用萬語通的 LINE token、管理員 LINE ID、資料庫、支付商店資料、Render 服務或網域。也不得把本專案併入辰新數位、SoundBank、NOWELYO 或其他專案目錄。
