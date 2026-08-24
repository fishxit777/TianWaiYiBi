# External-Attacker Defense and Disaster-Recovery Implementation Plan

**Status:** Completed and production-verified on 2026-08-24. GitHub Actions run `32696239051` succeeded; PostgreSQL 17.11 restore completed with 24 tables, 164 rows, and every per-table checksum matching. Plaintext and the disposable cluster were deleted after verification.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete a recoverable encrypted PostgreSQL backup while optimizing the security model for hostile outsiders rather than treating the owner or the local operator as adversaries.

**Architecture:** Preserve Passkey-only administration, Turnstile recovery, least-privilege database access, and public-key-encrypted GitHub artifacts. Remove the mandatory human-memorized private-key passphrase from the default offline recovery path: an RSA-4096 private key remains exclusively on a removable offline USB, while GitHub receives only its public key. Restore into a loopback-only disposable PostgreSQL 17 cluster, compare table counts and canonical SHA-256 checksums, then destroy plaintext and the test cluster.

**Tech Stack:** Python 3.14, cryptography 50.0.0, psycopg 3.3.4, PostgreSQL 17.11, PowerShell, GitHub Actions, Neon PostgreSQL.

---

## Threat-model decision

The protected assets are the production website, administrator access, the Neon database, and the ability to recover after malicious deletion. The primary adversary is an external attacker who compromises Render, GitHub, an application endpoint, or a cloud credential. Physical USB theft and a hostile owner/operator are out of scope under the owner's revised instruction.

Three options were evaluated:

1. Keep a human-entered private-key passphrase. Strongest against physical theft, but it adds a human availability dependency that does not reduce the specified remote website threat.
2. Store an encrypted private key and its unlock secret together on the same USB. It looks stronger but gives little real protection if that USB is stolen and adds recovery complexity.
3. Use a passwordless PKCS#8 RSA-4096 private key on an offline removable USB. This is the selected option because GitHub/Render/Neon compromise still cannot obtain the private key, daily backups remain fully encrypted, and disaster recovery has no memorized-secret failure point.

Compensating controls: verify the destination is a removable drive outside OneDrive/Git, keep GitHub limited to the public key, use a read-only backup database role, keep the USB disconnected outside backup-recovery operations, and never upload the private key.

### Task 1: Make passwordless offline key generation explicit and safe

**Files:**
- Modify: `scripts/generate_backup_keypair.py`
- Modify: `scripts/decrypt_backup.py`
- Modify: `scripts/backup_crypto.py`
- Test: `tests/test_backup_workflow.py`

**Steps:**

1. Add failing tests requiring RSA keys to be at least 4096 bits and covering an explicitly requested passwordless PKCS#8 private key.
2. Run `python -m pytest -q tests/test_backup_workflow.py` and confirm the new tests fail.
3. Add an explicit `--offline-passwordless` generator option; retain encrypted passphrase mode as the default for other threat models.
4. Let the decryption CLI auto-detect an unencrypted private key without prompting, while continuing to prompt for encrypted keys.
5. Raise the accepted RSA minimum from 3072 to 4096 bits.
6. Re-run the backup tests and Python compilation.

### Task 2: Add PostgreSQL-to-PostgreSQL integrity verification

**Files:**
- Create: `scripts/verify_postgres_backup_restore.py`
- Create: `tests/test_backup_restore_verifier.py`

**Steps:**

1. Write tests for deterministic canonical row hashing, schema/table discovery, mismatch reporting, and secret-free report output.
2. Run the new tests and confirm they fail before implementation.
3. Implement read-only snapshots of every ordinary table in the selected schema using parameterized identifiers, canonical JSON rows, counts, and SHA-256 checksums.
4. Compare a source URL and restore URL supplied only through environment variables; print no connection values or row data.
5. Run the verifier tests and compile the script.

### Task 3: Provision offline RSA-4096 material

**Files:**
- Create outside Git: `D:\TWYB-Offline\backup-private.pem`
- Create outside Git: `D:\TWYB-Offline\backup-public.pem`

