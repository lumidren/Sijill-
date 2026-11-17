# Progress

Resume here after a context reset: read this file and `git log --oneline`, then continue with the first unchecked item.

## Order of work (after the 2026-11-17 priority change)

Core first, then the assessment workflow, then the stretch goals in order:

- [x] **Skeleton**: FastAPI + SQLAlchemy + Alembic (7 migrations), Argon2 auth, roles enforced server-side, hash-chained append-only audit log, React shell EN/AR + RTL, CI workflow, `scripts/start.ps1` / `scripts/dev.ps1`, Dockerfile + compose (not run)
- [x] **Core 1: PDPL catalog in OSCAL**: `catalog/pdpl-catalog.json`, 11 areas, 52 bilingual requirements (16 technical), all `verified=false` / `source-status=needed`; validates against the official OSCAL 1.1.3 schema; lossless round trip; admin import/reset of a reviewed catalog
- [x] **Core 2: Evidence engine**: OCSF ingestion (validation, redaction, per-target runs, SHA-256 per file and per result), Prowler framework file (129 AWS checks), Linux mapping (12 checks), inbox + Prowler subprocess adapters, APScheduler collection, read-only Linux collector
- [x] **Core 3: Scoring, run history, regression detection, score-over-time dashboard**, with the automated / self-attested / not-assessed split and drill-down to each failing resource
- [x] **Core 4: Reports**: readiness report + gap list as PDF (EN and shaped RTL Arabic) and CSV, OSCAL assessment results + POA&M (schema-valid), OSCAL AR import round trip, evidence pack ZIP with SHA-256 manifest
- [x] **Core 5: Demo seed + README**: Nour Family Clinic (fictional): half-finished assessment, 6 weekly AWS + Linux scans with one regression, register, licences nearing renewal, one open breach with the clock running
- [x] **Assessment workflow**: per-area answers with notes, evidence upload, cap warnings, progress
- [x] Stretch 1: processing register with completeness hints and controller/processor exports
- [x] Stretch 2: applicability screener, licensing questionnaire ("likely required"), obligations tracker, renewal reminders, dashboard deadlines
- [x] Stretch 3: breach clock (regulator + individuals countdowns, escalation, timeline, EN/AR notice templates, PDF)
- [x] Polish: settings screen, accessibility and layout pass (contrast, labels, RTL and phone-width overflow), upstream Prowler notes, screenshots
- [x] **Evidence requests** (DECISIONS #40-42): private links for client staff, review before anything counts, accepted files become evidence; consultant list/detail pages, recipient page in English and Arabic, "Ask the client" from any requirement, answers to review on the Clients page
- [x] **Several organisations per install** (DECISIONS #34-38): automatic org scoping on every ORM query, migration 0006 moving existing data to organisation 1, organisation switcher, Clients page, per-account access, per-organisation audit trail, collectors bound to one organisation, `import-findings --org`, two more fictional demo clients, AWS test lab for the owner to run; day counts in Cairo time
- [x] **Governance extension** (DECISIONS #28-33): remediation tasks feeding the POA&M and PDF, risk register with heat map and expiring Admin acceptance, requests from individuals with response clocks, vendor/processor register, DPIAs with screening and approval, versioned policy library, TOTP two-step sign-in with QR setup and Admin reset, dashboard governance card, related records on the drill-down, demo data for all of it

## Verified, and how

- **Backend tests**: 237 passed, 2 skipped (the two live-Prowler tests; CI runs them). Includes every role on every write endpoint, malformed/oversized/wrong-type uploads, tampered evidence, credential redaction, scoring rules, OSCAL schema validity and round trip, deadline arithmetic across midnight and Egypt's DST change, the 70-hour urgent clock and an overdue clock.
- **Frontend tests**: 49 passed (vitest + Testing Library), including Arabic RTL with Arabic-Indic digits and the two-step sign-in flow.
- **Evidence requests in the running app**: created a request from requirement A05.04, opened the link with no account, answered, attached a file, sent; reviewed and accepted as the consultant; the file appeared under A05.04 credited to the sender and the audit chain still verified. Screenshot `docs/screenshots/evidence-request-link.jpg`.
- **Organisations**: migration 0006 run on a copy of the existing demo database (all rows moved to organisation 1, named "Nour Family Clinic"; audit chain still verifies); demo re-seeded with three clients; in the running app checked the Clients page, opening Delta Pharmacies (dashboard, tasks and collectors all switched), English and Arabic at 375 px with no overflow or unlabelled controls; screenshot `docs/screenshots/clients.jpg`.
- **Governance in the running app**: migrated a fresh database, seeded the demo, and checked the dashboard card, risk register, requests, DPIAs and vendors (Arabic) in the built-in browser; screenshots in `docs/screenshots/`.
- **In the running app** (built-in browser, screenshots in `docs/screenshots/`): dashboard EN + AR, requirement drill-down, run comparison with regressions, assessment answering (saved an answer and saw the new status), register, obligations and licensing, breach clock (desktop and 375 px), reports, Arabic PDF in the browser's PDF viewer.
- **Accessibility sweep** on 17 screens in the running app: no unlabelled form controls, unnamed buttons/links, duplicate ids or missing `h1`; no horizontal overflow in English, Arabic, or at 375 px. Secondary text raised to AA contrast.
- **Fresh clone**: `git clone` of the repo into an ignored folder, then `scripts/start.ps1 -Port 8010`: created the venv, installed Python and npm dependencies, built the UI, migrated, seeded and served in 80 s (pip and npm caches were already warm on this machine). All four demo roles signed in; dashboard, assessment, register, obligations, incidents, Arabic PDFs, CSV, evidence pack and POA&M all returned 200; an Auditor write returned 403. The clone was deleted afterwards.
- **Prowler framework**: loads with Prowler 5.50.0's own `load_compliance_framework`; all synthetic findings validate with `py_ocsf_models` `DetectionFinding` (one-off checks, DECISIONS #8, #11).

## Not working / not verified / fixture-only

- Prowler is not installed locally (Windows path limit; DECISIONS #8). The Prowler subprocess adapter is tested with a mocked subprocess only. CI job `prowler-mapping` installs real Prowler.
- All AWS evidence is synthetic (generated in Prowler's OCSF shape); no AWS account was scanned. `scripts/aws-lab` is ready for the owner to run against their own account; it was only syntax-checked here.
- The Linux collector ran only against recorded fictional hosts, never against a real host.
- Postgres is exercised only in CI (`backend-postgres` job); Docker image built only in CI; neither run locally.
- PDFs were inspected only in the browser's PDF viewer (poppler is a system tool; pypdfium2 could not be downloaded, PyPI timed out).
- The CI workflow has never run: there is no git remote, so nothing was pushed.
- No legal source documents were available: every requirement, the 11-area structure, the screener rules, the licence/permit list and both breach deadlines are unverified (docs/LEGAL-REVIEW.md). The notice-to-individuals default (144 h) is a placeholder.
- Reminders are in-app only (no email).
- Organisation scoping relies on the ORM: raw SQL would bypass it (there is none in the app today). Postgres runs of migration 0006 happen only in CI.
- Two-step sign-in was tested with RFC 6238 vectors and mocked UI flows, not with a real authenticator app on a phone.
- The request-response period (30 days), risk bands and DPIA screening rule are placeholders or practice conventions, not verified law.

## Next

Done for this brief. Suggested next steps are in the final report and the README.
