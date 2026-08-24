# Hybrid Section Conversations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build maintainable public-plus-private conversations beneath each public content section, with stable accessible customer identity colors and centralized admin moderation.

**Architecture:** Add one additive `section_messages` table shared by SQLite and PostgreSQL, expose narrowly scoped customer/public APIs through a dedicated blueprint, and reuse one lazy-loaded Jinja/JavaScript widget across allowlisted sections. Extend the existing Passkey-protected dashboard with moderation and targeted replies; keep permissions server-side and all message rendering plain text.

**Tech Stack:** Flask, Jinja, SQLite/PostgreSQL, vanilla JavaScript, CSS, pytest.

---

### Task 1: Specify permissions and identity presentation

**Files:**
- Create: `docs/plans/2026-08-24-hybrid-section-conversations-design.md`
- Create: `docs/plans/2026-08-24-hybrid-section-conversations-implementation.md`

**Step 1:** Record the two visibility modes, moderation rule, section allowlist, anonymous alias rule, accessible color use, validation and rate limits.

**Step 2:** Confirm the design never exposes customer names, Email addresses, internal IDs, message HTML or private threads publicly.

### Task 2: Add schema and backend conversation service

**Files:**
- Modify: `tianwai/schema.sql`
- Modify: `tianwai/schema_postgres.sql`
- Create: `tianwai/conversations.py`
- Modify: `tianwai/__init__.py`
- Test: `tests/test_conversations.py`

**Step 1: Write failing schema and API tests**

Cover anonymous public reads, login-required writes, public pending moderation, private ownership isolation, body validation, deterministic aliases/colors and rate limiting.

**Step 2: Run the focused test**

Run: `python -m pytest tests/test_conversations.py -q`

Expected: FAIL because the blueprint and table do not exist.

**Step 3: Add the table and indexes**

Create `section_messages` with foreign keys to `ideas`, `customers` and itself; constrain author, visibility and status values; add public/private timeline and moderation indexes in both SQL dialects.

**Step 4: Implement the public/customer API**

Add stable section validation, anonymous public identity generation, plain-text validation, CSRF checks, customer session checks and database-enforced private filtering.

**Step 5: Run the focused tests**

Run: `python -m pytest tests/test_conversations.py -q`

Expected: PASS.

### Task 3: Add reusable section widgets

**Files:**
- Create: `templates/_conversation_widget.html`
- Modify: `templates/home.html`
- Modify: `templates/idea_detail.html`
- Modify: `templates/base.html`
- Create: `static/conversations.js`
- Modify: `static/v16.css`
- Test: `tests/test_conversations.py`

**Step 1: Write failing rendering tests**

Assert six homepage widgets, one idea detail widget, correct data attributes, accessible labels and a single deferred JavaScript include.

**Step 2: Add the shared template component**

Render a collapsed disclosure with public/private tabs, legend, timeline, empty/loading/error states and a customer-only composer.

**Step 3: Implement lazy loading and safe DOM rendering**

Use `fetch`, `textContent`, abort-safe state changes, `aria-live`, keyboard-compatible buttons and CSRF request headers. Never assign message bodies through `innerHTML`.

**Step 4: Add visual treatment**

Use the existing refined xianxia palette, fixed keeper styling, six accessible customer accents, clear name/badge labeling, mobile stacking and reduced-motion handling.

**Step 5: Run focused tests**

Run: `python -m pytest tests/test_conversations.py tests/test_public_flow.py -q`

Expected: PASS.

### Task 4: Add Passkey-protected moderation and targeted replies

**Files:**
- Modify: `tianwai/admin.py`
- Modify: `templates/admin_dashboard.html`
- Modify: `static/admin.js`
- Modify: `static/v16.css`
- Test: `tests/test_conversations.py`

**Step 1: Write failing admin tests**

Cover dashboard privacy, admin CSRF, approve, hide, public reply, private targeted reply and audit records.

**Step 2: Add dashboard data**

Return pending counts, masked/anonymous customer identity, section metadata and recent messages only to an authenticated administrator.

**Step 3: Add mutation endpoints**

Implement publish/hide and reply operations behind `admin_required` plus `admin_mutation_guard`; validate target customer and section context server-side and write audit logs.

**Step 4: Add the conversation workspace**

Provide filters, pending badges, reply composer, moderation buttons, safe text rendering and refresh behavior in the existing dashboard.

**Step 5: Run focused tests**

Run: `python -m pytest tests/test_conversations.py tests/test_admin_security.py -q`

Expected: PASS.

### Task 5: Verify security, compatibility and visuals

**Files:**
- Modify: `tests/test_database_backend.py` if schema parity assertions require it
- Modify: `docs/security-review.md`

**Step 1:** Run Python compilation.

Run: `python -m py_compile app.py tianwai/*.py`

Expected: no output and exit code 0.

**Step 2:** Run the complete suite.

Run: `python -m pytest -q`

Expected: all tests pass with only the existing environment-dependent skip.

**Step 3:** Search tracked changes for secrets and unsafe message rendering.

Run targeted `rg` checks for credential patterns, `innerHTML` use in the new script and accidental Email/private-data output.

**Step 4:** Start the local app and visually inspect desktop/mobile public widgets plus the admin moderation workspace. Fix all observed loading, overflow, focus, contrast and empty-state defects before proceeding.

### Task 6: Record, publish and verify

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/updates/2026-08-24-hybrid-section-conversations.md`

**Step 1:** Document the delivered permission model, data model, tests, deployment state and any remaining manual checks without including secrets or customer data.

**Step 2:** Review `git diff --check`, `git status` and the exact staged file list.

**Step 3:** Commit the verified feature with a scoped message.

**Step 4:** Push `main`, wait for deployment, then verify `/healthz`, anonymous public visibility, login-required private access and the rendered production widget without submitting real customer data.
