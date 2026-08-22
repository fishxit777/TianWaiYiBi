# 天外一筆修仙版 Logo 概念

## V1

- 檔案：`tianwai-yibi-xianxia-v1.png`
- 生成方式：Codex 內建 ImageGen
- 狀態：本機評估中，未上傳、未部署、未視為定稿
- 評估頁：`http://127.0.0.1:5088/logo-review`

最終提示：

```text
Use case: logo-brand
Asset type: primary horizontal logo concept for a Taiwanese creative-idea studio website
Primary request: Create an original refined xianxia cultivation-themed evolution of the existing brand direction for "天外一筆工作室". Preserve the core idea of one unexpected brushstroke arriving from beyond the sky. The mark should combine a single dynamic cinnabar-orange calligraphy stroke, a subtle celestial sword-tip or writing-brush nib shape, one small jade-green spiritual spark, and a restrained star-orbit motif.
Style/medium: vector-friendly flat logo, elegant Chinese seal and ink-calligraphy influence, strong clean silhouette, premium but imaginative, suitable for website header and business card
Composition/framing: horizontal lockup; standalone symbol on the left and the exact Traditional Chinese wordmark on the right; generous clear space; centered on a genuinely transparent background
Color palette: deep midnight navy, cinnabar orange, moon-jade green, and a tiny old-gold accent; no more than four flat colors
Text (verbatim): "天外一筆工作室"
Secondary text (verbatim, smaller): "想法販售・創意支援"
Constraints: render both Traditional Chinese text lines exactly once with no added or missing characters; original design only; flat colors; high contrast; scalable; no mockup; no paper texture; no scene; no human figure; no existing anime or game symbols; no copyrighted characters; no watermark; genuinely transparent background
Avoid: generic lotus, yin-yang, mountain silhouette, dragon, clutter, photorealism, 3D bevels, neon cyberpunk, purple gradient, imitation of any known franchise
```

V1 判斷：品牌辨識強、修仙感明確，但裝飾密度偏高。若要更像成熟商業品牌，V2 應保留朱砂筆觸與筆劍，減少星軌、金色節點與靈火細節。

## V2 審稿版

- 檔案：`tianwai-yibi-xianxia-v2-review.png`
- 生成方式：Codex 內建 ImageGen，以 V1 為品牌歷史參考後重構並進行第二輪精修
- 狀態：本機米白底審稿，未上傳、未部署、未替換正式識別
- 核心符號：破界天門、中央筆劍、朱砂一筆
- 色彩：墨藍 `#071A2D`、朱砂 `#E64A19`

V2 已移除靈火、行星、金色節點、星芒、裝飾分隔線、光暈與 3D 質感。內建產圖器的透明背景嘗試實際輸出為不含 Alpha 的棋盤格影像，因此沒有把該檔冒充透明正式稿；目前保存的是乾淨米白底審稿圖。方向核准後，再建立 SVG、透明 PNG、反白版、單色版、方形頭像及 favicon。

完整十點審查與後續交付規格見 `../../docs/logo-v2-review.md`。

最終米白底審稿提示：

```text
Use case: precise-object-edit
Asset type: clean logo review proof on a solid background.
Input images: Image 1 is the exact refined logo to preserve.
Primary request: Replace only the checkerboard background with one perfectly uniform solid warm rice-white color #F7F3EA.
Constraints: preserve every logo shape, the exact two colors, emblem, cinnabar stroke, main wordmark, subtitle, spacing, scale, proportions, and composition unchanged; render a clean flat solid background with no texture; no shadow; no border; no mockup; no watermark; no added elements.
Text invariants: preserve exactly “天外一筆工作室” and “想法販售・創意支援”.
Avoid: checkerboard, transparency-grid pattern, gradients, paper grain, stains, shadows, glow, cropping, recoloring, retyping, misspelled or duplicated characters.
```

## V3 九霄仙門審稿版

- 檔案：`tianwai-yibi-xianxia-v3-nine-heavens-review.png`
- 生成方式：Codex 內建 ImageGen；V1、V2 僅作反例參考，全新生成構圖
- 狀態：本機品牌主視覺審稿，未上傳、未部署、未替換正式識別
- 核心視覺：九霄仙門法陣、筆劍法器、朱砂靈流、月下浮峰、青玉靈氣、月金書法
- 色彩：午夜靛藍、皇家紫、青玉綠、月金、朱砂、雲白

