# 手機版六脈卡片字型一致性更新

日期：2026-08-23  
版本：`mobile-card-type-v1`

## 使用者回報

手機版首頁「觀星策士／商機觀星盤／趨勢判讀・競品缺口」區塊的字形不一致，其中「商機觀星盤」同一個標題內同時出現粗毛筆與細楷書。

## 根因

網站使用自架 MasaFont WOFF2 子集，但原建置腳本沒有納入保存六脈動態內容的 `tianwai/db.py`。字型檔缺少部分卡片漢字時，iOS／行動瀏覽器會逐字改用系統字型，形成同一句內的混合字形。

## 完成項目

- 字型建置來源補入全部公開交易頁模板、`tianwai/db.py`、`tianwai/access.py` 與公開付款文案。
- 重新由 MasaFont Regular／Bold 原始字型產生 WOFF2；六脈卡片共 83 個不同漢字在兩個檔案中皆為缺字 0。
- 六張卡片角色名統一使用 MasaFont Regular 14px。
- 六張卡片主標統一使用 MasaFont Bold／Display；手機斷點設定 29px，不允許合成字重。
- 六張卡片技能分類統一使用 MasaFont Regular 14px，並保留青玉色資訊層級。
- 樣式與兩個字型網址加入 `mobile-card-type-v1` 版本參數，避免 iPhone 延用舊快取。
- 新增動態卡片文案字元收集測試，防止後續新增或改名時再次漏字。

## 驗證

- `py -3 -m py_compile ...`：通過。
- `node --check static/app.js`、`node --check static/admin.js`：通過。
- `py -3 -m pytest -q`：59 passed。
- 390 × 844 本機手機瀏覽器：六張主標皆回報 `Tianwai Masa Display`、字型載入狀態完成；角色名與技能分類皆回報 `Tianwai Masa` 14px。
- 第 6 張卡片實看：`商機觀星盤` 六字筆形一致，無逐字回退；根頁面無水平溢位。

## 未變更範圍

付款、開通、可信裝置、風險分級、管理通知、資料庫結構與後台功能皆未改動。
