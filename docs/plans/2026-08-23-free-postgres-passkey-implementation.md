# Free PostgreSQL and Passkey Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move every durable business record from ephemeral SQLite to free persistent PostgreSQL, add passwordless WebAuthn administration with two independent authenticators, and retain the existing Argon2id password only as a protected emergency recovery factor.

**Architecture:** Keep the existing Flask modular monolith and Render Free web service. Add a small database adapter that preserves the existing connection API while selecting SQLite for local tests and Psycopg for `DATABASE_URL`; production uses Neon PostgreSQL. WebAuthn challenges, credentials, recovery-code hashes, sessions, orders, entitlements, alerts, and audit events all use the same durable database. Daily GitHub Actions backups use `pg_dump`, validate the archive, encrypt it to an offline public key, and retain only encrypted artifacts.

**Tech Stack:** Python 3, Flask 3.1, SQLite for local unit tests, PostgreSQL 17-compatible SQL, Psycopg 3, py_webauthn 3, Argon2id, Cloudflare Turnstile, GitHub Actions, pytest.

---

### Task 1: Add PostgreSQL compatibility without changing production yet

**Files:**
- Modify: `requirements.txt`
- Modify: `tianwai/db.py`
- Create: `tianwai/schema_postgres.sql`
- Modify: `tianwai/__init__.py`
- Test: `tests/test_database_backend.py`

**Steps:**
1. Write tests for backend selection, qmark parameter conversion, conflict-safe seed inserts, `lastrowid`, row mappings, and secret-free health responses.
2. Run the focused tests and confirm they fail before the adapter exists.
3. Add `psycopg[binary]` and a connection wrapper exposing `execute`, `executescript`, `commit`, `rollback`, and `close`.
4. Use `DATABASE_URL` only when explicitly configured; otherwise preserve current SQLite behavior.
5. Add a PostgreSQL schema with identity columns, valid foreign-key ordering, equivalent checks, and all current indexes.
6. Make additive migration inspection use `information_schema` on PostgreSQL and `PRAGMA` on SQLite.
7. Run focused tests, the full suite, Python compilation, and dependency checks.

### Task 2: Add repeatable SQLite-to-PostgreSQL migration and integrity reporting

**Files:**
- Create: `scripts/migrate_sqlite_to_postgres.py`
- Create: `scripts/verify_postgres_migration.py`
- Test: `tests/test_database_migration.py`
- Modify: `.env.example`
- Modify: `README.md`

**Steps:**
1. Write a test database containing orders, paid entitlements, sessions, devices, events, and notifications.
2. Require migration to preserve explicit IDs, foreign keys, unique values, row counts, and sequence positions.
3. Refuse destructive overwrite unless the destination contains only schema seeds or `--allow-nonempty` is explicitly supplied.
4. Produce a JSON integrity report containing table counts and checksums but no customer values, tokens, credentials, or connection strings.
5. Verify repeat runs are safe and do not duplicate rows.

### Task 3: Add WebAuthn persistence and one-time challenges

**Files:**
- Modify: `requirements.txt`
- Modify: `tianwai/schema.sql`
- Modify: `tianwai/schema_postgres.sql`
- Create: `tianwai/passkeys.py`
- Modify: `tianwai/security.py`
- Test: `tests/test_admin_passkeys.py`

**Steps:**
1. Add `admin_webauthn_credentials`, `admin_webauthn_challenges`, and `admin_recovery_codes` tables.
2. Store only credential IDs, COSE public keys, sign counters, transports, backup flags, timestamps, labels, and revocation metadata.
3. Generate 32-byte registration/authentication challenges, hash them at rest, expire them after five minutes, and consume them atomically once.
4. Require the configured RP ID, exact HTTPS origin in production, and WebAuthn user verification.
5. Treat a non-increasing sign counter as a risk signal rather than an automatic false positive for synchronized passkeys.
6. Add tests for wrong origin, wrong RP ID, expired challenge, replay, unknown credential, revoked credential, and successful verification.

### Task 4: Replace daily password login with a Passkey-first admin flow

