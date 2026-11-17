# Progress

Resume here after a context reset: read this file and `git log --oneline`, then continue with the first unchecked item.

## Order of work (after the 2026-11-17 priority change)

Core first, fully working and demoable before anything else:

- [ ] **Skeleton** — repo layout, FastAPI + SQLAlchemy + Alembic, Argon2 auth, roles (Admin/DPO/IT/Auditor) enforced server-side, hash-chained append-only audit log, React shell with EN/AR + RTL, CI workflow, `scripts/dev.ps1` / `scripts/start.ps1`
- [ ] **Core 1: PDPL catalog in OSCAL** — 11 areas, requirements, bilingual, `verified: false` markers, schema-validated
- [ ] **Core 2: Evidence engine** — OCSF findings ingestion, PDPL→check mapping, Prowler compliance framework file, Prowler subprocess + file-import adapters, Linux collector
- [ ] **Core 3: Scoring, run history, regression detection, score-over-time dashboard** (with automated / self-attested / not-assessed split)
- [ ] **Core 4: One report** — readiness report + gap list, PDF (EN, AR if shaping works) and OSCAL (assessment results + POA&M)
- [ ] **Core 5: Demo seed + README** covering the above
- [ ] **Assessment workflow** — answers per area, evidence upload, gap analysis
- [ ] Stretch 1: processing register (controller/processor exports)
- [ ] Stretch 2: licensing questionnaire, applicability screener, obligations + renewal reminders
- [ ] Stretch 3: breach clock (72 h countdown, notification templates)
- [ ] Polish: accessibility pass, Dockerfile + compose (written, not run), Prowler upstream contribution notes

## Verified so far

- Backend: 17 pytest tests pass (login per role, throttling, CSRF header, admin-only user management, audit chain verification, append-only enforced by ORM events and SQLite triggers).
- Frontend: 7 vitest tests pass (sign-in, first-admin setup, bad credentials, Arabic RTL switch, admin nav hidden from non-admins, auditor read-only badge). `vite build` succeeds.
- Ran the app on 127.0.0.1:8000 and signed in through the browser as the demo DPO; found and fixed a bug where the language chosen on the sign-in page was overwritten by the profile language.

## Not working / not verified / skipped

- Prowler install into `.venv-prowler` was interrupted by a session restart and restarted; result pending.

## Next

Finish skeleton (CI workflow, run scripts), then Core 1.
