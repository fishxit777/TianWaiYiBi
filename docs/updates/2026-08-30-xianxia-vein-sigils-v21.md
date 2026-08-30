# 2026-08-30 V21 六脈仙門法印系統

## 結果

- 六脈索引的守、造、機、局、人、音已由普通單線圓標改成六枚仙門命牌。
- 每枚命牌保留清楚主字，增加鎮、鑄、演、破、生、鳴副印，並使用低飽和青玉、月金、玄紫、朱砂、木青與霜藍區分屬性。
- 桌機六脈由單排表格改為 3×2 命牌陣列；平板為 2×3；窄手機為單欄橫向命牌，不再把六脈壓成小格。
- 首頁商品卡、封印詳情與結帳確認共用朱砂玄鐵切角封牌。
- V20 首屏卷號狀態與拆封三步驟也換成同族小型命牌，整條購買前路徑不再混用普通單字圓章。
- 圓形禁制陣、Logo、頭像與狀態點維持原狀；它們是法陣或功能性識別，不是本次要退役的分類圓標。
- 補上六脈錨點安全距離，直接開啟 `#veins` 時標題不再被固定導覽遮住。

## 實作

- 新增 `static/v21.css`，在 V20 後載入，集中管理六脈屬性、切角輪廓、響應式排列與共用封牌。
- `templates/home.html` 為六脈加入可維護的語意 class 與 `data-mark`；主字裝飾標為 `aria-hidden`，脈名仍由正常標題提供給輔助科技。
- `templates/idea_detail.html` 與 `templates/checkout.html` 共用 `.sealed-talisman`，避免後續再次出現互不一致的封印章。
- 健康版本更新為 `xianxia-vein-sigils-v21`。

## 本機驗證

- `python -m pytest -q`：164 passed、1 skipped。
- `python -m compileall -q tianwai scripts`：通過。
- `static/app.js`、`static/admin.js`、`static/admin-identity.js`、`static/admin-passkey.js`：`node --check` 通過。
- `python -m pip check`：無相依衝突。
- `git diff --check`：通過。
- Browser 1440×900：六枚命牌為 3×2、舊直屬圓標 0、錨點標題未被導覽遮住、根頁面無水平溢位。
- Browser 390×844：六枚命牌為單欄、每張 347×150，封印詳情與結帳法牌均完整顯示，根頁面無水平溢位。
- 公開頁 0 破圖、0 console issue；相關命牌 computed border-radius 全部為 0，且無 MasaFont、DFKai、BiauKai、KaiTi 或 STKaiti。

## 未改動

- 沒有修改六脈分類、盲策內容、公開線索、價格、公開收款、訂單、退款、客戶權限或資料庫 schema。
- 沒有恢復留言、匿名討論、評分或買家社群。
- 沒有登入正式後台，也沒有操作正式客戶、Passkey、復原碼、備份或金流憑證。

## 正式部署

- 實作提交 `ceb17fb` 已推送至 `main`，Render 正式站已部署。
- `/healthz` 回 200、`status=ok`、`release=xianxia-vein-sigils-v21`。
- 正式首頁、封印詳情、收款未開放頁與 V21 CSS 均回 200；首頁有 6 枚六脈命牌、6 張六脈卡，舊式直屬圓標為 0。
- 首頁商品卡、封印詳情與收款未開放頁均載入共用切角封牌；公開收款仍關閉，首頁結帳連結為 0。
- 正式驗收只讀取公開端點，未送出匿名意願、未建立訂單、未登入後台，也未操作客戶資料、Passkey、復原碼、備份、通知或金流憑證。
