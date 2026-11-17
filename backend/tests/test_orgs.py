"""Several client organisations in one install: each one's data stays its own."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app import audit
from app.db import org_session
from app.models import Answer, AuditLog, Organisation, Task
from tests.conftest import login

REPO = Path(__file__).resolve().parents[2]
WEEK1 = REPO / "fixtures/prowler/nour-clinic-week1.ocsf.json"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _new_org(admin, name="Delta Pharmacies") -> int:
    r = admin.post("/api/orgs", json={"name": name, "sector": "Pharmacy"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _select(c, org_id: int) -> None:
    assert c.post("/api/orgs/select", json={"id": org_id}).status_code == 200


def test_every_module_is_separated(as_role):
    admin = as_role("admin")
    second = _new_org(admin)

    # Organisation 1: one of everything
    _select(admin, 1)
    assert admin.put("/api/assessment/answers/a01-01", json={"status": "compliant", "note": "Org one"}).status_code == 200
    task = admin.post("/api/tasks", json={"title": "Org one task"}).json()
    risk = admin.post("/api/risks", json={"title": "Org one risk", "likelihood": 4, "impact": 5}).json()
    act = admin.post("/api/register", json={"role": "controller", "name": "Org one patients", "purpose": "Care"}).json()
    ev = admin.post("/api/evidence", data={"requirement_id": "a01-01", "description": "letter"},
                    files={"file": ("letter.pdf", PDF, "application/pdf")}).json()
    assert admin.post("/api/checks/import", files={"file": ("w1.ocsf.json", WEEK1.read_bytes(), "application/json")}).status_code == 200
    one = admin.get("/api/posture/dashboard").json()

    # Organisation 2 sees none of it, by list or by id
    _select(admin, second)
    assert admin.get("/api/orgs").json()["current"] == second
    assert admin.get("/api/tasks").json() == []
    assert admin.get("/api/risks").json() == []
    assert admin.get("/api/register").json() == []
    assert admin.get("/api/checks/runs").json() == []
    assert admin.get("/api/evidence?requirement_id=a01-01").json() == []
    assert admin.get(f"/api/evidence/{ev['id']}/download").status_code == 404
    assert admin.put(f"/api/tasks/{task['id']}", json={"title": "hijack"}).status_code == 404
    assert admin.put(f"/api/risks/{risk['id']}", json={"title": "hijack", "likelihood": 1, "impact": 1}).status_code == 404
    assert admin.put(f"/api/register/{act['id']}", json={"role": "controller", "name": "hijack", "purpose": "x"}).status_code == 404
    two = admin.get("/api/posture/dashboard").json()
    assert two["organization"]["name"] == "Delta Pharmacies"
    assert two["counts"]["by_basis"].get("automated", 0) == 0
    assert two["overall"] != one["overall"] or two["counts"] != one["counts"]
    a = next(r for r in admin.get("/api/posture").json()["requirements"] if r["id"] == "a01-01")
    assert a["status"] == "not_assessed"

    # The same requirement can be answered differently per organisation
    assert admin.put("/api/assessment/answers/a01-01", json={"status": "non_compliant", "note": "Org two"}).status_code == 200
    _select(admin, 1)
    a = next(r for r in admin.get("/api/posture").json()["requirements"] if r["id"] == "a01-01")
    assert a["status"] == "compliant"
    assert [t["title"] for t in admin.get("/api/tasks").json()] == ["Org one task"]


def test_users_only_open_their_organisations(as_role, app_client):
    admin = as_role("admin")
    second = _new_org(admin)
    dpo_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "dpo")
    assert admin.patch(f"/api/users/{dpo_id}", json={"access": [second]}).status_code == 200
    assert admin.patch(f"/api/users/{dpo_id}", json={"access": [999]}).status_code == 400
    assert admin.patch(f"/api/users/{dpo_id}", json={"access": []}).status_code == 400

    app_client.cookies.clear()
    dpo = login(app_client, "dpo")
    orgs = dpo.get("/api/orgs").json()
    assert [o["id"] for o in orgs["items"]] == [second] and orgs["current"] == second
    assert dpo.post("/api/orgs/select", json={"id": 1}).status_code == 403
    # A forged cookie falls back to an organisation the user may open
    dpo.cookies.set("pdpl_org", "1")
    assert dpo.get("/api/orgs").json()["current"] == second
    assert dpo.post("/api/tasks", json={"title": "Pharmacy task"}).status_code == 201
    assert [o["id"] for o in dpo.get("/api/orgs/overview").json()["items"]] == [second]
    assert dpo.post("/api/orgs", json={"name": "x"}).status_code == 403

    with org_session(1) as s:
        assert s.execute(select(Task)).scalars().all() == []
    with org_session(second) as s:
        assert [t.title for t in s.execute(select(Task)).scalars()] == ["Pharmacy task"]


def test_user_without_any_organisation_is_refused(as_role, app_client):
    admin = as_role("admin")
    second = _new_org(admin)
    it_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "it")
    admin.patch(f"/api/users/{it_id}", json={"access": [second]})
    admin.patch(f"/api/orgs/{second}", json={"archived": True})
    app_client.cookies.clear()
    it = login(app_client, "it")
    assert it.get("/api/tasks").status_code == 403
    assert it.get("/api/tasks").json()["detail"] == "no_organisation_access"


def test_overview_ranks_each_client(as_role):
    admin = as_role("admin")
    second = _new_org(admin, "Sphinx Dental")
    _select(admin, second)
    admin.post("/api/tasks", json={"title": "Late", "due_on": (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()})
    admin.post("/api/risks", json={"title": "Big", "likelihood": 5, "impact": 5})
    items = {o["name"]: o for o in admin.get("/api/orgs/overview").json()["items"]}
    assert set(items) == {"My organisation", "Sphinx Dental"}
    dental = items["Sphinx Dental"]
    assert dental["tasks_overdue"] == 1 and dental["risks_high"] == 1
    assert dental["counts"]["total"] > 0 and dental["last_run"] is None
    assert items["My organisation"]["tasks_overdue"] == 0


def test_manage_organisations(as_role):
    admin = as_role("admin")
    second = _new_org(admin)
    renamed = admin.patch(f"/api/orgs/{second}", json={"name": "Delta Pharmacies Ltd"}).json()
    assert renamed["name"] == "Delta Pharmacies Ltd"
    _select(admin, second)
    assert admin.get("/api/settings").json()["organization"]["name"] == "Delta Pharmacies Ltd"
    # The profile form renames the organisation in the switcher too
    admin.put("/api/settings/organization", json={"name": "Delta Pharma"})
    assert {o["name"] for o in admin.get("/api/orgs").json()["items"]} == {"My organisation", "Delta Pharma"}
    assert admin.patch(f"/api/orgs/{second}", json={"archived": True}).status_code == 200
    assert admin.patch("/api/orgs/1", json={"archived": True}).status_code == 400  # last active one
    assert [o["id"] for o in admin.get("/api/orgs").json()["items"]] == [1]
    assert len(admin.get("/api/orgs/all").json()) == 2
    assert as_role("dpo").get("/api/orgs/all").status_code == 403


def test_collectors_feed_one_organisation(as_role):
    admin = as_role("admin")
    second = _new_org(admin)
    assert admin.get("/api/checks/collectors").json()["active_here"] is True
    _select(admin, second)
    data = admin.get("/api/checks/collectors").json()
    assert data["active_here"] is False and data["collect_org_id"] == 1
    assert admin.post("/api/checks/collect").status_code == 409


def test_audit_log_is_per_organisation_and_still_verifies(as_role, db):
    admin = as_role("admin")
    second = _new_org(admin)
    admin.post("/api/tasks", json={"title": "In org one"})
    _select(admin, second)
    admin.post("/api/tasks", json={"title": "In org two"})
    actions = [(e["action"], e["detail"].get("title")) for e in admin.get("/api/audit").json()["items"]]
    assert ("organisation.create", None) in actions  # install-wide events show everywhere
    titles = {t for a, t in actions if a.startswith("task")}
    assert "In org one" not in titles
    assert admin.get("/api/audit/verify").json() == {"ok": True, "first_bad_id": None}
    rows = db.execute(select(AuditLog).where(AuditLog.action.like("task%"))).scalars().all()
    assert sorted(r.org_id for r in rows) == [1, second]
    # Moving an entry to another organisation breaks the chain
    assert audit._digest(rows[0].prev_hash, rows[0].at.isoformat(), rows[0].actor_name, rows[0].action,
                         rows[0].entity_type, rows[0].entity_id, rows[0].detail, second) != rows[0].hash


def test_org_session_stamps_and_filters(db):
    db.add(Organisation(id=2, name="Two"))
    db.commit()
    with org_session(2) as s:
        s.add(Answer(requirement_id="a01-01", status="compliant"))
        s.commit()
    with org_session(1) as s:
        s.add(Answer(requirement_id="a01-01", status="partial"))
        s.commit()
        assert [a.status for a in s.execute(select(Answer)).scalars()] == ["partial"]
        assert s.get(Answer, 1) is None  # the other organisation's row, by primary key
    with org_session(2) as s:
        assert [(a.org_id, a.status) for a in s.execute(select(Answer)).scalars()] == [(2, "compliant")]


def test_demo_has_three_clients(app_client):
    from app.demo import DEMO_PASSWORD, seed_demo

    assert "2 more fictional clients" in seed_demo(reset=True)
    r = app_client.post("/api/auth/login", json={"username": "admin", "password": DEMO_PASSWORD})
    assert r.status_code == 200
    items = {o["name"]: o for o in app_client.get("/api/orgs/overview").json()["items"]}
    assert list(items) == ["Nour Family Clinic", "Delta Pharmacies", "Sphinx Dental Centre"]
    nour, delta, sphinx = items.values()
    assert nour["counts"]["technical_automated"] > 0
    assert delta["counts"]["by_basis"].get("automated", 0) == 0 and delta["counts"]["by_basis"]["attested"] > 40
    assert delta["tasks_overdue"] == 1 and delta["vendors_without_dpa"] == 1
    assert sphinx["counts"]["by_status"]["not_assessed"] > 40


def test_cli_imports_into_a_chosen_organisation(db, capsys, monkeypatch):
    import os

    from app import cli

    if os.environ.get("PDPL_TEST_DATABASE_URL"):  # the CLI opens its own engine; point it at the test database
        monkeypatch.setenv("DATABASE_URL", os.environ["PDPL_TEST_DATABASE_URL"])

    db.add(Organisation(id=2, name="Two"))
    db.commit()
    assert cli.main(["import-findings", str(WEEK1), "--org", "2"]) == 0
    assert "into Two" in capsys.readouterr().out
    assert cli.main(["import-findings", str(WEEK1), "--org", "9"]) == 2
    from app.models import CheckRun

    with org_session(1) as s:
        assert s.execute(select(CheckRun)).scalars().all() == []
    with org_session(2) as s:
        assert len(s.execute(select(CheckRun)).scalars().all()) == 1
    assert cli.main(["orgs"]) == 0
    assert "Two" in capsys.readouterr().out
