# Independent Content Security V32 Implementation Plan

> **For implementation:** Use the available executing-plans workflow task-by-task; the user has approved this complete batch, so routine checkpoints are progress reports rather than additional approval requests.

**Goal:** Close unauthorized paid-content access and harden TianWai-only access/alerts without changing public pricing, payment gates, or WanyuTong.

**Architecture:** Keep the existing Flask/PostgreSQL application, Passkey administration and LINE outbox. Store paid image bytes outside the public static tree and authorize each image request through the existing customer/device session plus that customer's paid order. Adopt reviewed security principles as an independent snapshot, never as a cross-project dependency.

**Tech Stack:** Flask, SQLite isolated tests, PostgreSQL-compatible additive migration, existing LINE push API, pytest.

## Approved acceptance criteria

1. Anonymous, non-owning, unpaid, expired and revoked readers cannot retrieve paid text or images, including legacy image URLs; valid buyers still receive the correct images.
2. Separate code/configuration/state/alerts/deployment, no automatic cross-project updates or fallback to another project's credentials. Record what was adopted without copying WanyuTong code or data.
3. High-risk alerts use only TianWai's private admin LINE; validate minimization, deduplication, rate controls, retries and failures. Do not revive customer messaging or rerun destructive production payment/account-recovery checks.

## Boundaries and alternatives

- Chosen: private local assets behind application authorization; this fits the existing deployment with no new storage provider or credentials. Hiding/renaming static paths is insufficient. A new signed-CDN/object-store system adds maintenance and is unnecessary for this batch.
- Preserve all existing original/retired paid images by relocating, not deleting, them. Preserve database asset identifiers and order prices to avoid unnecessary content/data migration.
- Adopt major-event alerting and routine summaries; do not copy raw request-detail notifications, old authentication shortcuts or cross-project configuration. Keep existing Passkeys and 08:00/12:00/20:00 summaries.
- No new per-image watermarking/DRM in this batch. Existing watermark remains; authorized screenshots and prior downloads cannot be recalled or guaranteed impossible.
- Price decisions stay in the ignored local analysis folder. Future ideas follow modern illustrated content first, separate pricing evaluation afterward. No public price or checkout changes.

## Task 1: Private content (root)

Files: create `tianwai/private_content.py`, `tests/test_private_content_v32.py`; modify `tianwai/__init__.py`, `templates/order_access.html`, `templates/home.html`, `templates/idea_detail.html`, `tianwai/admin.py`, relevant public/catalog assertions and `scripts/verify_public_catalog.py`.

1. Add failing tests for legacy anonymous image requests and valid-buyer slot access; run targeted pytest and capture failure counts only.
2. Relocate the 75 current/retired paid WebPs into `private_assets/brand/`, preserving hashes. Validate every source/destination remains inside this repository before moving binary files.
3. Add `/library/assets/<int:idea_id>/<slot>`: call `current_customer_session()`, parameterized paid-order ownership lookup, fixed field mapping, safe private-root resolution and `send_file(..., conditional=False, etag=False)` with no-store/no-referrer. Never accept a user-supplied filesystem path.
4. Remove real paid asset references from sealed public cards. Deny legacy static namespaces and dynamically referenced paid files even if accidentally regenerated under static. Validate admin image identifiers against existing private files, rejecting traversal/public files.
5. Test GET/HEAD/Range/If-None-Match/If-Modified-Since for authorized and unauthorized access, revoke/refund/expiry/wrong-volume states, traversal and public assets unaffected.

## Task 2: Session and code replay protection (session agent)

Files: `tianwai/access.py`, new `tests/test_session_hardening_v32.py`.

1. Write failing isolated tests for missing/wrong/revoked/expired device credentials and concurrent single-use login-code consumption.
2. Validate device-owner/token/trust on every session read, preserving the existing helper API and valid sessions.
3. Use a conditional unused/unrevoked/unexpired login-code update plus rowcount check before issuing a session.
4. Run the new tests and existing customer/device tests. No live account or recovery-code use.

## Task 3: Dedicated alert delivery (notification agent)

Files: `tianwai/notifications.py`, additive queue schema in `tianwai/db.py`, `tianwai/notification_routes.py` if required, new notification tests; only narrowly update old synthetic fixtures/expectations.

1. Write failing tests for private recipient validation, sensitive free-text omission, event-storm quotas, concurrent queue claims and bounded retry.
2. Add atomic claims/leases, persistent rate controls, bounded attempts with backoff and stable provider retry keys. Preserve legacy audit rows but never resend their old arbitrary payloads.
3. Use allowlisted messages; no raw query/path/detail/UA/customer/order identifiers or concept content. Keep safe summary aggregates and no other-project fallback.
4. Test provider success, rejection, timeout, dedup and lease recovery through mocks. Distinguish provider acceptance from delivery/read acknowledgement.

## Task 4: Integration and independent review

1. Clear external-service/database environment configuration for all tests; only temporary SQLite and mocked external I/O. Existing production data and local operational DB must remain untouched.
2. Run targeted tests, then `python -m pytest -q`, Python compile checks, JavaScript syntax checks, `pip check`, and non-echoing secret scan plus `git diff --check`.
3. Independently review changes against each acceptance criterion. At most three reported acceptance rounds; repair failures before advancing. Report unresolved boundaries, including deployed proxy-chain/secret-uniqueness checks not performed.
4. Verify no pricing/checkout/customer-messaging regressions; no WanyuTong tracked files changed by this batch.

## Task 5: Release and evidence

1. Update HANDOFF/README and the dated V32 update with exact tests, scope and remaining limits. Do not include internal prices or private data.
2. Commit scoped files and push main; no force push or unrelated edits.
3. Wait for auto-deploy and check health release, anonymous legacy/private denial, public assets and payment-closed page. Do not fetch paid image bytes anonymously, create production orders, or trigger account recovery.
4. If a controlled real LINE test is possible without owner login/secret transfer, emit at most one non-secret labelled verification alert; report API acceptance separately from actual receipt. Otherwise explicitly report this remaining owner-side verification.
5. Record final deployment evidence and verify local main/origin/main/live release synchronization. Never equate an unchanged health endpoint or historical tests with current release acceptance.