**Files:**
- Modify: `tianwai/admin.py`
- Modify: `templates/admin_login.html`
- Create: `static/admin-passkey.js`
- Modify: `static/styles.css`
- Modify: `tianwai/security.py`
- Test: `tests/test_admin_passkeys.py`
- Test: `tests/test_admin_security.py`

**Steps:**
1. Keep the current password form only until two verified Passkeys exist.
2. Add JSON registration and authentication option/verification endpoints protected by CSRF, origin validation, IP throttling, and generic errors.
3. After two credentials are enrolled, show only the Passkey button on normal login.
4. Preserve 256-bit server-side session tokens, HttpOnly/Secure/SameSite=Strict cookies, eight-hour expiry, logout revocation, and CSRF checks.
5. Add credential inventory and revocation controls inside the authenticated admin security page.

### Task 5: Add zero-cost break-glass recovery

**Files:**
- Create: `tianwai/turnstile.py`
- Create: `templates/admin_recovery.html`
- Modify: `tianwai/admin.py`
- Modify: `tianwai/security.py`
- Modify: `tianwai/notifications.py`
- Test: `tests/test_admin_recovery.py`

**Steps:**
1. Generate ten 128-bit single-use recovery codes and persist only Argon2id hashes.
2. Require the existing Argon2id password and one unused recovery code together.
3. Require server-side Cloudflare Turnstile verification in production when recovery is enabled; tokens are never trusted client-side.
4. On success, consume the code atomically, revoke all admin sessions, queue a critical alert, and require a replacement Passkey enrollment.
5. Never transmit passwords or recovery codes through LINE, Gmail, logs, URLs, audit details, or backup reports.

### Task 6: Add encrypted free backups and hard spending limits

**Files:**
- Create: `scripts/backup_postgres.ps1`
- Create: `.github/workflows/postgres-backup.yml`
- Create: `docs/postgres-backup-recovery.md`
- Test: `tests/test_backup_workflow.py`

**Steps:**
1. Run `pg_dump --format=custom` on a daily schedule with least-privilege GitHub permissions.
2. Validate the archive with `pg_restore --list` before encryption.
3. Encrypt with an offline recipient public key; upload only the encrypted artifact for fourteen days.
4. Ensure workflow logs redact URLs and never echo passwords, customer rows, dumps, private keys, or recovery codes.
5. Document the owner-only restore drill and set GitHub Actions metered-product budget to stop usage at zero dollars.

### Task 7: Deployment configuration and staged cutover

**Files:**
- Modify: `render.yaml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `HANDOFF.md`
- Create: `docs/adr/0003-free-postgres-passkey-authentication.md`
- Create: `docs/updates/2026-08-23-free-postgres-passkey.md`

**Steps:**
1. Add secret placeholders for `DATABASE_URL`, WebAuthn RP/origin, Turnstile, and backup settings without placing values in Git.
2. Create a Neon Free production project in Singapore and a separate test project only through the owner's authenticated account.
3. Import and verify data before setting Render `DATABASE_URL`.
4. Deploy with password login still available; verify health, row counts, customer access, payment callbacks, notifications, and admin login.
5. Enroll Windows Hello and a phone Passkey with the owner present.
6. Run the recovery drill, revoke the test recovery code, then switch normal login to Passkey-only.
7. Keep the Argon2id verifier as recovery-only and retain an encrypted pre-cutover SQLite backup for thirty days.

### Task 8: Final security and operational acceptance

**Files:**
- Modify: `docs/security-review.md`
- Modify: `HANDOFF.md`

**Steps:**
1. Run full unit/integration tests, PostgreSQL integration tests, syntax compilation, JavaScript syntax checks, and dependency checks.
2. Confirm no credential, connection URL, private key, recovery code, raw session, or customer data entered Git or response bodies.
3. Exercise Windows Hello login, phone login, logout, replay rejection, expired challenge, revoked credential, recovery-code one-time use, database cold wake, and encrypted-backup validation.
4. Verify production security headers, no-store behavior, CSP allowances limited to required Turnstile endpoints, and no public admin links.
5. Commit and push only after all automated checks pass; record any owner-only enrollment or dashboard step as incomplete until actually verified.
