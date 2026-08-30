# 天外一筆 V13「仙氣飄逸」品牌素材包

## 狀態

本資料夾為本機評估稿。尚未上傳、部署或替換官網。

統一風格：

- 透玉神筆：珍珠白玉筆管、月金筆冠與筆箍、朱砂筆毫
- 青玉靈氣：半透明雲紗、飛白尾絲、輕盈 S 形流動
- 月金法印：薄月暈與細線，不使用厚重金屬法環
- 主背景：深靛紫夜空或暖玉淺底
- 原則：仙氣、留白、飄逸、透光；避免遊戲裝備感、塑膠帶與裝飾堆疊

## 可用素材

| 檔案 | 尺寸 | 用途 |
| --- | ---: | --- |
| `logo-dark-1254.png` | 1254 × 1254 | 深底 Logo 主評估稿 |
| `logo-light-1254.png` | 1254 × 1254 | 淺底 Logo 主評估稿 |
| `logo-transparent-1254.png` | 1254 × 1254 | 透明背景候選母版，含真正 Alpha |
| `logo-transparent-512.png` | 512 × 512 | App／社群透明版本 |
| `website-nav-logo-256.png` | 256 × 256 | 官網導覽列透明圖標 |
| `logo-dark-512.png` | 512 × 512 | App icon／PWA 候選 |
| `logo-light-512.png` | 512 × 512 | 淺色介面候選 |
| `favicon-192.png` | 192 × 192 | Android／PWA |
| `favicon-64.png` | 64 × 64 | 高密度瀏覽器圖標 |
| `favicon-32.png` | 32 × 32 | 瀏覽器 favicon |
| `website-hero-dark.png` | 1915 × 821 | 深靛九霄官網首屏 |
| `website-hero-light.png` | 1915 × 821 | 明亮九霄官網首屏 |

`logo-transparent-raw-1254.png` 是 ImageGen 原始透明抽取稿，僅供追溯；正式使用應優先評估已縮入安全區的 `logo-transparent-1254.png`。

## 使用規則

- 官網導覽列使用透明版本；深色背景優先用 `website-nav-logo-256.png`。
- 深色首屏使用 `website-hero-dark.png`；內容頁或明亮主題使用 `website-hero-light.png`。
- Logo 本體不加文字。官網主視覺才使用「天外一筆／工作室」月金立體書法。
- 透明母版仍是 AI 抽取候選。正式商標定稿時應依核准圖重建 SVG 向量，確保邊緣、縮放與印刷一致。

## 圓形裁切驗證

V13 已使用實際圓形遮罩驗證。筆冠、朱砂筆尖、月暈與靈氣尾絲均完整保留，關鍵圖形距離裁切邊界仍有約 8–10% 餘量。

## ImageGen 提示摘要

深底主 Logo：

```text
Use case: logo-brand
Create one floating pearl-jade Chinese calligraphy brush with cinnabar-tipped bristles, one thin broken moon-gold halo and one semi-transparent turquoise-jade qi veil. Mood: 仙氣飄飄然; weightless, serene and refined. No text, scenery, thick metal ring, spearhead, plastic ribbon or clutter.
```

淺底版本：

```text
Use case: precise-object-edit
Preserve V13 geometry and circular-crop-safe placement. Change only the background to warm pearl-ivory and pale celadon with a faint lavender mist bloom; deepen only the minimum teal-violet edge contrast needed for visibility.
```

透明版本：

```text
Use case: background-extraction
Remove the indigo-violet background to genuine transparency. Preserve the complete brush, thin moon-gold halo, translucent qi opacity, flyaway filaments and glow falloff; no checkerboard, matte fringe, text or redesign.
```

官網主視覺：

```text
Use case: logo-brand
Rebuild V3R in the V13 ethereal material language: pearl-jade brush, thin moon-gold formation, silk-gauze qi, mist-softened gate and floating peaks, diffused full moon, and one airy cinnabar ink-water stroke. Render exactly “天外一筆” and “工作室”, each once.
```
