# V32 LINE Summary Repair Implementation Plan

> **Execution:** The user confirmed that existing private LINE push must work and that no new button should be added. Apply the Code / writing-plans verification workflow in this task; routine checks do not require another approval. Keep this existing project checkout and preserve all unrelated files.

**Goal:** Restore the existing production summary path after its PostgreSQL failure and reject false-green delivery results.

**Architecture:** Keep the same private LINE queue, recipient checks, endpoint, deduplication and three daily schedules. Bind SQL LIKE patterns instead of embedding literal percent characters in parameterized psycopg queries. Add a small standard-library response validator to the existing workflow, without adding a new endpoint, button, schedule or provider.

**Tech Stack:** Flask, psycopg/PostgreSQL 17.11 isolated cluster, pytest, Python standard library, existing GitHub Actions workflow.

## Evidence and acceptance

- Production scheduled run 63 on commit 3f8c1d9 failed with HTTP 500; the user reported no message today and last receipt yesterday at 22:26.
- A new full-route PostgreSQL test reproduced the invalid percent-placeholder error before any summary was created or LINE called. The earlier PostgreSQL tests did not exercise this full route.
- Acceptance 1: complete route on real isolated PostgreSQL succeeds and deduplicates, with a post-deploy real summary showing LINE API acceptance; actual receipt remains owner-confirmed.
- Acceptance 2: workflow exits nonzero for failed/skipped/pending/malformed/mismatched-slot responses and emits only allowlisted status/count fields.
- Acceptance 3: no new button, no new schedule, no payment/pricing/visual changes, no other-project changes or secret disclosure.

## Task 1: SQL regression and minimal fix

- Test: `tests/test_postgres_integration.py` covers the entire `/internal/notifications/daily-summary` route twice with synthetic data and mocked LINE.
- Modify only affected retry queries in `tianwai/notifications.py`; use bound values for both LIKE and NOT LIKE patterns. No adapter rewrite, schema migration or retry-policy change.
- Verify red then green on fresh loopback-only PostgreSQL and stop the cluster afterward.

## Task 2: Fail-closed workflow result

- Add `scripts/verify_line_summary_response.py` and `tests/test_line_summary_response.py`.
- Before implementation, test that only a valid expected-slot result with `channels.line=sent` and coherent queue/dedup counts passes; errors never echo response text.
- Modify `.github/workflows/daily-admin-summary.yml` to checkout this repository at a pinned action revision, retain the same private POST and exact cron expressions, and pipe the response through the validator under pipefail. Never follow redirects or print credentials/raw response bodies.
- Test malformed, provider failure, dedup, slot mismatch, oversized data and private-field non-echo behavior.

## Task 3: Release and verification

- Run targeted and full tests, compile check, secret scan and diff check; retain the separate actual PostgreSQL result.
- Update V32 evidence and HANDOFF, commit and push scoped files, verify the exact deployment commit and healthy release.
- Run only the existing appropriate summary workflow once after deployment. This is a normal summary, not a fake attack or new test message; its existing bounded retry behavior may process eligible recent notifications. Do not bulk-replay old alerts or create a new dedup identity.
- Verify API acceptance and ask the owner only for receipt/time, not screenshots or private contents. Record unresolved delivery evidence honestly.
- GitHub scheduled execution can be delayed; 08/12/20 remain target times, not a guaranteed wall-clock delivery SLA.
