# Progress

Resume here after a context reset: read this file and `git log --oneline`, then continue with the first unchecked item.

## Order of work (after the 2026-11-17 priority change)

Core first, then the assessment workflow, then the stretch goals in order:

- [x] **Skeleton**: FastAPI + SQLAlchemy + Alembic (4 migrations), Argon2 auth, roles enforced server-side, hash-chained append-only audit log, React shell EN/AR + RTL, CI workflow, `scripts/start.ps1` / `scripts/dev.ps1`, Dockerfile + compose (not run)
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

## Verified, and how

- **Backend tests**: 185 passed, 2 skipped (the two live-Prowler tests; CI runs them). Includes every role on every write endpoint, malformed/oversized/wrong-type uploads, tampered evidence, credential redaction, scoring rules, OSCAL schema validity and round trip, deadline arithmetic across midnight and Egypt's DST change, the 70-hour urgent clock and an overdue clock.
- **Frontend tests**: 28 passed (vitest + Testing Library), including Arabic RTL with Arabic-Indic digits.
- **In the running app** (built-in browser, screenshots in `docs/screenshots/`): dashboard EN + AR, requirement drill-down, run comparison with regressions, assessment answering (saved an answer and saw the new status), register, obligations and licensing, breach clock (desktop and 375 px), reports, Arabic PDF in the browser's PDF viewer.
- **Accessibility sweep** on 17 screens in the running app: no unlabelled form controls, unnamed buttons/links, duplicate ids or missing `h1`; no horizontal overflow in English, Arabic, or at 375 px. Secondary text raised to AA contrast.
- **Fresh clone**: `git clone` of the repo into an ignored folder, then `scripts/start.ps1 -Port 8010`: created the venv, installed Python and npm dependencies, built the UI, migrated, seeded and served in 80 s (pip and npm caches were already warm on this machine). All four demo roles signed in; dashboard, assessment, register, obligations, incidents, Arabic PDFs, CSV, evidence pack and POA&M all returned 200; an Auditor write returned 403. The clone was deleted afterwards.
- **Prowler framework**: loads with Prowler 5.50.0's own `load_compliance_framework`; all synthetic findings validate with `py_ocsf_models` `DetectionFinding` (one-off checks, DECISIONS #8, #11).

## Not working / not verified / fixture-only

- Prowler is not installed locally (Windows path limit; DECISIONS #8). The Prowler subprocess adapter is tested with a mocked subprocess only. CI job `prowler-mapping` installs real Prowler.
- All AWS evidence is synthetic (generated in Prowler's OCSF shape); no AWS account was scanned.
- The Linux collector ran only against recorded fictional hosts, never against a real host.
- Postgres is exercised only in CI (`backend-postgres` job); Docker image built only in CI; neither run locally.
- PDFs were inspected only in the browser's PDF viewer (poppler is a system tool; pypdfium2 could not be downloaded, PyPI timed out).
- The CI workflow has never run: there is no git remote, so nothing was pushed.
- No legal source documents were available: every requirement, the 11-area structure, the screener rules, the licence/permit list and both breach deadlines are unverified (docs/LEGAL-REVIEW.md). The notice-to-individuals default (144 h) is a placeholder.
- Reminders are in-app only (no email).

## Next

Done for this brief. Suggested next steps are in the final report and the README.
