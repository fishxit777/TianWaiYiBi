# TianWaiYiBi self-hosted web fonts

These WOFF2 files are glyph subsets for the public transmission page. They are self-hosted so the intended Traditional Chinese typography is consistent across devices and does not depend on a third-party font CDN.

## Display font

- File: `tianwai-brush-display.woff2`
- CSS family: `Tianwai Brush`
- Upstream: ChenYuluoyan 2.0 Thin
- Source: <https://github.com/Chenyu-otf/chenyuluoyan_thin>
- License: SIL Open Font License 1.1 (`ChenYuluoyan-OFL.txt`)
- Upstream SHA-256: `1289e42a6d1ec995d0cb23aee89efc69fc95749fbd54a610057a3e992dc453db`
- Web subset SHA-256: `220fb1f6f6340243fbda46b8ccc1df6881eeace43841f715c01a6757dc11e742`

## Body font

- File: `tianwai-wenkai-body.woff2`
- CSS family: `Tianwai WenKai`
- Upstream: LXGW WenKai TC Regular
- Source: <https://github.com/lxgw/LxgwWenkaiTC>
- License: SIL Open Font License 1.1 (`LXGWWenKaiTC-OFL.txt`)
- Upstream SHA-256: `b1a0795862c1415bf3f393ea50b2a4ea6275012cf5bad3f94feeb1222f555731`
- Web subset SHA-256: `209214d3ed7c83f4a24dc44770f7d1a0e21793a4af5f4f1514f5ada7e8a75778`

## Build notes

The subsets contain the glyphs used by `templates/base.html`, `templates/transmission.html`, and the copy-status text in `static/app.js`, plus basic Latin and CJK punctuation. They preserve OpenType layout features and hinting, then use WOFF2 compression. Rebuild the subsets whenever visible transmission-page copy adds new characters.