V3 的策略不是把 V2 加裝飾，而是承認 V2 過度企業化並重新建立修仙世界觀。它目前屬於品牌主視覺方向稿；核准後會從中拆分出可實際使用的字標、徽記、LINE 頭像、favicon、深淺底版本與透明母版。

V3 最終提示摘要：

```text
Use case: logo-brand
Asset type: spectacular premium xianxia brand-title logo concept for a dark fantasy website hero, app splash screen, and studio identity preview.
Primary request: Design an entirely new, richly colored, unmistakably xianxia logo for “天外一筆工作室”. A celestial writing brush forged like a flying immortal sword descends through a luminous ancient jade-and-gold formation; a living cinnabar ink stroke becomes spiritual qi and breaks through the formation. Behind it are floating immortal peaks, a sea of clouds, and moonlight.
Style: original high-end Chinese xianxia title-logo illustration with cinematic depth, jade energy, moon-gold calligraphy and restrained lacquer/ink texture.
Text (verbatim): “天外一筆工作室”; “想法販售・創意支援”.
Palette: midnight indigo, royal violet, luminous jade, turquoise, moon gold, cinnabar and pearl-white.
Avoid: minimalist flat logo, corporate icon, power-button shape, cheap mobile-game UI, copyrighted symbols, humans, cartoon dragon, yin-yang, lotus, duplicated or misspelled text.
```

## V3R 九霄仙門指定重製版

- 檔案：`tianwai-yibi-xianxia-v3r-nine-heavens-revised-review.png`
- 生成方式：Codex 內建 ImageGen，以 V3 為重製參考，重新建立三段景深與視覺層級
- 尺寸：1915 × 821（約 21:9 官網橫式主視覺）
- 狀態：本機品牌主視覺評估稿，未上傳、未部署、未替換官網
- 主層：朱砂神筆兼具毛筆、飛劍與法器輪廓，筆尖產生貫穿全景的朱砂墨流
- 中層：青玉靈氣穿過月金法陣，仙門立於雲海與浮峰之間
- 字標：滿月托住「天外一筆」，使用月金立體書法；「工作室」縮小陪襯

V3R 最終提示摘要：

```text
Use case: logo-brand
Asset type: ultra-wide website hero brand visual, revised V3 review artwork.
Input images: V3 is the redesign reference; retain its epic horizontal function and core divine-brush concept while rebuilding hierarchy.
Primary request: indigo-purple Nine Heavens, turquoise-jade spiritual qi, moon-gold formation and cinnabar divine brush; the brush must read simultaneously as calligraphy brush, flying sword and sacred artifact.
Composition: 21:9; left foreground divine brush, left-center moon-gold formation, center-background immortal gate over cloud sea and floating peaks, upper-right full moon behind the title, one cinnabar ink trail connecting the scene.
Text (verbatim): “天外一筆”; “工作室”. Render each exactly once in dimensional moon-gold Chinese calligraphy.
Visual hierarchy: divine brush and cinnabar stroke first; title second; formation third; gate, clouds, peaks and moon remain supporting scenery.
Avoid: corporate wordmark, flat gold text, duplicated or misspelled text, extra slogans, fake glyphs, dense talisman labels, crowded foreground, black-dominant darkness, cyberpunk, dragons, phoenixes or people.
```

## V4 九霄仙門精修審稿版

- 檔案：`tianwai-yibi-xianxia-v4-refined-review.png`
- 生成方式：Codex 內建 ImageGen，以 V3 為編修目標進行字標區與視覺層級精修
- 狀態：本機品牌主視覺審稿，未上傳、未部署、未替換正式識別
- 保留：神筆法器、青玉月金法陣、朱砂靈流、月下浮峰、雲海與完整華麗配色
- 改善：字標後方降噪、唯一清楚的「一」、朱砂「筆」、副標放大、移除假文字與假印章、收斂前景靈流

V4 最終提示摘要：

