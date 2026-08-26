# 天外一筆・仙策閣交接

更新：2026-08-27

## 目前狀態

本機初版已 commit 並推送至獨立私人 GitHub 儲存庫，Render 免費 HTTPS 服務與 LINE Messaging API 已完成接線。

2026-08-23 免費 PostgreSQL＋Passkey 安全升級已合併至 `main`，Render 正式站已切換至 Neon PostgreSQL。Cloudflare Turnstile、兩把實機 Passkey、10 組一次性復原碼、緊急復原入口與 Passkey 專用模式均已正式啟用。2026-08-24 已完成 RSA-4096／AES-256-GCM 加密異地備份接線與 PostgreSQL 17.11 實際還原：GitHub 只保存加密 Artifact，正式來源與還原端 24 張表、164 筆，逐表筆數與 SHA-256 全部一致。現在可以如實標示資料庫災難復原演練已完成；這不代表已執行會撤銷 Passkey 的管理帳號復原。

2026-08-26 已完成單筆 NT$6 正式金流閉環驗收：綠界付款、Brevo 交易信、一次性開通與付費內容讀取均成功，綠界結算後完成全額退刷，正式站再撤銷該筆驗收權限並實測原付費內容不可讀。NT$6 驗收入口已關閉，公開 NT$199 正式收款仍維持關閉；本次未消耗復原碼，也未撤銷兩把管理 Passkey。

2026-08-27 已完成「仙策需求雷達 V1」：六策詳情、閱讀、匿名意願、傳音與交易訊號已接成可稽核漏斗；同一匿名工作階段去重，機器與後台預覽排除，7／30／90 日固定觀察窗與樣本信心門檻均已落地。少於 10 人不下結論，10～29 人只標探索、不顯示精確排名，至少 30 人才允許方向排序；正式收款關閉時不會用零付款誤判商品失敗。

已完成：

