# V28 Policy, FAQ, and Private Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a TianWai-specific FAQ, legal policy center, private external support entry, and versioned checkout consent while public payment remains closed.

**Architecture:** Add read-only public routes and Jinja templates inside the existing Flask public blueprint. Support destinations come from validated project-specific configuration and are never stored in the database; the app exposes no customer-message API. A dedicated V28 stylesheet extends the existing sunlit xianxia design without changing payments, access control, or retired messaging routes.

**Tech Stack:** Python 3, Flask, Jinja, HTML `details`, CSS, pytest, existing browser QA.

---

### Task 1: Lock the public contract with failing tests

**Files:**
- Modify: `tests/test_public_flow.py`
- Modify: `tests/test_app.py`

**Step 1:** Add tests for `/faq`, `/policies`, `/terms`, `/privacy`, `/refunds`, `/support`, footer links, nine FAQ items, three legal sections, conditional support destinations, checkout policy links, the new terms version, payment-closed state, and retired messaging routes.

**Step 2:** Run `python -m pytest -q tests/test_app.py tests/test_public_flow.py` and confirm the new assertions fail before implementation.

### Task 2: Add validated support configuration and public routes

**Files:**
- Modify: `tianwai/__init__.py`
- Modify: `tianwai/public.py`

**Step 1:** Read `SUPPORT_EMAIL` and `SUPPORT_FORM_URL` without logging values.

**Step 2:** Validate the public email shape and require an HTTPS form URL before exposing either destination.

**Step 3:** Add FAQ, policy, alias, and support routes; keep them read-only and preserve all retired messaging endpoints as 404.

**Step 4:** Update `/healthz` release to `policy-faq-private-support-v28`.

### Task 3: Build the FAQ, legal center, and support pages

**Files:**
- Create: `templates/faq.html`
- Create: `templates/policies.html`
- Create: `templates/support.html`
- Modify: `templates/base.html`
- Modify: `templates/checkout.html`

**Step 1:** Implement nine TianWai-specific FAQ questions and answers.

**Step 2:** Implement purchase/service terms, privacy notice, and digital-content/refund rules using native accessible accordions.

**Step 3:** Implement a private-support page that only exposes validated TianWai-specific destinations and otherwise explains that the channel opens before public payment.

**Step 4:** Add desktop navigation, footer links, and checkout policy references without adding chat, comments, or customer LINE.

### Task 4: Add the V28 visual layer

**Files:**
- Create: `static/v28.css`
- Modify: `templates/base.html`

**Step 1:** Add a sunlit celestial policy shell, scroll-like accordions, chibi companion staging, focus states, mobile layout, and reduced-motion behavior.

**Step 2:** Ensure the new layer uses the readable UI font system and existing optimized assets only.

### Task 5: Version checkout consent

**Files:**
- Modify: `tianwai/public.py`
- Modify: `tianwai/admin.py`
- Modify: `tests/test_public_flow.py`

**Step 1:** Change new order consent records to `2026-08-30-v28-policy-center` for both public and isolated verification orders.

**Step 2:** Test that the two separate affirmative consents remain required and that public payment stays closed.

### Task 6: Verify locally and visually

**Files:**
- Modify only if a defect is found.

**Step 1:** Run targeted tests, then `python -m pytest -q`.

**Step 2:** Run Python compile, every JavaScript syntax check, `pip check`, `git diff --check`, forbidden-name scan, and non-content-emitting secret scan.

**Step 3:** Run isolated local Browser QA at 1440×900 and 390×844 for FAQ, policies, support, checkout, navigation, accordions, focus behavior, broken images, overflow, and console issues.

### Task 7: Connect the dedicated external destinations

**Files:**
- No secret values in repository files.

**Step 1:** Create a TianWai-only support mailbox and Google Form in the owner's authenticated Google session; do not reuse WanyuTong assets.

**Step 2:** Configure production with the public support address and form URL without printing them to terminal, documentation, or chat.

**Step 3:** Verify the support links resolve to the dedicated destinations; do not submit a production form entry.

### Task 8: Document, commit, deploy, and close the acceptance loop

**Files:**
- Create: `docs/updates/2026-08-30-policy-faq-private-support-v28.md`
- Modify: `HANDOFF.md`
- Modify: `README.md`

**Step 1:** Record all three acceptance rounds, tests, privacy boundaries, external-login result, and any unresolved legal-identity limitation.

**Step 2:** Commit implementation, push `main`, wait for `/healthz` V28, run production HTTP and desktop/mobile Browser QA, then record deployment evidence in a final documentation commit.

**Step 3:** Fetch origin and require a clean worktree with `main...origin/main` equal to `0 0` before delivery.
