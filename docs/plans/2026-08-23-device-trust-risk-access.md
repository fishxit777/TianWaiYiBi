# Customer Device Trust and Risk Access Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Deliver two trusted devices, one simultaneous paid-content session, ten-minute one-time codes, rule-based risk scoring, private LINE administrator alerts, traceable watermarks, and an auditable event timeline without coupling entitlements to short-lived credentials.

**Architecture:** Extend the existing Flask modular monolith and additive SQLite migrations. Preserve paid orders as the entitlement source of truth, introduce stable internal customers and first-party device records, bind customer sessions to devices, and evaluate access events with deterministic server-side rules. Alerts are queued after the security event is committed so LINE failures never affect payment or access state.

**Tech Stack:** Python 3, Flask, SQLite, Jinja, browser Web Crypto/local storage compatible device identifiers, LINE Messaging API, pytest, vanilla JavaScript/CSS.

---

### Task 1: Baseline and schema tests

**Files:**
- Modify: `tests/test_customer_access.py`
- Modify: `tests/test_integrations.py`
- Modify: `tests/test_admin_security.py`
- Create: `tests/test_device_risk.py`

**Steps:**
1. Add failing tests for ten-minute activation/login codes, latest-code-only behavior, two trusted devices, third-device replacement, one active paid-content session, risk escalation, idempotent alerts, and masked admin payloads.
2. Run the targeted tests and confirm they fail for the missing behavior.
3. Keep fixtures independent and avoid real email, LINE, or payment calls.

### Task 2: Additive customer/device/risk schema

**Files:**
- Modify: `tianwai/schema.sql`
- Modify: `tianwai/db.py`

**Steps:**
1. Add `customers`, `customer_devices`, `access_events`, `risk_incidents`, and `notification_queue` tables plus required indexes.
2. Add customer/device references and revocation metadata to customer sessions without exposing raw tokens.
3. Backfill one internal customer per normalized paid-order email and keep existing databases compatible.
4. Run schema and migration tests.

### Task 3: Ten-minute codes and device-bound sessions

**Files:**
- Modify: `tianwai/access.py`
- Modify: `templates/activate.html`
- Modify: `templates/customer_login.html`
- Modify: `templates/customer_library.html`

**Steps:**
1. Set activation and login codes to ten minutes, one-time use, latest-code-only, five attempts, resend cooldown, and HMAC-only storage.
2. Resolve or create the internal customer after payment and activation.
3. Register at most two trusted first-party devices for thirty days.
4. Bind sessions to devices, enforce one simultaneous paid-content session, and provide an explicit session-transfer flow.
5. Keep paid entitlements intact when codes, devices, or sessions expire.
6. Run the access tests.

### Task 4: Risk engine and tamper-evident events

**Files:**
- Create: `tianwai/risk.py`
- Modify: `tianwai/security.py`
- Modify: `tianwai/access.py`
- Modify: `tianwai/payments.py`

**Steps:**
1. Record normalized events with masked customer/device/session identifiers.
2. Chain event hashes with an application-secret HMAC and verify the chain.
3. Score deterministic signals for device churn, failed codes, concurrent content, region changes, and revoked-token replay.
4. Apply low/medium/high/critical actions without labeling a customer as a criminal.
5. Run risk and regression tests.

### Task 5: Private LINE alert queue

**Files:**
- Create: `tianwai/notifications.py`
- Modify: `tianwai/line_bot.py`
- Modify: `tianwai/__init__.py`
- Modify: `.env.example`
- Modify: `render.yaml`

**Steps:**
1. Add masked administrator push messages through a TianWaiYiBi-only `LINE_ADMIN_USER_ID`.
2. Queue only high/critical events for immediate delivery; keep medium events in the dashboard.
3. Make delivery idempotent and retryable, and never include full email, IP, name, payment data, tokens, or codes.
4. Verify alert failures do not roll back payments, entitlements, or session changes.

### Task 6: Watermark and administration UI

**Files:**
- Modify: `tianwai/admin.py`
- Modify: `templates/admin_dashboard.html`
- Modify: `static/admin.js`
- Modify: `static/styles.css`
- Modify: `templates/order_access.html`

**Steps:**
1. Add dynamic masked customer/order/session watermarks to paid content.
2. Return customer, device, session, risk, incident, notification, and chain-integrity summaries from the protected admin API.
3. Add customer/device/risk sections and safe administrative actions without exposing secrets.
4. Verify responsive layout and existing six-workspace navigation.

### Task 7: Full verification, documentation, and release

**Files:**
- Modify: `README.md`
- Modify: `HANDOFF.md`
- Modify: `docs/security-review.md`
- Create: `docs/updates/2026-08-23-device-trust-risk-release.md`

**Steps:**
1. Run Python compile checks, JavaScript syntax checks, all pytest tests, and dependency checks.
2. Exercise phone-to-desktop transfer, second purchase, expired/reused code, third-device, concurrent-session, alert-failure, and watermark flows locally.
3. Review authentication, CSRF, access control, secret handling, input validation, cache policy, and privacy minimization.
4. Update the complete release/change table and handoff documentation.
5. Commit only TianWaiYiBi changes, push the private repository, verify the production health endpoint and static deployment safely, and report any external credential-only items separately.
