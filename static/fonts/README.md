# TianWaiYiBi self-hosted public-site fonts

The two WOFF2 files are glyph subsets used across every public customer-facing page: home, idea details, checkout, payment, delivery, message, and transmission. The admin console, hidden logo review, and local LINE simulator intentionally keep their utility typography.

## Brush family

- Files: `tianwai-bakudai-regular.woff2`, `tianwai-bakudai-medium.woff2`
- CSS families: `Tianwai Bakudai`, `Tianwai Bakudai Display`
- Upstream: Bakudai Font（莫大毛筆字體）Regular and Medium, Taiwan set
- Source: <https://github.com/max32002/bakudaifont>
- License: SIL Open Font License 1.1 (`Bakudai-OFL.txt`)
- Upstream Regular SHA-256: `19fad0c294f3d3013bdee7471cd5e79015ee7a03acb2c47d9955937fc3dc8e4e`
- Upstream Medium SHA-256: `6c4a1be29e508fed588d8ec749ed8ae9e3b8325af0e0a973657739256dba9997`
- Web Regular SHA-256: `3a6c51857e1d771ca6aa58ce8cccb9a42e023f614118d434ce7f237f60fd88a7`
- Web Medium SHA-256: `ef44b10c057a82268b48e6b6a533179134f3598bf101b06e6fb427c06b38f392`

The Regular cut carries paragraphs and controls. The Medium cut carries headings and bold emphasis. Both preserve real brush-edge variation and remain vector-sharp without glow or fake CSS strokes.

## Rebuild

1. Download `tw/Bakudai-Regular.ttf` and `tw/Bakudai-Medium.ttf` from the upstream repository.
2. Install the optional build dependencies: `python -m pip install fonttools brotli`.
3. Run:

   `python scripts/build_webfonts.py --regular <Bakudai-Regular.ttf> --medium <Bakudai-Medium.ttf>`

The build script collects visible glyphs from all public templates, public/payment copy, seed content, and public JavaScript. Rebuild whenever public-facing text adds new characters.
