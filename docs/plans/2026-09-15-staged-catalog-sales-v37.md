# Staged Catalog Sales V37 Implementation Plan

> Execute the user-approved three acceptance criteria within TianWaiYiBi only. This plan contains no unpublished prices or customer data.

**Goal:** Prepare the first thirteen volumes privately, separate price publication from purchasing, and leave all production sales closed.

**Architecture:** Add per-volume prepared price, three-state release status and a manual release-readiness check. Keep the current publication flag for sealed catalogue visibility and the existing payment-readiness master gate. Use a single server-side commerce decision for HTML, API and order creation; existing order amounts and paid entitlements remain independent.

**Tech Stack:** Flask/Jinja, SQLite/PostgreSQL, existing admin JavaScript/CSS, pytest.

## Approved acceptance criteria

1. Private preparation and authenticated previews for volumes I–XIII only; anonymous HTML/API/JavaScript must not disclose unpublished prices. Volume XIV is excluded from the price batch.
2. Per-volume preparing → price-listed → for-sale states, with explicit confirmation for publication and readiness required for sales. No direct checkout/API bypass; the existing global payment switch remains closed.
3. Reuse existing detail pages and payment/access flows; preserve old order amount snapshots, entitlements, private content protection and current visual/readability conventions.

## Task 1: Fail-closed data and policy

- Modify `tianwai/schema.sql`, `tianwai/schema_postgres.sql`, `tianwai/db.py`; add `tianwai/commerce.py`.
- Add additive, restart-safe fields `prepared_price`, `sale_state`, `release_ready`, defaulting to no price, preparing, false. Never seed actual prices in Git or infer commercial readiness from published content.
- Write isolated tests for fresh databases, additive upgrades, invalid prices/states, and restart preservation. Run the focused tests before and after implementation.
- The state policy must return no public price for preparing and allow new orders only for an explicitly ready, published, for-sale volume with a valid prepared price and the existing global payment readiness.

## Task 2: Private management and public boundaries

- Modify `tianwai/admin.py`, `tianwai/public.py`.
- Provide authenticated, no-store GET/POST `/admin/api/ideas/<id>/commerce` with the existing mutation guard and explicit publication confirmation.
- Provide atomic POST `/admin/api/commerce/prepare`, validating exactly the thirteen allowed volumes and preserving all non-commerce data. Import the approved prices only through private management after public protections are deployed.
- Update homepage/detail/API/checkout/order creation consistently. Omit unpublished prices rather than hiding them in CSS, DOM attributes or JSON.
- Test CSRF/authentication, malformed inputs, disallowed batch volumes, no partial updates, state/payment matrix, stale order amounts and existing access behavior.

## Task 3: Existing UI integration

- Modify `templates/home.html`, `templates/idea_detail.html`, `templates/checkout.html`, `templates/admin_dashboard.html`, `static/admin.js`; add `static/v37-commerce.css` if needed.
- Reuse standalone product detail pages, with price-listed and not-for-sale states explicitly distinguished. Preserve the anonymous-interest path and sealed content.
- Use a focused private commerce editor with draft price, delivery preview, limits, readiness checklist and impact confirmation. No extra public popup or second catalogue.
- Test keyboard focus, unsaved changes, errors, state labels, desktop and mobile layout. Use synthetic data only for screenshots and local positive-flow tests.

## Task 4: Verification and deployment

- Update `tianwai/__init__.py` release to `staged-catalog-sales-v37` and relevant release tests.
- Run `python -m pytest -q --tb=no`, Python compile checks, JavaScript syntax checks, dependency check, `git diff --check`, and redacted secret/unpublished-price scans.
- Use isolated PostgreSQL integration for the additive migration and commerce queries; do not repeat production backup/Passkey/payment/refund tests.
- Complete up to three acceptance rounds, documenting failures and corrections truthfully.
- Commit only implementation/tests/non-sensitive documentation, push, verify deployment and public routes, then import approved prices privately while preserving preparing/false states.
- Verify production catalogue count, no public prices or checkout forms, expected release, and main/origin/remote synchronization. Do not submit real orders or generate notifications.

## Explicit non-goals and release limits

- No customer data access, real payments, new LINE messages, recovered secrets, credentials changes, destructive migration, or cross-project coupling.
- No automatic completion of the commercial delivery attachments or legal/support launch prerequisites. Administrative readiness remains unchecked until independently completed.
- No new price for volume XIV; its current visual delivery and entitlement remain intact.
- If owner authentication is required for private import, stop that specific step and request login; do not claim all thirteen prices were stored remotely without read-back evidence.
