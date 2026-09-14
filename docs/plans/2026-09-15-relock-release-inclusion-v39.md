# ReLock Release Inclusion V39 Implementation Plan

**Goal:** Include the approved fourteenth volume in private price preparation, full preview and one-click listing, then update HANDOFF.

**Architecture:** Extend the existing catalogue to fourteen volumes. Reuse ReLock's V36 guide, four private images and original manuscript instead of manufacturing a second six-step package. Preserve existing authentication, atomic publishing, order snapshots and closed payment gates. Save the approved price privately through the existing authenticated per-volume settings; no real price in runtime code or Git.

**Tech Stack:** Existing Flask/Jinja, vanilla JavaScript, SQLite/PostgreSQL and pytest.

## Acceptance criteria

1. Fourteen prepared volumes; ReLock has its approved private price, original four images, seven-step introduction, state/scenario explanations and full manuscript. First thirteen prices/content remain unchanged.
2. Single/all-volume listing and full previews include XIV. The normal hub has no price input; ReLock accurately reports its own delivery format, not thirteen-volume worksheet counts.
3. No production publication, payment activation, order mutation or public private-content exposure. Authenticated assets remain no-store; atomic failure and repeated submission protections cover fourteen volumes.

## Implementation tasks

- Backend: expand the pricing/publishing whitelist and scope messages, validate ReLock's existing guide/manuscript/four actual assets, supply accurate inventory metadata and introduction asset URL, and keep malformed/unknown volumes fail-closed.
- Presentation: use API counts for listing totals, update maintenance import copy consistently, share the existing guide presentation between owner preview and paid reader, preserve accepted artwork and explanatory wording.
- Tests: cover XIV private preparation, four preview assets, missing-fourth-image batch rollback, old orders/prices preserved, invalid fifteenth volume rejected, and fourteen-count import/publication on SQLite and isolated PostgreSQL.
- Production: verify base Git/health read-only, test locally, commit/push, verify release, privately save only XIV's approved price, compare first thirteen readbacks unchanged, inspect fourteen-ready hub and XIV full preview without publishing.
- Handoff: record actual test/deployment/private preparation evidence, supersede V38's exclusion and do not equate listing readiness with payment readiness.

## Verification commands and boundaries

Use `python -m pytest -q --tb=no`, targeted isolated loopback PostgreSQL tests, Python/JS syntax, incremental secret/real-price scans and `git diff --check`. Browser tests use synthetic data for positive publishing and only authenticated preview/private preparation in production. No live purchase, refund, access revocation or notification tests.
