# Complete Release Packages V38 Implementation Plan

**Goal:** Deliver thirteen complete, private concept-reading packages with prepared prices, leaving only a deliberate publish action to the owner.

**Architecture:** Reuse all 39 approved images and original texts. Add structured, per-volume research handoff content shared by authenticated administrative previews and paid readers. Add an authenticated release catalogue and atomic single/batch publishing; publishing exposes sealed clues and the prepared price, never full content or a payment-gate override.

**Tech Stack:** Existing Flask/Jinja, SQLite/PostgreSQL, vanilla JavaScript, CSS, pytest. Work in the user-designated independent repository; no parallel repository or new service.

## Acceptance criteria

1. I–XIII each has the existing three figures, full original text, six-step illustrated reading guide, scope/specification proposals, Micro-MVP steps, test matrix, substantive worksheets, handoff template and approved private price. No blank price or import task is left to the owner. XIV is not repriced or changed.
2. Normal administration shows package completeness, price, preview and one-action publication. Legacy raw-input/price/state forms are maintenance-only, collapsed by default. Preview and buyer content share the same supplemental document source.
3. Before owner publication, new prices remain private. Administrative previews/assets require current admin authentication. Publishing never grants paid entitlements, marks legal/operational readiness complete, rewrites old orders or enables the global payment gate.

## Task 1: Build substantive packages

- Add `tianwai/release_packages_a.py` for I–VII and `tianwai/release_packages_b.py` for VIII–XIII, using identical structured schemas.
- Audit actual existing images/text and the local pricing document's delivery gaps. Preserve existing accepted images and XIV. Retain original text except a narrowly justified safety correction to XI's old motor-imbalance demonstration; only an exact legacy seed may be migrated.
- Supply six flow steps and six MVP steps, figure-specific notes, at least five specification and handoff entries, six test cases, three populated worksheets and primary-source references per volume.
- Use proposal/example/blank-result labels. Do not invent performance, supplier quotations, clinical accuracy, field safety, manufacturability or completed prototypes.
- Validate schemas, lengths, nonempty cells, source URLs and all actual image files.

## Task 2: Private preparation and publishing backend

- Add `tianwai/release_packages.py`: aggregate loaders, content/readiness checks and no public export of package bodies.
- Extend `tianwai/admin.py`: dedicated private release catalogue, full package preview, authenticated image routes, single/all-thirteen publish endpoints.
- Use existing admin session, mutation guard, no-store headers, transaction locking and whitelist. Full batch validation precedes updates; errors cannot cause partial publication.
- Publish only sealed listing/price. Never automatically set `release_ready` or enable payment; preserve existing for-sale state if already authorized. Missing content/price blocks publication with specific gaps.
- Test unauthorized preview/assets, traversal, missing assets, required confirmation, CSRF, idempotence, atomicity, exclusion and old-order independence.

## Task 3: Clear release hub and shared reading document

- Add `templates/admin_package_preview.html`, `templates/_release_package_body.html`, `static/v38-release.js`, `static/v38-release.css`.
- Update `templates/admin_dashboard.html` to show the release hub first and collapse legacy editing tools. Single/all publication has clear adjacent disclosure of the effect, no price input or state selector in the normal flow.
- Update `templates/order_access.html` to include the same supplemental package for the first thirteen volumes; retain existing payment/session/device/watermark protection and XIV's approved reader unchanged.
- Update application template globals and release tag to `complete-release-packages-v38` without seeding actual prices into source.
- Test loading, unavailable API, double clicks, server validation errors, keyboard navigation, mobile reading/table overflow and draft public-source confidentiality.

## Task 4: Verification and handoff

- The thirteen confirmed prices are imported through the already authenticated private V37 preparation flow and read back against the local target-price column. No publication or payment occurs.
- Run full pytest, isolated PostgreSQL tests relevant to publication, compile/JavaScript checks, secret/private-price scans and git diff checks.
- Inspect every package and image correspondence; use local synthetic data for positive publishing tests, not real public publication or transactions.
- Commit/push, confirm deployment/health/private readbacks and public hidden-price boundaries. Update HANDOFF and a factual acceptance report, recording any unverified prerequisites.

## Important scope distinctions

The deliverable is a complete concept/research reading package, not completed engineering, an executable simulator or verified financial return. Proposed specifications and empty observation logs are explicitly distinguished from measured results. One-action publication does not certify operator identity, tax handling, support readiness or legal terms, and does not bypass the existing payment closure.
