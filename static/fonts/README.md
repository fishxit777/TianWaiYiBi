# TianWaiYiBi self-hosted public-site fonts

The two WOFF2 files are glyph subsets used across every public customer-facing page: home, idea details, checkout, payment, delivery, message, and transmission. The admin console, hidden logo review, and local LINE simulator intentionally keep their utility typography.

## Logo-aligned brush family

- Files: `tianwai-masa-regular.woff2`, `tianwai-masa-bold.woff2`
- CSS families: `Tianwai Masa`, `Tianwai Masa Display`
- Upstream: MasaFont（正風毛筆字體）Regular and Bold, Taiwan set
- Source: <https://github.com/max32002/masafont>
- License: SIL Open Font License 1.1 (`MasaFont-OFL.txt`)
- Upstream Regular SHA-256: `f5a449d3a9ce2170e404050cc2b44bfa16ae48ef8fb06aa5968383ed74e5ed4d`
- Upstream Bold SHA-256: `8fa80974e45ce2ba43ce6dd68aa1f2d0005a79dae761f6dde46e4d0a51b2dfb7`
- Web Regular SHA-256: `6f1cf0932b46b176f3b697731c28db92c07fb4ec59b9e22bcae185880e4f037b`
- Web Bold SHA-256: `58c4f0cf4ac4ed43bd99ce45da728787250f8cf08856fdd171810ae3a2811965`

The illustrated logo wordmark is raster artwork rather than a reusable font file. MasaFont is the complete Traditional Chinese family used across the public site. Regular carries paragraphs and controls; Bold provides the dense brush skeleton required by the white-jade and moon-gold carved title treatment. Both remain live, selectable vector text.

## Rebuild

1. Download `tw/MasaFont-Regular.ttf` and `tw/MasaFont-Bold.ttf` from the upstream repository.
2. Install the optional build dependencies: `python -m pip install fonttools brotli`.
3. Run:

   `python scripts/build_webfonts.py --regular <MasaFont-Regular.ttf> --bold <MasaFont-Bold.ttf>`

The build script collects visible glyphs from all public templates, public/payment copy, seed content, and public JavaScript. Rebuild whenever public-facing text adds new characters.