- Flask 應用工廠與 SQLite 自動建表／種子資料。
- V13 修仙品牌響應式官網、六個原創想法商品、深淺 Logo、透明 Logo、favicon 與 LINE 圓形頭像。
- 統一價格設定、訂單成交價快照、專屬內容連結。
- 本機模擬付款、HMAC webhook、事件冪等與金額核對。
- 付款前明確告知彈窗、雙重同意版本與稽核紀錄；付款後成功彈窗改用清楚的消費者文字。
- 付款成功後才寄送專屬開通連結與 12 位一次性開通碼；首次開通與重新登入碼均為 10 分鐘、一次性、最多嘗試 5 次，失效不會刪除已付款權益。
- 每位客戶最多 2 台 30 天可信裝置；第三台驗證成功會淘汰最久未使用裝置。任何時間只有 1 個有效內容工作階段，新登入自動撤銷舊工作階段。
- 客戶 session 採 7 天絕對期限、24 小時閒置期限、HttpOnly Cookie；付費頁含匿名客戶代碼、訂單尾碼與時間浮水印。
- 低／中／高／重大四級風險、已撤銷工作階段重播偵測、HMAC 防竄改證據鏈、風險案件與告警佇列均已完成；正常換機只列中度，不直接當成惡意。
- 高／重大事件才私下推播管理員 LINE；訊息不含完整 Email、IP、驗證碼或 token。後台可撤銷裝置、更新案件、重試告警並驗證證據鏈。
- 綠界 AioCheckOut V5 已完成表單轉送、官方 CheckMacValue 算法、ReturnURL／OrderResultURL、金額核對、防重送與正式啟用閘門；可沿用與 NestFM 相同的合法特店憑證，但固定使用 `TWYB` 訂單前綴及 `StoreID=TWYB` 隔離對帳與 callback。
- 交易信介面已完成；本機使用不外寄的 outbox 預覽，正式付款交付已改由本專案獨立 Brevo API 寄送並通過實際收信驗收。管理摘要 SMTP 屬另一條獨立通知通道。
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
- V15 已完成整站 20 點仙俠視覺稽核與改版：導覽改為全幅天幕，首頁首屏改成一幅無字九霄主景，標題、價值、CTA 與三道印記同屏；六脈改成不等寬卷冊編排，入世改成三境路徑，心訣改成開卷經文，LINE 收尾改成月壇傳音主行動。
- V15 新主景為原創無字 WebP（約 126 KB），左側保留標題安全區、右側集中朱砂神筆／飛劍、月金法陣、仙門、浮峰與青玉靈氣；不再把主視覺關在長方形卡片，也不會和 HTML 題字重複。
- V15 字級採「書法只負責品牌與大標、正文負責清楚閱讀」：桌機正文 18px，手機 16–17px，章標 36–58px，卡名 28–34px，互動元件至少 42–58px 高。
- V15.1 已補改首頁卷首三個遺留元素：灰色向下提示改為月金「續入下一卷」卷印；「卷一・擇法」改為大型朱砂印章；世界觀主標改為固定兩行金墨壓印與朱砂收筆，並加入錨點安全距離避免手機固定導覽遮住卷印。
- V15.2 已把仙閣心訣四欄文字分為深朱砂、深青玉、靛紫與沉月金四套屬性色；小標、主標、正文、頂線與淡印同步分色，底紙仍維持單一月白古卷，兼顧角色差異與閱讀對比。
- V16 官網已完成 20 點專業化：圖像題字保留但補上完整語意 H1；手機首屏不再被固定導覽遮住；三項摘要改成獨立三層資訊；六脈改成一致的桌機 3×2／平板 2 欄／手機 1 欄卡片，新增「適合解決」、篩選結果數與交易信任頁尾。390px 手機總頁高由基準 8280px 降至 7953px，且新增內容後仍無水平溢位。
- V16 後台已完成 20 點專業化：頂部改為麵包屑、正式站與同步時間；總覽縮短品牌主景並加入 KPI 狀態語意與骨架載入；訂單表格升級字級、sticky header、斑馬紋與 aria-pressed；客戶六項指標固定 6 欄／3＋3／2＋2＋2；安全旗標固定 3＋3；串接卡新增依狀態變化的下一步；撤銷裝置改為明確危險操作。
- V17 官網第二輪 20 點專業化已完成：新增手機章節導覽、長頁進度、目前章節、緊湊頁首與「已購取回」入口；付款狀態由伺服器真實決定，公開收款關閉時首頁與詳情不再出現結帳入口，六卡改為先看摘要。另加入適合／不適合判斷、可還原篩選網址、焦點安全、空狀態、麵包屑與正確頁尾信任文案。
- V17 後台第二輪 20 點專業化已完成：手機七個工作區完整單列顯示；儀表板具載入／成功／錯誤與中文斷線重試；KPI 可鍵盤導頁，訂單搜尋可清除；價格、上下架、裝置撤銷、解除封鎖、安全測試與留言審核均改用站內影響確認；編輯器具未儲存保護，傳音範圍即時說明，歷史付款驗收區降級收納，安全事件預設高風險優先。
- 管理通知 V1 已完成：台北時間 08:00／12:00／20:00 詳細營運摘要；高／重大登入、存取、付款、LINE 與系統事件立即分送管理員 LINE＋Gmail。兩通道個別佇列、個別重試、日期／時段防重送；通知會遮罩 Email／IP 並移除驗證碼、Token、Cookie、密碼及簽章值。
- 手機六脈卡片字型一致性已修正：字型子集建置補入 `tianwai/db.py` 與全部公開交易頁文案，Regular／Bold 皆重新輸出；角色名與技能分類統一 MasaFont Regular 14px，主標統一同系 Display，手機 29px。六脈共 83 個不同卡片漢字已驗證缺字 0，並加入版本參數避免 iPhone 延用舊快取。
- 管理員憑證 V2 已完成：本機與正式輪替工具可產生 32 bytes／43 位 Base64url／256-bit 密碼；伺服器支援 Argon2id（19 MiB、2 次、p=1）且 Hash 存在時禁止降級使用舊明文。後台安全稽核新增 Argon2id 狀態；正式新明文不得進 Git、文件或對話，需由擁有者在可信任終端產生並直接保存到密碼管理器後，再設定 Render `ADMIN_PASSWORD_HASH`、驗收並移除 `ADMIN_PASSWORD`。
- 管理員憑證本機交接 V2 已完成：`scripts/admin_credential_handoff.py` 以一次性 Windows 視窗顯示 43 位密碼；複製 Argon2id verifier 後視窗仍保持開啟，可在 Render 部署完成後再次複製真正登入密碼，直到正式登入成功才銷毀，避免密碼管理器未保存時鎖死。明文不寫入磁碟、終端、Git、LINE、Gmail 或 Chat。
- 客戶交易郵件寄送失敗已接入即時管理告警；管理 Gmail 故障時不會遞迴產生無限告警，LINE 仍獨立送達。後台已顯示雙通道、通知類型及每日排程就緒狀態。
- 免費 PostgreSQL 基礎完成：SQLite／PostgreSQL 雙後端、完整 PostgreSQL schema、additive migration、SQLite→PostgreSQL checksum 遷移／核對工具與 PostgreSQL 17 CI；健康回應不揭露後端或連線值。
- 管理 Passkey 完成：32-byte／五分鐘／一次性 WebAuthn challenge，精確 RP／HTTPS origin、user verification、兩把金鑰門檻、Passkey-only 登入、憑證盤點與最後一把撤銷保護。
- 公開管理入口已完成情報最小化：未登入畫面與直接載入資源只顯示中性身分驗證，不公開驗證技術、裝置種類、憑證數量、密碼模式或復原入口；authentication options 不再下發 credential ID 清單，舊公開路由回 404，challenge 起始請求限制為每 IP 每分鐘 10 次。登入後的完整安全管理能力不變。
- 緊急復原完成：10 組 128-bit 一次性碼只存 Argon2id；必須密碼＋復原碼＋Turnstile 全部正確。成功會撤銷全部舊 session／Passkey、即時告警，並限制只能重建兩把 Passkey。
- 免費加密異地備份與還原已完成：每日 `pg_dump` 先由 `pg_restore --list` 驗證，再以 AES-256-GCM 加密與離線 RSA-4096 公鑰包裝；GitHub 只上傳 14 天加密檔，單份 25 MB 上限。RSA 私鑰只在實體離線 USB，GitHub 已設定只讀備份連線與公鑰；正式 run `32696239051` 成功，Artifact 只有 `.twybenc`，PostgreSQL 17.11 隔離還原及 24 表／164 筆逐表 checksum 全數通過。
- Neon 最小權限收尾已完成：建立正式唯讀備份角色 `twyb_backup_ro` 後，已永久刪除未使用且不擁有任何資料庫的臨時角色 `twyb_backup`；production 分支只保留正式擁有者與唯讀備份角色。
- 卷二限定傳音 V2 已完成：全站只有「卷二・六脈仙策」的六個仙策詳情頁保留獨立傳音串；首頁卷首、卷一、卷二總區、卷三、卷四與卷五不再掛載留言元件，舊首頁卷別 API 亦回 404。舊資料列不物理刪除，但不再出現在公開讀寫或後台新回覆範圍。
- 卷二首頁新增分層活動提示：有已公開內容時顯示「已有傳音」，同一瀏覽器讀過後再出現新公開內容時顯示「新傳音」，已登入客戶收到自己的守閣者私密回覆時顯示「有新回覆」。沒有留言不顯示 0 或空人氣提示；卷二標題、桌機導覽與對應仙策卡片都使用文字加色點，不以顏色作為唯一資訊。
- 活動摘要 API 只回六個 slug、公開數量與最新訊息流水號；匿名訪客不會取得任何私密欄位。私密已讀狀態使用伺服器 HMAC 產生的 20 位匿名範圍隔離不同客戶，瀏覽器 localStorage 只保存 slug、範圍與流水號，不保存留言正文、Email、客戶 ID 或其他機密。
- 客戶公開身分只顯示由匿名客戶代碼穩定產生的 `同道・XXXX` 與固定識別色，不公開訂單姓名、Email 或內部客戶 ID。顏色只套在頭像、名稱與色條，正文維持高對比中性色；每則訊息仍有名稱與 `守閣者`、`同道`、`等待公開`、`指定給你` 等文字徽章。
- 後台「傳音對話」工作區只列出卷二六脈，可篩選待審核、私密、已公開與全部訊息，一鍵公開、隱藏或指定回覆；不物理刪除訊息，所有審核／回覆寫入 `audit_logs`。新客戶傳音的 LINE／Gmail 管理提醒不含客戶身分與正文；客戶回覆提醒信也只要求登入查看，不外送站內內容。
- 傳音防濫用已完成：2～800 字、純文字、前端只用 `textContent`、公開網址拒絕、CSRF、客戶狀態檢查、每 10 分鐘 5 則／每日 30 則限制、公開先審後發、私密與 API 全部 `no-store`。付款、登入、開通與安全頁面不放傳音元件。
- 卷二匿名公開傳音 V3 已完成：未登入訪客可在六個仙策詳情頁直接留下公開傳音，固定先進待審；私密傳音仍只限已驗證客戶。每名訪客顯示穩定的 `訪客・XXXXXX` 與「訪客」文字徽章，顏色只作輔助；同一訪客可看自己的待審內容，其他訪客在核准前看不到。
- 訪客防濫用不依賴公開身分：CSRF、Turnstile `public-conversation` action／hostname 伺服器驗證、蜜罐、2～500 字、網址／HTML 拒絕、每 10 分鐘 3 則與每日 10 則雙層限速。資料庫只保存由伺服器金鑰 HMAC 的訪客／來源雜湊，不保存原始訪客 Cookie；API 與後台回應也不回傳這兩個雜湊。後台可核准、隱藏及公開回覆訪客，但不能把訪客留言轉成私密回覆。
- 正式金流閉環已完成：獨立 NT$6 驗收訂單經正式綠界付款、Brevo 交付、一次性開通、內容讀取、全額退刷、本地權限撤回與內容封鎖全部通過。驗收訂單不計入一般營收、成交訂單或客戶權益指標；公開 NT$199 收款未開啟。
- 後台退款撤權確認已由瀏覽器原生 prompt 改為站內 dialog，保留完整驗證訂單編號、管理 session、CSRF 與伺服器端逐字核對；避免瀏覽器擴充控制原生提示時卡住，也不降低誤觸防線。
- 仙策需求雷達 V1 已完成：第一方匿名事件使用 HMAC 去重、版本化事件字典、粗粒度來源、機器／後台預覽排除與不重複工作階段；每策顯示閱讀、有效閱讀、匿名意願、傳音及收款開啟後的結帳／建單／付款漏斗，並公開信心、證據、限制與下一個驗證動作。完整設計與驗證見 `docs/updates/2026-08-27-demand-radar-v1.md`。
- 完整 40 點問題、影響與對應修正記錄於 `docs/updates/2026-08-23-public-admin-40-point-professionalization.md`；本次只改呈現層與互動狀態，沒有改動付款、開通、可信裝置、風險分級或資料庫規則。