**Steps:**

1. Confirm `D:` is a physical removable USB and neither key exists.
2. Run the explicit passwordless offline generator.
3. Verify the public key is RSA-4096 and matches the private key without printing either key.
4. Verify Git tracks no private key, dump, or encrypted artifact.

### Task 4: Prepare a disposable local PostgreSQL 17 recovery environment

**Files:**
- Modify: `.gitignore`
- Download outside OneDrive: `_local/postgresql-17.11-binaries.zip`
- Extract outside OneDrive: `_local/postgresql-17.11/`
- Runtime data outside OneDrive: Windows temporary directory

**Steps:**

1. Ignore `_local/` so portable runtime files cannot enter Git.
2. Download the PostgreSQL 17.11 Windows binaries from EDB over HTTPS to the resolved non-OneDrive path.
3. Verify the archive is a valid ZIP and record its local SHA-256 in the private execution log only.
4. Extract `pg_dump`, `pg_restore`, `initdb`, `pg_ctl`, `createdb`, `dropdb`, and `psql` with their runtime dependencies.
5. Initialize a disposable cluster bound only to `127.0.0.1` on a nonstandard port with local trust authentication.

### Task 5: Connect least-privilege GitHub backup secrets

**External state:**
- Neon: backup-only read role/connection
- GitHub Actions secrets: `NEON_BACKUP_DATABASE_URL`, `BACKUP_PUBLIC_KEY_PEM`

**Steps:**

1. Confirm the Neon connection used by the workflow cannot create, update, or delete production rows and can read all current public tables.
2. At the final browser boundary, identify that the database URL and RSA public key will be transmitted to the private GitHub repository as encrypted Actions secrets.
3. Set the two secrets without showing their values in chat, logs, documents, or screenshots.
4. Verify only the secret names and update timestamps are visible.

### Task 6: Run and inspect the encrypted production backup

**External state:**
- GitHub Actions workflow: `Encrypted PostgreSQL backup`
- Downloaded artifact outside OneDrive

**Steps:**

1. Manually dispatch the workflow from `main`.
2. Wait for a successful run and inspect its logs for plaintext paths, accidental connection-string output, or upload of anything except `.twybenc`.
3. Download the artifact outside OneDrive.
4. Verify the artifact contains exactly one `.twybenc`, begins with `TWYBPG01`, stays below 25 MB, and contains no recognized plaintext marker.

### Task 7: Decrypt, restore, and prove integrity

**Runtime files:**
- Encrypted artifact outside OneDrive
- Plaintext dump in a dedicated Windows temporary directory only
- Disposable PostgreSQL cluster on loopback only

**Steps:**

1. Decrypt with the offline USB private key and verify `pg_restore --list` succeeds.
2. Restore into a new disposable database, never the production database.
3. Compare production and restored schemas with the verifier, reporting only table names, counts, checksums, and verified/mismatch state.
4. Confirm the total table count, total row count, and every table checksum.
5. Stop PostgreSQL, verify exact temporary paths, and delete the plaintext dump and disposable cluster.
6. Keep the encrypted artifact as the DR evidence copy outside OneDrive; disconnect the private-key USB after completion.

### Task 8: Security regression, documentation, and delivery

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/updates/2026-08-23-free-postgres-passkey.md`
- Modify: `docs/postgres-backup-recovery.md`
- Modify: `README.md` only where stale status remains

**Steps:**

1. Run targeted backup/verifier tests, the complete pytest suite, Python compilation, JavaScript syntax checks, `pip check`, and `git diff --check`.
2. Scan tracked filenames and repository contents for private keys, connection URLs, passwords, recovery codes, dumps, and artifacts without printing matches containing secret values.
3. Record factual run ID, artifact metadata, table/row/checksum verification, cleanup result, and any remaining limitation without storing credentials or row values.
4. Re-check production `/healthz` and ensure Passkeys/recovery codes were untouched.
5. Commit only audited source/document changes and push `main` to `origin/main`.
