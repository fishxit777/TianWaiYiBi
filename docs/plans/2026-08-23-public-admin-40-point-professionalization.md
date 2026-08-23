# 官網與後台 40 點專業化重整 Implementation Plan

> **For Codex:** 依序完成介面結構、視覺系統、互動狀態、自動測試、瀏覽器驗證與正式站部署；每一項修改都要能回扣本文件的問題清單。

**Goal:** 各修正官網與後台 20 個具體的業餘感來源，保留既有修仙品牌辨識，同時提升手機首屏、內容可讀性、後台營運效率與可存取性。

**Architecture:** 不改動付款、開通、風險控管與資料庫商業邏輯；以模板語意、獨立 `v16.css` 設計層及既有 JavaScript 的漸進增強完成。後台繼續使用同一組受保護 API，僅改善資料呈現、狀態層級與操作回饋。

**Tech Stack:** Flask/Jinja2、原生 CSS、原生 JavaScript、Pytest、Codex in-app Browser。

---

## Task 1：建立可驗證的 20＋20 問題基準

**Files:**
- Create: `docs/updates/2026-08-23-public-admin-40-point-professionalization.md`

1. 寫出官網 20 個問題、影響與修正方式。
2. 寫出後台 20 個問題、影響與修正方式。
3. 將桌機與手機的首屏、頁高、標題語意、卡片密度與表格可讀性列為驗收指標。

## Task 2：重整官網的內容層級與購買導引

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/home.html`
- Modify: `static/app.js`
- Create: `static/v16.css`
- Test: `tests/test_public_flow.py`

1. 為圖像標題補上真正可讀的語意 H1。
2. 重構首屏三項資訊，避免手機文字擠成一列。
3. 強化主／次 CTA、鍵盤焦點與互動狀態。
4. 為六脈篩選新增結果數與即時回饋。
5. 縮短卡片空白、增加「適合情境」提示並建立更清楚的價格與行動層級。
6. 調整卷軸、三步流程、心訣與傳音區的節奏、對比和手機排版。
7. 擴充頁尾的信任資訊與客戶入口，但不暴露管理後台或內部工具。

## Task 3：重整後台的營運密度與異常優先級

**Files:**
- Modify: `templates/admin_dashboard.html`
- Modify: `static/admin.js`
- Modify: `static/v16.css`
- Test: `tests/test_admin_security.py`

1. 將重複的大標題改為精簡麵包屑與正式站狀態。
2. 重做 KPI、待辦、脈動與圖表層級，補足期間／判讀語意。
3. 提高訂單表格、篩選器、狀態標籤、空狀態與載入狀態的可讀性。
4. 壓縮仙策內容管理的空白，放大主要操作並區分上架／編輯狀態。
5. 將客戶與安全六項指標排成 3＋3，避免 5＋1 的業餘斷行。
6. 為串接狀態補上明確的下一步，不再只顯示被動狀態。
7. 強化撤銷裝置、風險事件與警示通知的危險操作視覺。
8. 補齊手機側欄、橫向表格、焦點與 reduced-motion 支援。

## Task 4：自動化驗證與瀏覽器 QA

**Files:**
- Modify: `tests/test_public_flow.py`
- Modify: `tests/test_admin_security.py`

1. 新增語意 H1、v16 設計層、篩選結果回饋與後台營運狀態列的測試。
2. 執行 `python -m pytest -q`。
3. 執行 JavaScript 語法檢查。
4. 以本機瀏覽器驗證官網桌機、手機，以及後台總覽、訂單、仙策、客戶、串接、安全六頁。
5. 修正 QA 發現的裁切、溢位、低對比與過長頁面問題。

## Task 5：更新交接、版本與正式站

**Files:**
- Modify: `README.md`
- Modify: `HANDOFF.md`
- Modify: release marker source discovered in app configuration

1. 完整記錄 40 點修改與驗證結果。
2. 更新版本標記為 `professional-ui-v16`。
3. Commit、push，等待 Render 自動部署。
4. 驗證正式站 `/healthz` 版本、官網與受保護後台登入頁。
