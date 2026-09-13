# Private paid visuals

This directory is not a Flask static directory and must never be exposed through a static host, public bucket, CDN or file-listing route.

- The existing 75 current/retired delivery images were relocated here byte-for-byte in V32; no artwork was deleted or regenerated.
- Database identifiers retain `brand/...` to preserve existing content records. They are identifiers relative to this private root, not public URLs.
- Import new modern technical visuals here first. Admin validation accepts only existing, safe private identifiers; the customer image route checks current session/device and ownership of a paid order before every response.
- Retired V30 illustrations stay private for history, not as current delivery content. V31 remains the current modern visual set.
- Original source media and temporary renders remain in the ignored local project folder. This repository must remain private; moving files here does not make a public Git repository safe.
- No public pre-signed URL or copy-protection guarantee is provided. Legitimate readers can still capture their screens; previous downloads cannot be recalled.
