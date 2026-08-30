# 2026-08-30 V23 雲上仙伴互動系統

## 結果

- 首頁新增六位固定、可重複辨識的 Q 版仙伴，不使用無關的隨機貼圖：守護脈「守雲」、造物脈「鑄星」、靈機脈「玄算」、破局脈「弈川」、人間脈「桃夭」、傳音脈「清商」。
- 六位角色共用九霄封卷匣的黑漆、古金、朱砂、青玉與冷青靈光材質，維持 V20 封印卷的修仙世界觀；男女角色、服裝、法器、表情與手勢各有差異。
- 守雲在首屏守護封卷匣；六脈卡各由對應仙伴駐守；封印目錄按主脈顯示看守角色；拆封三步形成三個插圖小場景；清商在頁尾吹笛送客。
- 角色按鈕支援滑入、鍵盤焦點與點擊。點擊後會切換短句、播放揮手、舉槌、推演、展扇、靈花或吹笛動作，約 2.4 秒後回到待機；沒有送出 API、沒有記錄分析事件，也不把互動次數當成真人或需求證據。
- V22 明亮雲海保留，另加入法陣、雲帶與淡金光暈填補空白。所有介面文字仍使用 V19 清楚正黑體；Logo 與品牌圖片規則不變。

## 圖像資產

內建 ImageGen 先產生原始 PNG，再逐張做背景抽離；只有四角 alpha 通過的來源才進行網站壓縮。最終資產均為 480×720、`yuva420p` 透明 WebP：

- `static/brand/companions/chibi-guardian-v23.webp`：87,696 bytes。
- `static/brand/companions/chibi-crafter-v23.webp`：92,354 bytes。
- `static/brand/companions/chibi-oracle-v23.webp`：92,986 bytes。
- `static/brand/companions/chibi-strategist-v23.webp`：115,792 bytes。
- `static/brand/companions/chibi-healer-v23.webp`：89,108 bytes。
- `static/brand/companions/chibi-musician-v23.webp`：106,124 bytes。

全部低於 180 KB；首屏只預載守雲，其餘維持 lazy loading。

## ImageGen 模式與最終 prompt set

- 模式：Codex 內建 ImageGen；以 `sealed-scroll-casket-v20.webp` 作材質色票參考，以守雲通過透明度檢查的版本作固定角色家族風格參考。
- 守雲母版 prompt：`Create an original full-body chibi female immortal swordswoman named Shouyun, the Guardian Vein companion. Cheerful young xianxia guardian waving with one hand, short cinnabar-red spirit sword safely downward, translucent jade protective disc behind her shoulder; premium polished 3D chibi collectible illustration; two-and-a-half-head proportions; bright morning celestial light; moon-white and pale-jade robe, black lacquer, antique gold and cinnabar; one complete character, genuine transparent background, clean alpha, no text, logo, watermark, extra limbs or cropped body.`
- 共用家族 prompt：`Create one new full-body recurring website companion using the reference character's polished 3D chibi rendering, proportions and bright celestial lighting, and the sealed casket's black lacquer, antique gold, cinnabar, pale jade and cyan glow. One centered character, complete props and limbs, generous padding, genuine transparent background, no scenery, frame, text, logo, watermark, duplicate props or extra limbs.`
- 六脈角色變體：`Zhuxing: cheerful male celestial crafter, ornate spirit hammer and floating black-gold cauldron`; `Xuansuan: clever female talisman scholar, thinking gesture, cyan-violet calculation wheel and talisman slips`; `Yichuan: playful male strategist, folding fan and floating jade chess piece`; `Taoyao: sunny female healer, glowing peach blossom, medicine gourd and thumbs-up`; `Qingshang: joyful male musician, pale-jade flute and cyan-gold spirit notes`。
- 背景抽離 prompt：`Isolate the exact existing chibi immortal character and all intentional held or floating props. Delete every background pixel completely. Outside the subject must be genuine alpha 0, not white, black, blurred or a simulated checkerboard. Preserve identity, face, pose, expression, clothing, props, glow, proportions and crop; no redesign, relighting, background, floor, text or watermark.`

## 實作

- `templates/home.html` 建立六脈角色映射、首屏角色、六張可操作仙伴卡、主脈封印卡 cameo、三步插圖與頁尾送客角色。
- `templates/base.html` 載入 V23 樣式並提供只有首頁使用的頁尾角色區塊。
- `static/v23.css` 集中處理角色排版、泡泡、名牌、雲海補景、六種動作、桌機／平板／手機響應式與 `prefers-reduced-motion`。
- `static/companions.js` 只做本機台詞輪替、`aria-pressed` 與短暫動作狀態；沒有 `fetch`、儲存或分析。
- 健康版本更新為 `chibi-immortal-companions-v23`。

## 本機驗證

- `python -m pytest -q`：166 passed、1 skipped。
- Python compileall、`static/app.js`、`static/companions.js`、`static/admin.js` syntax、`pip check`、`git diff --check`：通過。
- 六張透明 WebP 均為 480×720、`yuva420p`，尺寸 87,696～115,792 bytes。
- Browser 1440×900：首屏封卷匣與守雲、六脈 3×2、封印卡、拆封三步與頁尾均正常；角色點擊會換句與動作，狀態牌與角色無重疊。
- Browser 390×844：單欄六脈、封印卡 cameo、三步插圖與頁尾角色均正常；文件寬 375px、頁面寬 375px，無根頁面水平溢位。
- 所有角色圖片成功載入，0 破圖、0 console error／warning；手機仙伴名牌位於卡內，封卷狀態牌與守雲交疊面積為 0。
- 瀏覽器使用 Windows Temp 隔離資料庫；沒有送出匿名意願、沒有建立訂單，也沒有登入正式後台或觸碰正式資料。

## 未改動

- 沒有修改盲策公開線索、拆封內容、匿名意願、需求雷達、價格、付款、訂單、退款、客戶權限、安全、Passkey、復原碼、通知或資料庫 schema。
- 沒有恢復留言、匿名討論、評分或買家社群。
- 公開 NT$199 收款維持關閉。

## 正式部署

- 待 V23 實作提交推送並由正式站只讀驗證後回填；在正式證據出現前不宣稱已上線。