## 驗證結果

- 2026-08-27 仙策需求雷達 V1 本機完整驗證：`python -m pytest -q` 為 149 passed、1 skipped；Python compileall、兩支 JavaScript syntax、`git diff --check` 通過。隔離資料庫驗證匿名意願去重、事件白名單、機器排除、信心門檻與收款關閉診斷；桌機 1280px 與手機 390×844 無根頁面水平溢位，7／30／90 日切換與匿名意願回饋成功，console 0 error／0 warning。QA 未操作正式客戶、訂單、留言、Passkey、復原碼或備份。
- 2026-08-27 V17 本機完整驗證：官網桌機 1521px 與手機 390×844、後台桌機 1521px 與手機 390×844 均無根頁面水平溢位；手機後台七個工作區逐一切換成功，官網付款關閉情境為 0 個結帳連結。全站價格確認、未儲存離開保護、服務斷線中文錯誤與重試均實際觸發；官網／後台 console 0 error。`python -m pytest -q` 為 145 passed、1 skipped。
- 2026-08-26 正式小額金流閉環：唯一 NT$6 驗收交易已完成付款、交易信、一次性開通、內容讀取與綠界全額退刷；後台正式資料顯示本地權限已撤回，撤權按鈕隱藏，直接讀取原付費內容網址會回到客戶登入且不顯示付費內容。NT$6 驗收入口已停用，公開 NT$199 收款維持關閉。
- 退款確認介面修正提交 `56283d8`：退款專項 9 passed；全套 `python -m pytest -q` 為 143 passed、1 skipped，Python compileall、全部 JavaScript `node --check`、`pip check`、新增行機密掃描與 `git diff --check` 均通過。
- 2026-08-24 卷二匿名公開傳音 V3：`python -m pytest -q` 為 127 passed、1 skipped；Python compileall、三支 JavaScript `node --check`、`pip check`、機密樣式掃描與 `git diff --check` 全部通過。舊 SQLite 留言表實際升級測試保留原資料；PostgreSQL 遷移以交易 advisory lock 防止 Gunicorn 多 worker 同時啟動競爭，正式資料庫升級結果另以部署健康檢查確認。
- V3 本機瀏覽器 QA：桌機與 390×844 手機均只在仙策詳情頁出現匿名公開留言；公開頁顯示先審說明、訪客 500 字上限與人機確認，手機使用窄版安全元件且沒有裁切。切換私密分頁後匿名表單隱藏，只顯示客戶登入入口；未送出任何正式留言，也未觸碰 Passkey、復原碼或備份。
- V3 已由提交 `77a5618` 推送並正式部署：`/healthz` 回 200、`status=ok`、`release=volume-two-anonymous-conversations-v3`，代表既有 Neon PostgreSQL 已成功完成新增欄位／約束遷移並啟動。正式首頁仍為 0 個完整留言元件與 6 個六策提示，仙策詳情為 1 個匿名留言區；Chrome 實看建立 1 個 Turnstile iframe，訪客表單上限 500 字。匿名 API 顯示訪客投稿已啟用、0 則正式公開留言、無訪客雜湊／私密欄位，舊首頁留言 API 維持 404。GitHub Actions `PostgreSQL integration` run `32736250964`（#1）在隔離 PostgreSQL 17 成功，耗時 33 秒、沒有 Artifact；唯一 annotation 是既有 action runtime 的 Node 20 淘汰維護提醒，不影響本次成功結果。驗收全程未送出假留言、未登入後台、未消耗復原碼、未變更 Passkey 或重跑備份。
- 2026-08-24 卷二限定傳音 V2：`python -m pytest -q` 為 121 passed、1 skipped；Python compileall、`node --check static/app.js`、`node --check static/conversations.js`、`node --check static/admin.js`、`pip check`、機密樣式掃描與 `git diff --check` 全部通過。
- 卷二 V2 本機瀏覽器 QA：桌機與 390×844 手機首頁均為 0 個完整留言元件、6 個仙策活動提示掛點；仙策詳情頁只有自己的 1 個完整傳音元件。實際以隔離假資料驗證「已有傳音 → 展開閱讀 → 新增公開內容 → 新傳音」狀態轉換；390px viewport 的 document scroll width 為 375px，沒有水平溢位，console 0 error／0 warning。隔離資料庫驗收後已刪除。
- 卷二 V2 已由提交 `f9f4c70` 推送並正式部署：`/healthz` 回 200、`status=ok`、`release=volume-two-conversations-v2`；正式首頁為 0 個完整留言元件與 6 個提示掛點，仙策詳情為 1 個獨立元件。匿名活動 API 回 6 個仙策、0 個私密欄位並帶 `no-store`；舊 `home-world` 傳音 API 回 404。正式公開訊息目前為 0，因此畫面不顯示虛假的「已有傳音」；煙霧測試未建立留言、未登入客戶、未消耗復原碼或變更 Passkey。
- 2026-08-24 分區混合傳音 V1：`python -m pytest -q` 為 120 passed、1 skipped；其中傳音／資料遷移專項 16 passed。Python compileall、`node --check static/conversations.js`、`node --check static/admin.js` 與 `git diff --check` 通過。
- 傳音權限驗收：匿名只能讀已公開訊息；待審訊息只讓投稿者本人看見；兩個客戶的私密訊息互不可見；管理核准、隱藏、公開回覆、私密指定回覆與 CSRF 均通過。外部管理通知未包含測試正文或 Email。
- 分區混合傳音 V1 的首頁六卷元件曾完成桌機與 390×844 QA，並由提交 `a38a8c2` 部署；該首頁呈現與首頁卷別 API 已由卷二限定傳音 V2 正式取代。V1 的匿名身分、先審後發、私密 SQL 所有權、速率限制與管理稽核底層仍保留在六個仙策詳情頁。
- V1 正式已登入後台曾完成 12 個區塊的只讀驗收；V2 已將後台允許選項收斂為六個仙策並由自動測試核對。V2 正式驗收未登入後台、未按下公開、隱藏或送出，避免為純範圍調整操作正式客戶資料。
- 免費 PostgreSQL＋Passkey 正式版：`python -m pytest -q` 為 103 passed、1 skipped；skipped 只在 PostgreSQL 17 CI 執行。Passkey／復原／加密備份專項、Python compile、JavaScript syntax、`pip check`、依賴稽核、機密掃描與 `git diff --check` 均通過。
- 2026-08-24 公開管理入口情報最小化後的最終本機驗證：`python -m pytest -q` 為 110 passed、1 skipped；`verify_postgres_backup_restore.py` 的直接 CLI 與 module invocation 均通過。
- PostgreSQL 17.11 隔離整合測試另以本機臨時資料庫實跑 1 passed：新 challenge IP／時間索引已實際建立，每分鐘上限在 PostgreSQL 後端同樣生效；測試叢集與日誌已刪除。
- 正式加密備份 run `32696239051`（#3）成功，提交 `cfc23e7`，Artifact `tianwai-yibi-postgres-32696239051-1` 的 GitHub 與本機 ZIP SHA-256 均為 `2C0D72C6ADC2789DB29BC40510B61C7E63C8F446E6428D342F30A326B2FBB303`；ZIP 只有一個 `TWYBPG01` 加密檔。
- PostgreSQL 17.11 隔離還原 `pg_restore` exit code 0、零診斷錯誤；正式來源與還原端均為 24 張表、164 筆，逐表筆數與 canonical SHA-256 全部一致。隔離叢集、明文 dump 與日誌已刪除，只保留加密 Artifact 與不含資料列的報告。
- SQLite→Neon 正式遷移完成：21 張資料表、111 筆資料，逐表筆數與 SHA-256 checksum 全數核對；切換後正式瀏覽資料持續寫入 Neon，證明站台不是只建立空資料庫。
- Render 正式部署已為 Live；`/healthz` 回 200，`release=free-postgres-passkey-v1`、`status=ok`，健康資訊不揭露資料庫連線或驗證機密。
- Cloudflare Turnstile 正式 widget 只允許 `tianwai-yibi.onrender.com`，Managed 模式、pre-clearance 關閉；`/admin/recovery` 回 200、widget 正常載入、console 無錯誤，頁面未洩漏 site secret、資料庫連線或管理密碼 verifier。
- 兩把實機金鑰已登記並存入 Neon：`Windows Hello（主要）` 與 `手機備援（第二把）`，兩者皆為可同步備援的 `multi_device` credential；正式資料庫確認 2 把為 active。
- 已產生 10 組一次性復原碼並由持有人下載保留一份；正式資料庫只保存 10 筆 Argon2id 雜湊，每組原碼 32 字元，重複下載的 `_1`、`_2` 副本已由持有人刪除。
- Passkey 專用模式正式啟用後，以未登入 HTTP 視角核對：登入頁回 200、一般密碼表單不存在、Passkey 登入按鈕存在、專用模式說明存在、緊急復原入口存在，且沒有公開任何環境機密。
- Windows Hello 實機重新登入通過：正式站先由已登入後台執行安全登出，確認落到 `/admin/login` 且只剩 Passkey；完成本人驗證後成功回到 `/admin`，今日總覽與正式 Neon 營運資料正常載入。
- `python -m py_compile ...`：通過。
- `node --check static\app.js`：通過。
- `node --check static\admin.js`：通過。
- `python -m pytest -q`：58 passed，0 failed。
- `python -m pip check`：No broken requirements found。
- 舊版 `data/tianwai.db` 副本原地升級：新增客戶、裝置、存取事件、風險案件與告警表，回填訂單 customer 關聯；`/healthz` 通過，沒有刪除或重建既有訂單。
- 本機瀏覽器完整操作：結帳告知 → 模擬付款 → 10 分鐘開通碼 → 付費內容；桌機與 390 × 844 均無水平溢位，浮水印 12 組且只含匿名客戶代碼、訂單尾碼與時間。
- 後台瀏覽器實看：可信裝置／單一 session 指標、遮罩網路資訊、存取事件、證據鏈與 LINE 佇列皆正確顯示；console 0 error、0 warning。
- 正式 Render 部署已驗證：實作 commit `0337e9e` 上線後 `/healthz` 回傳 `release=trusted-device-risk-v1`；官網、客戶登入、後台登入回 200，客戶／後台頁維持 no-store 與 frame deny，`/logo-review`、正式 `/dev/line` 維持 404。
- V16 正式 Render 部署已驗證：實作 commit `df2219a` 上線後 `/healthz` 回傳 `release=professional-ui-v16`；官網、`static/v16.css`、後台登入皆回 200，正式首頁含完整語意 H1 且沒有 `/admin` 公開連結；後台登入維持 `Cache-Control: no-store` 與 `X-Frame-Options: DENY`，`/logo-review`、正式 `/dev/line` 維持 404。
- V17 正式 Render 部署已驗證：實作 commit `94249a5` 上線後 `/healthz` 回傳 `release=professional-ui-v17`；正式首頁載入 `static/v17.css`、無根頁面水平溢位，公開收款關閉時維持 0 個結帳連結且六張卡全部顯示「先看摘要」。後台登入頁同樣載入 V17、沒有公開正式驗證器數量或裝置細節；驗收未登入正式後台、未建立訂單、未送出留言或修改正式資料。
- 管理通知 V1 正式 Render 部署已驗證：實作 commit `197740d` 上線後 `/healthz` 回傳 `release=admin-notifications-v1`；官網與後台登入回 200，未帶密鑰的摘要端點回 404，公開首頁沒有 `/admin` 或內部通知連結。GitHub 已正確載入 `Daily admin summary` workflow，沒有 invalid workflow；正式雙通道實際收件仍需先補 Render／GitHub 私密設定。
- 手機卡片字型修正已正式部署：實作 commit `4872bbe` 上線後 `/healthz` 回傳 `release=mobile-card-type-v1`；正式 390×844 首頁六張主標皆載入 `Tianwai Masa Display`，角色名與技能分類皆為 `Tianwai Masa` 14px，`商機觀星盤` 實看無混字、無水平溢位，console 0 error／0 warning。
- 管理員憑證 V2 已完成正式輪替：擁有者透過本機交接 V2 保存 43 位／256-bit 新密碼，正式登入成功後才銷毀本機明文；Render 現在只保留 `ADMIN_PASSWORD_HASH`，legacy `ADMIN_PASSWORD` 已刪除並再次部署為 Live。`/healthz` 回傳 `release=admin-credential-v2`，登入頁 200、no-store、frame deny 且未洩漏 verifier。第一次交接因視窗過早關閉導致登入失敗，已如實記錄並由 V2 防鎖死流程修復，不列為成功驗收。
- 管理通知外部排程已接通：Render 已設定獨立 `NOTIFICATION_CRON_SECRET` 與管理員收件地址，GitHub Actions 已設定同名加密 Secret；正式密鑰端點回 200 並建立兩通道佇列，手動 `Daily admin summary #1` 執行成功。Gmail 仍因 SMTP 未設定而為 `failed`，LINE 仍因 `LINE_ADMIN_USER_ID` 未設定而為 `skipped`，沒有沿用其他專案收件人。
- 新建本機資料庫：6 筆仙策、0 筆訂單；`orders` 只有 `access_token_hash`，沒有明文 `access_token` 欄位。
- 桌機瀏覽器：V13 官網、分類篩選、商品詳情、建單、模擬付款、內容解鎖、Logo 評估、LINE 六張卡片、後台登入、KPI、串接狀態與內容編輯器均通過。
- 手機 390 × 844：官網、V13 主視覺、LINE 模擬器、後台與內容編輯 dialog 都沒有根頁面水平溢位。
- 傳音頁 V2：桌機 1440 × 960 與手機 390 × 844 已分段檢視；手機根頁面寬度 390／內容寬度 390，無水平溢位；導覽、題字、內文、按鈕與頁尾的 computed font 均為書法字系。
- V14 視覺 QA：桌機實看首頁頂部、六脈區與傳音頁；導覽列品牌組合約 304px 寬，首頁與傳音主標皆正確顯示專屬封面題字，首頁深藍矩形底已由 luminance mask 消除；其餘 H2／H3 已收斂為一致月金層級。
- V14.1 可讀性 QA：桌機 computed style 確認 LOGO 副標 12px／700、導覽 15px／700、首頁卷標 14px／700、首屏說明 19px；另以 390 × 844 真實 iframe viewport 實看首頁與傳音頁，副標、主標、正文與按鈕均完整顯示且沒有水平擠壓。
- V15 視覺 QA：桌機 1280 × 720 分段檢視首屏、古卷、六脈、不等寬末卷、三境路徑、心訣與月壇；首屏主 CTA 位於 720px 視窗內。另以 390 × 844 真實 iframe viewport 檢查首頁、六脈與傳音頁，標題／按鈕／卡片無水平溢位，固定導覽已恢復。
- 瀏覽器 console：0 error、0 warning。
- 付款開通流程：桌機與 390 × 844 手機版均完成「填資料 → 付款前彈窗 → 模擬付款 → 付款成功彈窗 → 12 位碼開通 → 付費內容」實際操作；根頁面無水平溢位。
- HTTP smoke：`/healthz`、`/` 回 200；`/logo-review` 與正式環境 `/dev/line` 回 404；健康狀態為 `ok`。
- V16 本機桌機 QA：官網 1440px 首屏、卷軸、六脈 3×2 卡片、篩選互動與頁尾無水平溢位；後台 1280×900 六個工作區逐頁實看，訂單首屏可完整呈現、客戶六指標同列、安全六旗標 3＋3，系統串接四張卡均顯示下一步。
- V16 本機手機 QA：390×844 官網首屏題字完整、三項摘要無碰撞、卡片統一 394px、根頁面 375px／內容 375px；後台固定六項底部導覽、兩欄 KPI 與訂單表格內部橫向捲動正常，根頁面無水平溢位。
- 手機卡片字型 QA：390×844 六張主標 computed font-family 全為 `Tianwai Masa Display`，角色名與技能分類全為 `Tianwai Masa` 14px；第 6 張 `商機觀星盤` 實看無逐字回退，字型載入完成且根頁面無水平溢位。
- 管理憑證 V2 QA：43 位 Base64url 格式、256-bit 熵、Argon2id 正誤驗證、Hash 優先禁止降級、交接狀態機、防鎖死與後台不洩漏 verifier 均通過；完整測試 67 passed，`pip check` 無衝突。正式環境已驗證 Hash 存在、舊明文不存在、部署 Live、健康狀態正常，且擁有者以新密碼實際登入成功。

