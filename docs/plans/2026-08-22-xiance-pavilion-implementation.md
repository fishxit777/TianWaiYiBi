# Xiance Pavilion Initial Version Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local-first initial version of Tianwai Yibi Studio's xianxia-themed paid idea marketplace with a LINE Bot interface, secure admin analytics, and payment automation boundaries.

**Architecture:** A Flask application factory serves public pages, JSON endpoints, the LINE webhook, a mock payment adapter, and a server-side-session admin console. SQLite stores catalog, order, analytics, audit, and security data; integrations remain behind small adapter modules so production services can replace them later.

**Tech Stack:** Python 3.14, Flask 3.1, SQLite, Jinja, native JavaScript, CSS, pytest.

---

### Task 1: Project scaffold and database

**Files:**
- Create: `app.py`
- Create: `tianwai/__init__.py`
- Create: `tianwai/db.py`
- Create: `tianwai/schema.sql`
- Test: `tests/test_app.py`

**Steps:**
1. Write a failing app-factory health test.
2. Run `python -m pytest tests/test_app.py -q` and confirm failure.
3. Add app factory, database connection, schema initialization, and six seeded ideas.
4. Run the focused test and confirm it passes.

### Task 2: Public website and paid idea catalog

**Files:**
- Create: `tianwai/public.py`
- Create: `templates/base.html`
- Create: `templates/home.html`
- Create: `templates/idea_detail.html`
- Create: `templates/checkout.html`
- Create: `templates/order_access.html`
- Create: `static/styles.css`
- Create: `static/app.js`
- Test: `tests/test_public_flow.py`

**Steps:**
1. Write tests for homepage, published idea detail, input validation, order creation, mock payment, and paid-content access.
2. Implement the catalog and order routes with CSRF, validation, a global price setting, and immutable order price snapshots.
3. Implement the xianxia responsive pages and idea-card filtering.
4. Run public-flow tests and inspect response content.

### Task 3: Payment idempotency and LINE Bot

**Files:**
- Create: `tianwai/payments.py`
- Create: `tianwai/line_bot.py`
- Test: `tests/test_integrations.py`

**Steps:**
1. Write tests for valid payment, amount mismatch, invalid webhook signature, duplicate event ID, valid LINE signature, and duplicate LINE delivery.
2. Implement payment processing in one SQLite transaction with unique event IDs.
3. Implement LINE signature verification, local reply generation, event deduplication, and optional reply API calls only when credentials exist.
4. Run integration tests.

### Task 4: Secure admin console and analytics

**Files:**
- Create: `tianwai/security.py`
- Create: `tianwai/admin.py`
- Create: `templates/admin_login.html`
- Create: `templates/admin_dashboard.html`
- Create: `static/admin.js`
- Test: `tests/test_admin_security.py`

**Steps:**
1. Write tests for generic login failure, lockout, hashed sessions, authorization, CSRF, price change audit, sensitive-path blocking, and security-event access.
2. Add server-side admin sessions, secure cookie flags, rate limiting, persistent block records, preflight scanning, audit logs, and response security headers.
3. Add dashboard metrics, idea controls, global pricing, orders, security events, manual security test, and IP unblock endpoint.
4. Run admin/security tests and review no secret or raw session token is persisted.

### Task 5: Documentation, launch scripts, and logo preview

**Files:**
- Create: `README.md`
- Create: `HANDOFF.md`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `run_local.ps1`
- Create: `assets/logo-concepts/tianwai-yibi-xianxia-v1.png`

**Steps:**
1. Document local setup, generated temporary credentials, data location, test commands, and integration boundaries.
2. Add a launcher that generates per-process secrets when they are not explicitly set and binds only to `127.0.0.1`.
3. Generate one original deep-navy, cinnabar, jade, and old-gold xianxia logo concept; save it locally and do not deploy it.
4. Update the website to reference the local concept only after it exists.

### Task 6: Full verification

**Files:**
- Verify all Python, template, CSS, JavaScript, tests, and docs.

**Steps:**
1. Run `python -m py_compile app.py tianwai/*.py`.
2. Run `python -m pytest -q` and require all tests to pass.
3. Run `node --check static/app.js` and `node --check static/admin.js`.
4. Start the server on localhost and check `/healthz`, `/`, a detail page, checkout, mock payment, `/dev/line`, admin login, and admin dashboard.
5. Use browser visual QA at desktop and mobile widths; fix issues before delivery.
6. Update `HANDOFF.md` with verified and intentionally unconnected items.

