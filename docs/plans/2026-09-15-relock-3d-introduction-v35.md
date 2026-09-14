# ReLock 3D Introduction V35 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> 本環境沒有上述superpowers套件；依Code／writing-plans流程，在使用者指定的既有專案直接完成核准補件，不另開專案。

**Goal:** 保留第十四卷既有三張驗收相關圖，另外新增單張完整3D圖文介紹長圖，解釋概念用途、整個事件流程與分支。

**Architecture:** 以純資料registry增加該卷唯一的介紹圖與對照文字，不修改資料庫schema。新增introduction圖片slot沿用既有逐卷付費、裝置與工作階段授權；公開不揭露新圖或完整流程。閱讀頁先介紹概念，再保留原有三圖與測試規劃。

**Tech Stack:** Flask／Jinja、現有私有素材路由、原生大圖對話框、WebP、pytest、內建imagegen。

---

## 驗收標準

1. 單張3D現代車輛圖文長圖，從正常行駛、疑似事件、資料品質／事件評估、再次移動請求、獨立授權條件到處理結果；不是只畫測試工作台。每步有繁中標示、場景與明確箭頭。
2. 條件不足／未知與成立分支清楚區分；持續觀察的新事件回評估；條件慢移明示為獨立待研究例外，不暗示任意解除、保證停止或安全效果。正文有逐步對照，圖與文一致。
3. 新圖不取代原三圖；只交付第十四卷授權買家，公開保持封印。桌機1440與手機390閱讀無溢位，測試、機密掃描、文件、commit／push、正式站與main／origin同步驗證完成；收款／價格／推播與前13卷不變。

## Task 1：先建立契約測試

Create `tests/test_relock_introduction_v35.py`，測試registry、2048×3072 WebP、單張新增圖、舊3圖不變、匿名／跨卷／撤權／撤裝置不能讀、正確買家GET／HEAD可讀且no-store、公共頁與API不洩漏。

先跑 `python -m pytest tests/test_relock_introduction_v35.py -q`，預期缺少registry／素材而失敗；實作後重跑至通過。

## Task 2：製作單張3D介紹圖

以內建imagegen產生圖文長圖，畫面使用一致的現代銀色車輛、道路／座艙／概念處理模組，不画仙俠場景或再次用工作台取代產品介紹。保存原始PNG到本機忽略的`_local/qa-v35/source/`，最終WebP存`private_assets/brand/concepts/v35-14-introduction.webp`；只作格式／尺寸轉換。目視文字、分支與箭頭，最多三輪修正。

## Task 3：最小私有交付整合

Create `tianwai/concept_guides.py`：`get_concept_guide(slug)`、`supplemental_asset_identifiers()`及單一guide資料。Modify `tianwai/private_content.py`：允許introduction slot，授權查詢取得DB slug後才解析registry路徑。Modify `tianwai/access.py`、`templates/order_access.html`、`static/v34-reader.css`：於原hero之前加入完整介紹流程、大圖及逐步文字，不動原卷格式或資料庫欄位。

root更新`v34_catalog.py`的交付清單與「三張→四張」描述，使用精確舊值更新規則只補本卷原版文字，避免覆寫自行編修內容。更新公開驗證器私有總圖數79、release與相關測試，不減少原78圖覆蓋。

## Task 4：驗證與正式交付

執行完整pytest、Python compileall、JS語法、pip check、機密掃描、git diff --check；隔離本機合成買家GUI驗收兩尺寸及大圖。更新README／HANDOFF／V35驗收與提示詞文件。明確stage、commit、push；以對應commit部署狀態及公開唯讀驗證核對，不讀正式客戶或觸發付款／推播。

生成圖的呈現不等於實作、車規或安全效果已完成；不製作新的實車控制程式。
