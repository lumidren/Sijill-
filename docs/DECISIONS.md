# Decisions

One line per decision: what was chosen, why, and the alternative that was not taken.

| # | Decision | Why | Alternative |
|---|----------|-----|-------------|
| 1 | Backend venv uses the 64-bit Python 3.12 (`py -3.12`), not the 32-bit `python` on PATH. | Several wheels (argon2, pydantic-core) and Prowler expect 64-bit; the PATH `python` is 32-bit. | Using PATH `python` and building wheels from source. |
| 2 | Prowler is installed into a separate `.venv-prowler`, not the app venv. | Prowler pins many libraries; isolating it avoids version fights with FastAPI/Pydantic, and the adapter runs it as a subprocess anyway. | One shared venv. |
| 3 | OSCAL 1.1.3 schemas are vendored from the NIST GitHub release; JSON Schema `pattern` keywords are evaluated with the `regex` package. | The schemas use `\p{L}` Unicode classes, which Python's `re` cannot compile. | Skipping pattern checks, or a Node-based validator. |
| 4 | Priority change (2026-11-17, from the project owner): core first — catalog, evidence engine, scoring/drift/dashboard, one report, demo seed + README — then the assessment workflow; processing register, licensing tracker and breach clock become stretch goals in that order. | Owner instruction mid-build. | Original 8-phase order. |
| 5 | A thin skeleton (auth, roles, audit log, i18n/RTL, app shell) is still built before the catalog. | Every core screen needs login, role checks and i18n from the first string; retrofitting i18n was explicitly ruled out. | Building the catalog with no shell. |
| 6 | Primary users are compliance consultants / DPOs serving several small organizations, plus in-house IT teams. Tenancy stays one organization per install; a consultant runs one install (one `PDPL_DATA_DIR`) per client. | Keeps the settled single-tenant model and its simple access control while still serving multi-client consultants. | Multi-tenant data model. |
| 7 | The headline number is called a "readiness score", always shown with the split of automated / self-attested / not-assessed requirements, and never labelled "legal compliance". | Automated checks only cover technical safeguards; owner asked not to overstate. | Calling it a compliance score. |
