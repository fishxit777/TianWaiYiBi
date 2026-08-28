# Analytics Traffic Integrity V2 Implementation Plan

**Goal:** Separate public, attributable, unattributed, admin-preview, automated, and legacy analytics sessions without deleting historical data or claiming sessions are people.

**Architecture:** Add a fixed trusted-signal baseline and a protected admin preview session. Apply the same classification helpers to the demand radar, admin dashboard, and daily summary so every surface uses one definition.

**Tech Stack:** Flask, signed Flask Session, SQLite/PostgreSQL-compatible parameterized SQL, vanilla JavaScript, pytest.

---

### Task 1: Lock the classification contract with tests

**Files:**
- Modify: `tests/test_demand_radar.py`
- Modify: `tests/test_admin_notifications.py`
- Modify: `tests/test_admin_security.py`

**Steps:**
1. Add failing tests for the trusted baseline, session classes, protected preview entry, and wording.
2. Run the focused tests and confirm the new assertions fail before implementation.

### Task 2: Add trusted baseline and protected preview state

**Files:**
- Modify: `tianwai/__init__.py`
- Modify: `tianwai/analytics.py`
- Modify: `tianwai/admin.py`
- Modify: `templates/admin_dashboard.html`

**Steps:**
1. Add a configurable trusted baseline with a production default of 2026-08-29 00:00 Asia/Taipei.
2. Add an authenticated `/admin/preview` route that writes an eight-hour signed preview marker and redirects only to the homepage.
3. Make event source classification prefer a valid preview marker over public query input.
4. Replace the dashboard preview link with the protected route.

### Task 3: Use one classification in all metrics

**Files:**
- Modify: `tianwai/analytics.py`
- Modify: `tianwai/notifications.py`
- Modify: `tianwai/admin.py`
- Modify: `static/admin.js`

**Steps:**
1. Exclude pre-baseline events from demand conclusions while retaining a legacy-excluded count.
2. Count distinct sessions for sources and quality categories.
3. Rename visitor claims to work-session language and expose attributable/unattributed context.
4. Run focused tests until green.

### Task 4: Verify and deliver

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/updates/2026-08-27-demand-radar-v1.md`
- Modify: `README.md`

**Steps:**
1. Run the full pytest suite, Python compile, JavaScript syntax, dependency, diff, and secret checks.
2. Review access control, redirects, session handling, SQL parameters, and response privacy.
3. Update release documentation, commit, push, and verify production `/healthz` plus public-sale closure.
