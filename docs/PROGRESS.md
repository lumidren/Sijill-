# Progress

Resume here after a context reset: read this file and `git log --oneline`, then continue with the first unchecked item.

## Order of work (after the 2026-11-17 priority change)

Core first, fully working and demoable before anything else:

- [x] **Skeleton** — FastAPI + SQLAlchemy + Alembic, Argon2 auth, roles enforced server-side, hash-chained append-only audit log, React shell EN/AR + RTL, CI workflow, `scripts/start.ps1` / `scripts/dev.ps1`, Dockerfile + compose (not run)
- [x] **Core 1: PDPL catalog in OSCAL** — `catalog/pdpl-catalog.json`: 11 areas, 52 bilingual requirements (16 technical), all `verified=false` / `source-status=needed`; validates against the official OSCAL 1.1.3 schema; lossless round trip; admin import/reset of a reviewed catalog
- [x] **Core 2: Evidence engine** — OCSF ingestion (validation, redaction, per-target runs, SHA-256 per file and per result), Prowler framework file `compliance/prowler/pdpl_egypt_aws.json` (129 AWS checks), Linux mapping, inbox + Prowler subprocess adapters, APScheduler collection, Linux collector (`collectors/linux/`)
- [ ] **Core 3: Scoring, run history, regression detection, score-over-time dashboard** — backend done (scoring, snapshots, diffs, `/api/posture/*`, `/api/checks/*`); frontend dashboard, requirements and checks screens next
- [ ] **Core 4: One report** — readiness report + gap list, PDF (EN, AR) and OSCAL (assessment results + POA&M)
- [ ] **Core 5: Demo seed + README**
- [ ] **Assessment workflow** — answers per area, evidence upload, gap analysis
- [ ] Stretch 1: processing register
- [ ] Stretch 2: licensing questionnaire, applicability screener, obligations + reminders
- [ ] Stretch 3: breach clock
- [ ] Polish: accessibility pass, upstream Prowler contribution notes

## Verified so far

- Backend: 102 pytest tests pass, 2 skipped (live-Prowler tests; they run in CI where Prowler installs).
  Covers auth per role, CSRF header, throttling, audit chain + append-only triggers, catalog schema validation and round trip, scoring rules (cap, N/A override, staleness, roll-up), ingestion edge cases (bad JSON, wrong class, oversized, wrong type, duplicate file), credential redaction, regression detection (AWS and Linux), adapters (inbox quarantine, Prowler subprocess mocked).
- Linux collector: 15 tests replaying recorded fictional hosts, plus a static test that it only runs allow-listed read-only commands.
- Frontend: 7 vitest tests (sign-in, setup, bad credentials, Arabic RTL, role-based navigation).
- Manually: signed in through the browser as the demo DPO in Arabic; `scripts/start.ps1` ran end to end (install, build, migrate, seed, serve).
- Prowler framework files load with Prowler 5.50.0's own `load_compliance_framework`; all generated findings validate with `py_ocsf_models` `DetectionFinding` (one-off checks, see DECISIONS #8, #11).

## Not working / not verified / fixture-only

- Prowler is not installed locally (Windows path limit; DECISIONS #8). The Prowler subprocess adapter is tested with a mocked subprocess only. CI job `prowler-mapping` installs real Prowler.
- All AWS evidence is synthetic (generated in Prowler's OCSF shape); no AWS account was scanned.
- The Linux collector was run only against recorded fictional hosts, never against a real host.
- Postgres is exercised only in CI (`backend-postgres` job); not run locally.
- Docker image is built only in CI; not run locally.

## Next

Frontend: dashboard (score, trend, coverage split, gaps, regressions), requirements list + drill-down, checks/runs screens. Then the demo seed (app/demo_data.py) with weekly history.
