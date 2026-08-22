# V13 Brand, LINE Bot, Website and Admin Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Deliver a locally runnable first version that applies the approved V13 cultivation brand, provides a LINE-compatible guided catalog, and lets an authenticated administrator manage each idea and inspect business/security data.

**Architecture:** Extend the existing Flask modular monolith. Keep public, LINE, payment, admin and security boundaries; add no external runtime dependency and no database-destructive migration.

**Tech Stack:** Python 3, Flask 3.1, SQLite, Jinja, vanilla CSS/JavaScript, pytest.

**Execution note:** This local project is not a Git repository, so verification replaces commit checkpoints. No deploy, credential entry or public upload is included.

---

### Task 1: Establish the baseline and copy approved brand assets

**Files:**
- Copy: `assets/brand-kit-v13/*` to `static/brand/`
- Modify: `templates/base.html`
- Modify: `templates/admin_login.html`
- Modify: `templates/admin_dashboard.html`

1. Run the current automated tests.
2. Copy only reusable V13 PNG assets into Flask static storage.
3. Replace old text/glyph marks and favicons with the approved no-text logo assets.

### Task 2: Upgrade the public website

**Files:**
- Modify: `templates/home.html`
- Modify: `templates/idea_detail.html`
- Modify: `templates/checkout.html`
- Modify: `templates/order_access.html`
- Modify: `static/styles.css`
- Modify: `static/app.js`

1. Use the V13 hero and celestial brush visual system without obscuring conversion copy.
2. Preserve all six distinct idea products, pricing and checkout behavior.
3. Add visible mock/initial-version disclosures and responsive behavior.
4. Verify keyboard focus, reduced motion, contrast and mobile layout.

### Task 3: Build a LINE-ready guided catalog

**Files:**
- Modify: `tianwai/line_bot.py`
- Modify: `templates/line_simulator.html`
- Modify: `static/app.js`
- Test: `tests/test_integrations.py`

1. Add a message builder supporting welcome/help, catalog, price and numbered product commands.
2. Return a Flex carousel for the catalog and text messages for simple answers.
3. Keep signature verification on the raw body and event-id deduplication.
4. Let the local simulator render text and product cards from the same response model.

### Task 4: Add per-idea content management

**Files:**
- Modify: `tianwai/admin.py`
- Modify: `templates/admin_dashboard.html`
- Modify: `static/admin.js`
- Modify: `static/styles.css`
- Test: `tests/test_admin_security.py`

1. Include editable idea fields and integration status in the dashboard payload.
2. Add an authenticated CSRF-protected update endpoint with type, length and enum validation.
3. Build an accessible edit drawer/modal for title, role, discipline, summaries, deliverables, tags, accent, sort order and optional price override.
4. Write an audit entry for every successful content update.

### Task 5: Harden, document and verify

**Files:**
- Modify: `tianwai/security.py`
- Modify: `README.md`
- Modify: `HANDOFF.md`
- Modify: `docs/security-review.md`
- Test: `tests/*.py`

1. Recheck request-size, CSP, admin cache policy and sensitive-path behavior.
2. Run `python -m py_compile` for application modules.
3. Run `node --check` for both JavaScript files.
4. Run `pytest -q` and require all tests to pass.
5. Start the local server and verify home, idea, checkout, LINE simulator, admin login/dashboard and responsive layouts in the browser.