瀏覽器驗收使用的假訂單與假 Email 已從正式本機資料庫清除；可復原 QA 副本暫存於 Windows Temp，不屬專案交付資料。

## 入口

- `/`：官網與六脈仙策
- `/transmission`：自有修仙傳音頁與官方加好友 QR 法印
- `/ideas/<slug>`：免費摘要
- `/checkout/<slug>`：建立訂單
- `/pay/mock/<token>`：本機模擬付款
- `/pay/ecpay/<token>`：綠界付款轉送頁（設定完成後啟用）
- `/payments/ecpay/notify`：綠界伺服器付款通知
- `/payments/ecpay/result`：綠界客戶端付款結果返回
- `/payment/status/<activation_token>`：付款確認與開通說明
- `/activate/<activation_token>`：一次性 12 位碼首次開通
- `/customer/login`：已購客戶 Email 登入碼入口
- `/customer/library`：已購內容庫
- `/library/orders/<order_no>`：需客戶 session 的付費內容
- `/api/conversations/<section_key>`：讀取公開或該客戶自己的私密分區傳音
- `/api/conversations/<section_key>/messages`：訪客經安全驗證提交公開待審傳音；有效客戶工作階段可提交公開待審或私密傳音
- `/orders/<access_token>`：舊網址相容轉址，不再直接顯示付費內容
- `/dev/line`：LINE Bot 模擬器
- `/line/webhook`：正式 LINE webhook 入口
- `/payments/webhook/mock`：支付 webhook 範例
- `/admin`：管理後台
- `/admin/passkeys/setup`：登入後的 Passkey、雙金鑰與一次性復原碼設定（不得公開連結）
- `/admin#conversations`：登入後的傳音審核與指定回覆工作區
- `/admin/recovery`：只在 Passkey-only 且復原三因素已完整配置時存在；一般情況回 404
- `/internal/notifications/daily-summary`：GitHub Actions 專用的密鑰保護排程端點，不得公開連結

