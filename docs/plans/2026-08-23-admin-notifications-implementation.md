# Admin Dual-Channel Notifications Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver detailed admin-only summaries three times per day and immediate LINE plus Gmail alerts for abnormal events, with privacy minimization, retries, and duplicate prevention.

**Architecture:** Extend the existing SQLite notification queue into a generic two-channel dispatcher. A secret-protected internal Flask endpoint builds a Taiwan-time business summary and queues both channels. GitHub Actions calls the endpoint at 08:00, 12:00, and 20:00 Asia/Taipei. High/critical access and security events invoke the same dispatcher immediately.

**Tech Stack:** Python 3, Flask, SQLite, SMTP, LINE Messaging API, GitHub Actions, pytest.

---

### Task 1: Specify observable behavior with tests

**Files:**
- Create: `tests/test_admin_notifications.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_device_risk.py`

1. Add test configuration for a dedicated admin alert email and schedule secret.
2. Test secret rejection, valid summary delivery, detailed sections, and privacy exclusions.
3. Test per-slot/per-channel idempotency.
4. Test high-risk events create separate LINE and email rows.
5. Run the new test module and confirm expected failures before implementation.

### Task 2: Build the generic notification service

**Files:**
- Modify: `tianwai/notifications.py`
- Modify: `tianwai/mailer.py`

1. Add masked recipients, privacy-safe event formatting, and Taipei timestamps.
2. Add generic queue insertion and independent LINE/email delivery.
3. Build daily metrics and both concise and detailed summary bodies.
4. Make retry processing support both channels while preserving the existing admin API.
5. Prevent alert-email failure recursion and preserve failed delivery evidence.

### Task 3: Add the protected scheduler endpoint

**Files:**
- Create: `tianwai/notification_routes.py`
- Modify: `tianwai/__init__.py`
- Modify: `render.yaml`

1. Add POST-only endpoint with constant-time schedule-secret comparison.
2. Accept only the fixed `morning`, `noon`, and `evening` slots.
3. Return counts and readiness only; never return message bodies or secrets.
4. Register the blueprint and add `ADMIN_ALERT_EMAIL` and `NOTIFICATION_CRON_SECRET` deployment variables.

### Task 4: Connect immediate anomaly sources

**Files:**
- Modify: `tianwai/risk.py`
- Modify: `tianwai/security.py`
- Modify: `tianwai/mailer.py`

1. Pass access-event context to the dual-channel alert composer.
2. Queue high/critical general security events after their database transaction commits.
3. Queue a system-delivery alert when transactional customer email fails, without recursive email alerts.
4. Verify no raw code, token, complete email, full IP, or secret reaches queued payloads.

### Task 5: Add external schedule and operator visibility

**Files:**
- Create: `.github/workflows/daily-admin-summary.yml`
- Modify: `README.md`
- Modify: `docs/security-review.md`

1. Add UTC cron schedules matching 08:00, 12:00, and 20:00 Taiwan time plus manual dispatch.
2. Call the production endpoint with a GitHub Actions secret and fail on non-2xx responses.
3. Document required variables, delivery semantics, privacy rules, manual test, and retry steps.

### Task 6: Verify, release, and record

**Files:**
- Modify: `tianwai/__init__.py`
- Create: `docs/updates/2026-08-23-admin-notifications.md`
- Modify: `HANDOFF.md` if present

1. Run `python -m py_compile` for application modules.
2. Run the full pytest suite.
3. Run security-focused source checks and local endpoint smoke tests.
4. Update the health release marker and detailed change log.
5. Commit, push, configure deployment secrets where existing authenticated access permits, and verify the production health marker and endpoint protection.
