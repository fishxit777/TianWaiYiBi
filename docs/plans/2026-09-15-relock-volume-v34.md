# ReLock sealed volume V34 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> 本環境未提供上述 superpowers 子技能；本次依 Code／writing-plans 流程，在使用者指定的獨立專案執行已授權批次，不另建專案或讀取其他歷史對話。

**Goal:** 執行使用者確認的第 2、3 項：完整現代圖文交付，並新增第拾肆卷封印目錄。

**Architecture:** 新增獨立 V34 seed，沿用既有 insert-if-missing 流程、三圖欄位與逐卷授權，不修改前十三卷種子與價格。既有啟動時三圖／圖說同步規則沿用，不宣稱保留任意視覺編修。公開只顯示線索；完整內容與三張圖片留在既有私有閱讀管道。題材是電腦模擬概念，不交付真車控制軟體。

**Tech Stack:** Flask、Jinja、SQLite/PostgreSQL 既有相容層、WebP、pytest、原生瀏覽器。

---

## 授權與驗收

- 不另交第 1 項的原說法／修正版審核報告；必要的概念成熟度與安全邊界仍寫入交付內容。
- 標準 2：三張現代圖（主視覺、資料流拆解、使用情境）＋完整繁中圖說；內文包含原理、模組、編號實作步驟、測試方法、限制。沒有古裝工程、假數據或量產承諾。
- 標準 3：第拾肆卷主脈守護、副脈靈機；未授權不能讀完整文字或圖片，原十三卷不覆寫；1440px／390px 圖文無破圖或水平溢位；公開收款與價格不變，既有測試、機密檢查、正式部署与同步核對通過。
- 圖文僅提出可供評估的方案，不宣稱完成真車、人體辨識、傷亡減少、專利或車規驗證。不接 CAN／OBD／油門／煞車，不做真車或真人碰撞測試。

## Task 1: Content contract and regression tests

Files: `tests/test_relock_v34.py`, `tianwai/v34_catalog.py`.

1. 先新增測試，要求 slug `sealed-concept-v14`、公開卷名、主副脈、三個私有圖片路徑及必要內文段落。
2. 執行 `python -m pytest tests/test_relock_v34.py -q`，證明目前缺少此卷。
3. 補上單筆 `V34_BLINDBOX_SEEDS`，真名 `ReLock｜二次移動鎖`，三圖路徑 `brand/concepts/v34-14-{hero,diagram,scene}.webp`。
4. 增加重啟不重複、新卷加入前後十三卷資料與價格不變、匿名不可取得圖文的回歸測試。

## Task 2: Three modern visual assets

Files: `private_assets/brand/concepts/v34-14-*.webp`, `docs/updates/2026-09-15-relock-visual-prompts-v34.md`.

1. 用內建 imagegen 分別生成三個獨立資產；乾淨現代工業／介面示意，不畫真實傷亡或假成效。
2. 原始檔複製至本機忽略的 `_local/qa-v34/source/`；以圖像格式轉換輸出 WebP，保持完整畫面不裁切。
3. 逐張目視核對圖中文字、箭頭、模組與內文一致；記錄完整 prompt 與來源路徑。
4. 每張 1600×900 且小於 700 KB；確保 `static/` 無副本。

## Task 3: Existing catalog integration

Files: `tianwai/db.py`, `tianwai/__init__.py`, `tests/test_blindbox_catalog.py`, `tests/test_public_flow.py`, `scripts/verify_public_catalog.py` and narrowly affected count assertions.

1. 匯入 V34 seed，僅在 `BLINDBOX_SEEDS` 末端追加；不變更訂單、登入、通知、價目設定或 schema。
2. 更新現行目錄的 14 卷預期；保留 V31 舊 36 張及舊 75 張禁止公開的歷史覆蓋，不以新數量削弱測試。
3. 更新 health release 為 `relock-sealed-concept-v34`。
4. 執行完整 pytest、compileall、JS syntax、pip check、git diff --check 及不回印機密的增量掃描。

## Task 4: Visual and authorization acceptance

Files: ignored `_local/qa-v34/` fixtures only; `docs/updates/2026-09-15-relock-sealed-concept-v34.md`, `HANDOFF.md`.

1. 用隔離 SQLite 與合成權限啟動 loopback QA，不讀正式客戶資料。
2. 1440px／390px 檢查目錄、公開封印頁、完整內容、三圖與大圖操作；任何一項不通過即修正重驗，最多三輪。
3. 記錄兩條標準的逐輪通過狀態與未驗證邊界，不把素材示意或網站測試冒充概念效果驗證。
4. stage 明確檔案、commit、push；正式唯讀驗證 health、14 卷、封印邊界、新圖未授權 404、收款關閉。
5. 補記正式證據，提交推送交接文件，核對 main、origin/main 與遠端一致。

### 實作中自驗修正

- 資料流圖第1／2輪不通過；第3輪簡化成五個主流程模組與下方旁路紀錄，人工請求直接進狀態機，最終目視通過。
- 新卷閱讀頁成熟度標籤原本對比過淡、長文缺少層級：限定第拾肆卷套用清楚色彩與14個分節標題，六步各自成節，舊卷維持原呈現。
- 新卷公開卷面原會套用「雙輪護陣」：限定新 slug 使用守護圖紋與「觀險守程」，首頁、詳情、關閉中的結帳頁一致；不揭露私有機制。
- 交叉複查補齊 PostgreSQL 並行冷啟動測試的14卷預期；沒有為通過測試移除原並行行為覆蓋。
- 最後編輯相容性複查補齊CRLF／多空白行正規化與明確標題判斷；一般正文不再因空白行被提升為標題，HTML跳脫不變。最終28項新卷測試與347項一般測試通過、6項需獨立PostgreSQL環境跳過。
