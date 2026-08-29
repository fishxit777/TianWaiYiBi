# 2026-08-30 V20 九霄封卷匣主視覺

## 結果

- 首頁右側舊米白紙卷已移除，不再出現像紙袋、紙杯或普通包裝的輪廓。
- 新主視覺改為「九霄封卷匣」：玄黑卷匣、古金雲紋、朱砂束帶、青玉環鎖、流蘇、禁制陣與冷青靈氣共同表現尚未拆封的仙門秘卷。
- 新增「封印未解／禁制完整・內容未揭」狀態牌，三項購買資訊仍保留，但全部使用 V19 清楚正黑體。
- 桌機與手機各自調整法器比例、狀態牌和三欄資訊，不靠裁切或隱藏文字製造效果。
- 動畫包含法器漂浮、禁制陣旋轉、靈氣呼吸與雲霧位移；使用者偏好減少動態時全部停用。

## 資產

- 原創透明主資產：`static/brand/sealed-scroll-casket-v20.webp`。
- 尺寸 1122×1402，WebP 含透明通道，約 287 KB。
- 圖中沒有首卷真名、完整機制、可讀文字、Logo 或其他專案素材。
- 首頁以高優先圖片預載，避免首屏先出現空白禁制陣。

## 本機驗證

- `python -m pytest -q`：163 passed、1 skipped。
- `python -m compileall -q tianwai scripts`：通過。
- `static/app.js`、`static/admin.js`、`static/admin-identity.js`、`static/admin-passkey.js`：`node --check` 通過。
- `python -m pip check`：無相依衝突。
- `git diff --check`：通過。
- Browser 1440×900：新資產載入成功、舊紙卷節點 0、根頁面無水平溢位。
- Browser 390×844：法器、禁制陣、狀態牌與三欄資訊均完整呈現，根頁面無水平溢位。
- 公開首頁 0 破圖、0 console issue；首屏 computed font 無 MasaFont、DFKai、BiauKai、KaiTi 或 STKaiti。

## 未改動

- 沒有修改盲策內容、公開線索、價格、公開收款狀態、訂單、退款、客戶權限或資料庫 schema。
- 沒有恢復留言、匿名討論、評分或買家社群。
- 沒有登入正式後台，也沒有操作正式客戶、Passkey、復原碼、備份或金流憑證。

## 正式部署

- 待實作提交推送並完成 Render 純讀驗證後補記。
