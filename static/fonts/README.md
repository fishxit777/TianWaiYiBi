# TianWaiYiBi self-hosted public-site fonts

The two WOFF2 files are glyph subsets used across every public customer-facing page: home, idea details, checkout, payment, delivery, message, and transmission. The admin console, hidden logo review, and local LINE simulator intentionally keep their utility typography.

## Logo-aligned brush family

- Files: `tianwai-masa-regular.woff2`, `tianwai-masa-medium.woff2`
- CSS families: `Tianwai Masa`, `Tianwai Masa Display`
- Upstream: MasaFont（正風毛筆字體）Regular and Medium, Taiwan set
- Source: <https://github.com/max32002/masafont>
- License: SIL Open Font License 1.1 (`MasaFont-OFL.txt`)
- Upstream Regular SHA-256: `f5a449d3a9ce2170e404050cc2b44bfa16ae48ef8fb06aa5968383ed74e5ed4d`
- Upstream Medium SHA-256: `24ddf16810c42a98b358776767b0e6be7ab171099d6c959aa7ad1accc1cd6bb3`
- Web Regular SHA-256: `6f1cf0932b46b176f3b697731c28db92c07fb4ec59b9e22bcae185880e4f037b`
- Web Medium SHA-256: `7af1fae22011706670fffc1033914b367ad153a8562842d73c7778b7f7dfe28f`

The illustrated logo wordmark is raster artwork rather than a reusable font file. MasaFont is the closest complete Traditional Chinese family in the project: its semi-cursive construction, connected momentum, variable stroke pressure, and sharp finishing strokes track the logo more closely than the previous square brush-kaishu family. The Regular cut carries paragraphs and controls; Medium carries headings and bold emphasis. Both remain vector-sharp without glow or fake CSS strokes.

## Rebuild

1. Download `tw/MasaFont-Regular.ttf` and `tw/MasaFont-Medium.ttf` from the upstream repository.
2. Install the optional build dependencies: `python -m pip install fonttools brotli`.
3. Run:

   `python scripts/build_webfonts.py --regular <MasaFont-Regular.ttf> --medium <MasaFont-Medium.ttf>`

The build script collects visible glyphs from all public templates, public/payment copy, seed content, and public JavaScript. Rebuild whenever public-facing text adds new characters.