`/dev/line` 與 `/admin` 為非公開營運入口，不得從公開頁面連結；Logo 評估路由已撤除。

## 下一個最高 ROI 決策

PostgreSQL 持久化、管理登入、異地可還原備份與正式小額付款／交付／退款閉環均已完成。每日加密備份監控與每季隔離還原是例行維運，不是待補建置。現在最大商業限制已轉為需求與商品品質；最高 ROI 下一步是用目前官網招募 10～20 名目標客戶，驗證首發 1～2 個仙策的付費意願，再決定是否開啟公開 NT$199 正式收款。

安全切換與需求驗證建議依序：

1. 將每日 03:25（台北）加密 Artifact 監控與每季隔離還原納入例行維運；這是持續性保養，不是本次建置待辦，明文 dump 不得留在磁碟。
2. 手機 Passkey 保留為第二把備援，定期做非破壞性登入確認，不為測試而撤銷兩把正式金鑰或消耗復原碼。
3. 用目前 V17 與六脈頁面做 10～20 人需求驗證，選出首發 1～2 個仙策。
4. 把首發仙策補強到正式可交付品質，定案價格、退款、授權與電子發票規則。
5. 正式綠界與 Brevo 憑證只留在本專案 Render；日後只有在首發仙策內容、退款規則、發票責任與客服流程全部定案後，才重新評估開啟公開收款。

GitHub 帳號層級的 Actions budget 可能同時影響其他儲存庫，因此本專案不擅自修改。它是可選的帳務成本控制，不是防盜、防駭或災難復原的完成條件；本工作流本身已有單檔 25 MB、14 天保留與最小權限限制。

## 禁止混用

不得沿用萬語通的 LINE token、管理員 LINE ID、資料庫、Render 服務或網域。綠界特店憑證可依法沿用同一組，但不得寫入程式庫或互相共用訂單／權益資料；天外一筆固定使用 `TWYB` 訂單前綴、`StoreID=TWYB` 與自己的 callback。也不得把本專案併入辰新數位、SoundBank、NOWELYO 或其他專案目錄。