```text
Use case: precise-object-edit
Asset type: premium refined xianxia brand-title logo V4.
Input images: V3 is the approved direction and edit target.
Primary request: preserve the entire Nine Heavens immortal-sect direction while refining only the typography zone and immediate visual hierarchy.
Main text (verbatim): “天外一筆工作室”; render “一” as one clear moon-gold stroke and “筆” in restrained cinnabar light.
Supporting text (verbatim): “想法販售・創意支援”; enlarge for legibility and remove divider ornaments.
Remove: fake readable pseudo-Chinese runes, random seal text and competing foreground energy.
Preserve: celestial brush-sword, jade-and-gold formation, moon, floating peaks, clouds, cinematic lighting and the full indigo/violet/jade/turquoise/gold/cinnabar palette.
```

## V5 一筆開天審稿版

- 檔案：`tianwai-yibi-xianxia-v5-one-stroke-creates-heaven-review.png`
- 生成方式：Codex 內建 ImageGen；不引用 V3／V4 構圖，從零生成明亮修仙方向
- 狀態：本機品牌主視覺審稿，未上傳、未部署、未替換正式識別
- 核心特色：白玉神筆的一道靈墨創造整個仙界，並誕生六枚對應產品能力的法印
- 色彩：珍珠白、暖象牙、天青、青綠翡翠、桃花粉、珊瑚朱砂、香檳金、薰衣草紫；深色低於 15%

V5 最終提示摘要：

```text
Use case: logo-brand
Asset type: entirely new luminous xianxia brand-title key visual and logo direction V5.
Primary request: “one divine brushstroke writes an immortal world into existence.” A white-jade celestial brush paints an ink-river that becomes an unfolding scroll, jade sky-gate, floating islands, waterfalls, flying-sword light trails, and six elemental idea-seals representing sword, talisman, alchemy, mechanism, sound and star compass.
Scene: brilliant sunrise above pearl-white and pale-aqua clouds; luminous floating jade palaces and peaks; ascension and creation at dawn, not dark fantasy.
Text (verbatim): “天外一筆工作室”; “想法販售・創意支援”.
Palette: pearl white, ivory, cyan, turquoise jade, emerald, peach blossom, coral-cinnabar, champagne gold, lavender and a small amount of violet; dark colors below 15%.
Avoid: night scene, dark-dominant palette, V3/V4 composition, magic-circle main icon, corporate minimalism, fake glyphs, duplicated or misspelled text.
```

## V6 琉璃天門審稿版

- 檔案：`tianwai-yibi-xianxia-v6-jade-gate-review.png`
- 生成方式：Codex 內建 ImageGen；從零生成，不延續 V5 的繁雜場景構圖
- 狀態：本機 Logo 審稿，未上傳、未部署、未替換正式識別
- 核心視覺：白玉筆劍穿越琉璃天門，寫出唯一的朱砂「一」
- 色彩：珍珠白、天青、翡翠、月金、朱砂與少量桃紫反光
- 技術檢查：`1880 × 837`、`Format32bppArgb`，已驗證包含真正 Alpha 透明度

V6 最終提示摘要：

```text
Use case: logo-brand
Asset type: clean, luminous, premium xianxia primary logo direction V6.
Primary request: use exactly three components—one white-jade celestial brush-sword, one tall translucent jade Gate of Heaven, and one cinnabar-and-gold ink stroke forming “一”. The brush-sword passes upward through the gate, symbolizing an idea ascending beyond heaven.
Backdrop: pearl-white to pale sky-cyan with restrained immortal mist; no landscape or world scene.
Text (verbatim): “天外一筆工作室”; “想法販售・創意支援”.
Palette: pearl white, celestial cyan, turquoise jade, emerald, moon-gold, coral-cinnabar and a small peach-lavender reflection.
Avoid: clutter, six icons, floating islands, mountains, waterfalls, temples, multiple weapons, magic arrays, night scenes, fake Chinese and divider plaques.
```

## V7 LINE Bot 方形 Logo 審稿版

- 檔案：`tianwai-yibi-xianxia-v7-line-avatar-review.png`
- 生成方式：Codex 內建 ImageGen；以 V6 為品牌風格參考，另做全新 1:1 無文字圖標，第二輪再縮小置中修正圓形裁切
- 狀態：本機 LINE 大頭照候選，未上傳、未套用至 LINE Official Account
- 尺寸：`1254 × 1254`
- 核心圖像：白玉筆劍、琉璃仙門、朱砂金色一筆靈氣、四枚浮空玉符
- 色彩：深青藍、皇家靛紫、紫晶、青玉、翡翠、月金、朱砂與珍珠白；中等明度，不偏全黑或蒼白
- LINE 裁切：所有關鍵元素已縮入中央圓形安全區，外圍深色背景保留裁切餘量

V7 最終裁切修正提示摘要：

```text
Use case: precise-object-edit
Asset type: LINE Official Account circular-crop-safe square avatar.
Primary request: preserve the complete xianxia emblem, then uniformly scale the foreground group down by about 17 percent and recenter it precisely.
Keep: one white-jade brush-sword, one jade Gate of Heaven, one cinnabar-gold energy stroke, cloud tips, four jade shards, teal/indigo/amethyst celestial background and jade halo.
Safe area: brush tip, tassel, bristles, gate corners, shards, clouds and energy stroke must remain inside an inscribed circular crop with at least 8 percent internal margin.
Text: none; no letters, numbers, Chinese characters or pseudo-writing.
```

## V12 天外神筆法印無字 Logo 評估版

- 檔案：`tianwai-yibi-xianxia-v12-celestial-brush-seal-review.png`
- 生成方式：Codex 內建 ImageGen；以 V3R 為色彩與材質參考，重新提煉為方形無字標誌
- 狀態：本機 Logo 評估稿，未上傳、未套用官網或 LINE Bot
- 尺寸：`1254 × 1254`
- 核心圖像：一支朱砂神筆、一圈四段月金法印、一縷 S 形青玉靈氣
- 刪除項目：文字、仙門、雲海、浮峰、遠景滿月、符文與裝飾碎片
- LINE 裁切：全圖已縮入中央圓形安全區

V12 最終提示摘要：

```text
Use case: logo-brand
Asset type: square no-text symbol mark for LINE Bot avatar, app icon, favicon and website logo.
Primary request: distill V3R into exactly three components—one unmistakable cinnabar-red Chinese calligraphy brush, one four-segment moon-gold formation ring and one controlled turquoise-jade qi ribbon.
Style: premium vector-friendly xianxia emblem with crisp silhouette, restrained dimensional cel-shading and minimal detail.
Composition: centered 1:1 mark, brush carries about 65% visual weight, complete emblem remains safe inside a circular profile crop.
Background: clean indigo-to-imperial-purple radial gradient.
Constraints: no text, characters, glyphs, runes, scenery, extra rings, extra trails or ornamental clutter.
```

## V13 仙氣飄逸無字 Logo 評估版

- 檔案：`tianwai-yibi-xianxia-v13-ethereal-celestial-brush-review.png`
- 生成方式：Codex 內建 ImageGen；以 V12 為三元素與配色參考，重新設計材質與漂浮動勢
- 狀態：本機 Logo 評估稿，未上傳、未套用官網或 LINE Bot
- 核心圖像：透玉神筆、月金薄暈、半透明青玉雲紗靈氣
- 改善：移除厚重金屬法環、槍尖感與塑膠帶質感，改用月暈細線、開口月冠、飛白尾絲與透光筆管
- 尺寸：`1254 × 1254`，已保留 LINE 圓形裁切安全距離

V13 最終提示摘要：

```text
Use case: logo-brand
Asset type: square no-text LINE Bot and app logo, ethereal xianxia variant.
Primary request: exactly one floating pearl-jade calligraphy brush with cinnabar-tipped bristles, one thin broken moon-gold halo, and one semi-transparent turquoise-jade qi veil.
Style: premium xianxia manhua emblem with luminous ink wash, delicate negative space and a clean vector-friendly silhouette.
Mood: 仙氣飄飄然—weightless, serene, celestial, refined and quietly powerful.
Avoid: thick metal ring, rigid symmetry, spearhead, game inventory icon, solid plastic ribbon, scenery, text and ornamental clutter.
```
