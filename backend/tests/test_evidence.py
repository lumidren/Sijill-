import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import demo_aws
from app.evidence import ocsf
from app.evidence.adapters import InboxAdapter, ProwlerCliAdapter
from app.evidence.service import DuplicateImport, import_findings
from app.models import Answer, CheckResult
from app.posture import current_score, open_regressions

REPO = Path(__file__).resolve().parents[2]
WEEK1 = REPO / "fixtures/prowler/nour-clinic-week1.ocsf.json"
WEEK6 = REPO / "fixtures/prowler/nour-clinic-week6.ocsf.json"
LINUX_WEB = REPO / "fixtures/linux-output/clinic-web-01.ocsf.json"
MB = 1024 * 1024


def upload(client, path_or_bytes, name="findings.ocsf.json", ctype="application/json"):
    raw = path_or_bytes.read_bytes() if isinstance(path_or_bytes, Path) else path_or_bytes
    return client.post("/api/checks/import", files={"file": (name, raw, ctype)})


def status_of(client, req_id):
    return next(r for r in client.get("/api/posture").json()["requirements"] if r["id"] == req_id)


# ------------------------------------------------------------------ parsing

def test_parse_prowler_fixture():
    (batch,) = ocsf.parse(WEEK1.read_bytes(), 5 * MB)
    assert (batch.provider, batch.target) == ("aws", demo_aws.ACCOUNT)
    assert len(batch.findings) == 152
    f = batch.findings[0]
    assert f.check_id and f.status in {"PASS", "FAIL"} and f.observed_at.tzinfo and len(f.sha256) == 64


def test_parse_linux_collector_output():
    (batch,) = ocsf.parse(LINUX_WEB.read_bytes(), 5 * MB)
    assert (batch.provider, batch.target) == ("linux", "clinic-web-01")


def test_mixed_file_is_split_per_target():
    items = json.loads(WEEK1.read_text()) + json.loads(LINUX_WEB.read_text())
    batches = ocsf.parse(json.dumps(items).encode(), 5 * MB)
    assert sorted((b.provider, b.target) for b in batches) == [("aws", demo_aws.ACCOUNT), ("linux", "clinic-web-01")]


@pytest.mark.parametrize("raw,code", [
    (b"{not json", "bad_json"),
    (b'{"a": 1}', "not_findings"),
    (b"[]", "empty_findings"),
    (b'[{"metadata": {}, "status_code": "PASS", "time": 1}]', "not_findings"),
    (b'[{"metadata": {"event_code": "x"}, "status_code": "MAYBE", "time": 1}]', "not_findings"),
    (b'[{"metadata": {"event_code": "x"}, "status_code": "PASS", "class_uid": 3001, "time": 1}]', "not_findings"),
    (b'[{"metadata": {"event_code": "x y z"}, "status_code": "PASS", "time": 1}]', "not_findings"),
    (b'[{"metadata": {"event_code": "x"}, "status_code": "PASS"}]', "not_findings"),
    (b'[1, 2]', "not_findings"),
])
def test_malformed_findings_rejected(raw, code):
    with pytest.raises(ocsf.FindingsError) as e:
        ocsf.parse(raw, MB)
    assert e.value.code == code


def test_oversized_file_rejected():
    with pytest.raises(ocsf.FindingsError) as e:
        ocsf.parse(b"[" + b" " * 2000 + b"]", 1000)
    assert e.value.code == "too_large"


def test_credentials_are_redacted():
    item = json.loads(WEEK1.read_text())[0]
    item["status_detail"] = ("User backup-bot has access key AKIAIOSFODNN7EXAMPLE; "
                             "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY leaked")
    (batch,) = ocsf.parse(json.dumps([item]).encode(), MB)
    msg = batch.findings[0].message
    assert "AKIAIOSFODNN7EXAMPLE" not in msg and "wJalrXUtnFEMI" not in msg
    assert "[redacted" in msg


def test_millisecond_and_iso_timestamps():
    item = json.loads(LINUX_WEB.read_text())[0]
    item["time"] = 1_794_000_000_000
    (b,) = ocsf.parse(json.dumps([item]).encode(), MB)
    assert b.findings[0].observed_at.year == 2026
    del item["time"]
    item["finding_info"].pop("created_time")
    item["time_dt"] = "2026-11-01T10:00:00Z"
    (b,) = ocsf.parse(json.dumps([item]).encode(), MB)
    assert b.findings[0].observed_at == datetime(2026, 11, 1, 10, tzinfo=timezone.utc)


# ------------------------------------------------------------------ API + scoring

def test_import_changes_requirement_status(as_role):
    c = as_role("it")
    assert status_of(c, "a06-06")["status"] == "not_assessed"
    r = upload(c, WEEK1)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 152
    s = status_of(c, "a06-06")
    assert s["status"] == "compliant" and s["basis"] == "automated"
    assert status_of(c, "a07-03")["status"] == "non_compliant"  # threat detection all off in week 1


def test_failing_check_caps_a_compliant_answer(as_role, db, users):
    db.add(Answer(requirement_id="a06-04", status="compliant", updated_by_id=users["dpo"].id,
                  updated_at=datetime.now(timezone.utc)))
    db.commit()
    c = as_role("it")
    assert status_of(c, "a06-04")["status"] == "compliant"
    upload(c, WEEK1)
    s = status_of(c, "a06-04")
    assert s["status"] == "partial" and s["capped"] and s["reason"] == "capped_by_failing_checks"
    detail = c.get("/api/posture/requirements/a06-04").json()
    assert any(ch["status"] == "FAIL" for ch in detail["checks"])
    assert detail["answer"]["status"] == "compliant"


def test_regression_flagged_and_score_dips(as_role, db):
    c = as_role("it")
    # week 5 state then week 6 (regression) for the same account
    upload(c, demo_aws.findings_bytes(5, datetime(2026, 11, 9, 8, tzinfo=timezone.utc)), "w5.ocsf.json")
    before = c.get("/api/posture").json()["overall"]
    upload(c, WEEK6, "w6.ocsf.json")
    after = c.get("/api/posture").json()["overall"]
    assert after < before
    regs = c.get("/api/checks/regressions").json()
    checks = {(r["check_id"], r["resource"]) for r in regs}
    assert ("s3_bucket_public_access", "arn:aws:s3:::nour-patient-scans") in checks
    assert all(r["requirements"] for r in regs)
    hist = c.get("/api/posture/history").json()
    assert len(hist) == 2 and hist[1]["overall"] < hist[0]["overall"]
    runs = c.get("/api/checks/runs").json()
    assert runs[0]["regressions"] == 4 and runs[0]["previous_run_id"] == runs[1]["id"]


def test_linux_regression_detected(db):
    from argparse import Namespace
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("col", REPO / "collectors/linux/pdpl_linux_collector.py")
    col = module_from_spec(spec)
    spec.loader.exec_module(col)
    opts = Namespace(hostname=None, min_log_retention_days=90)
    for i, host in enumerate(["clinic-db-01", "clinic-db-01-week3"]):
        out = col.collect(col.FixtureProbe(str(REPO / "fixtures/linux" / host)), opts, now=1_790_000_000 + i * 604800)
        import_findings(db, json.dumps(out).encode(), f"{host}.json", None, "upload")
    db.commit()
    regs = open_regressions(db)
    assert [(r["check_id"], r["target"]) for r in regs] == [("linux_ssh_password_auth_disabled", "clinic-db-01")]
    assert regs[0]["requirements"] == ["a06-05"]


def test_duplicate_file_rejected(as_role):
    c = as_role("admin")
    assert upload(c, LINUX_WEB).status_code == 200
    assert upload(c, LINUX_WEB).status_code == 409


@pytest.mark.parametrize("role", ["auditor", "dpo"])
def test_only_admin_and_it_can_import(as_role, role):
    c = as_role(role)
    assert upload(c, LINUX_WEB).status_code == 403
    assert c.post("/api/checks/collect").status_code == 403


def test_wrong_type_and_malformed_uploads(as_role):
    c = as_role("it")
    assert upload(c, b"MZ\x90\x00binary", "tool.exe", "application/x-msdownload").status_code == 415
    assert upload(c, b"{bad", "x.json").status_code == 422
    r = upload(c, b"[]", "x.json")
    assert r.status_code == 422 and r.json()["detail"] == "empty_findings"


def test_oversized_upload_rejected(as_role, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    c = as_role("it")
    r = upload(c, LINUX_WEB)
    assert r.status_code == 413 and r.json()["detail"] == "too_large"


def test_each_result_is_hashed_and_timestamped(as_role, db):
    upload(as_role("it"), LINUX_WEB)
    results = db.query(CheckResult).all()
    assert len(results) == 12
    assert all(len(r.sha256) == 64 and r.observed_at.tzinfo for r in results)


def test_run_detail_and_mapping_endpoints(as_role):
    c = as_role("auditor")
    as_role("it")
    upload(c, WEEK1)
    c = as_role("auditor")
    runs = c.get("/api/checks/runs").json()
    detail = c.get(f"/api/checks/runs/{runs[0]['id']}").json()
    assert detail["results"][0]["status"] == "FAIL"  # failures first
    assert detail["diff"]["previous_run_id"] is None
    mapping = c.get("/api/checks/mapping").json()
    assert len(mapping) == 16 and all(m["checks"] for m in mapping)
    assert c.get("/api/checks/runs/9999").status_code == 404


def test_import_is_audited(as_role):
    c = as_role("it")
    upload(c, LINUX_WEB)
    actions = [e["action"] for e in as_role("admin").get("/api/audit").json()["items"]]
    assert "checks.import" in actions


# ------------------------------------------------------------------ adapters

def test_inbox_adapter_imports_and_quarantines(db, tmp_path):
    (tmp_path / "good.json").write_bytes(LINUX_WEB.read_bytes())
    (tmp_path / "bad.json").write_text("{nope")
    result = InboxAdapter(tmp_path).collect(db)
    assert result.runs == 1 and result.status == "error"
    assert (tmp_path / "processed" / "good.json").exists()
    assert (tmp_path / "failed" / "bad.json").exists()
    assert current_score(db).counts()["by_basis"]["automated"] > 0


def test_prowler_adapter_skips_without_binary_or_credentials(db, monkeypatch):
    for var in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        monkeypatch.delenv(var, raising=False)
    a = ProwlerCliAdapter()
    monkeypatch.setattr(a, "binary", lambda: None)
    assert a.collect(db).detail == "prowler_not_installed"
    monkeypatch.setattr(a, "binary", lambda: "/usr/bin/prowler")
    assert a.collect(db).detail == "no_aws_credentials_in_environment"


def test_prowler_adapter_runs_subprocess_and_imports_output(db, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        outdir = Path(cmd[cmd.index("--output-directory") + 1])
        (outdir / "sijill.ocsf.json").write_bytes(WEEK1.read_bytes())
        return subprocess.CompletedProcess(cmd, 3, "", "")  # 3 = scan ok, some checks failed

    a = ProwlerCliAdapter(runner=fake_run)
    monkeypatch.setattr(a, "binary", lambda: "/usr/bin/prowler")
    monkeypatch.setattr(a.settings, "aws_profile", "audit-readonly")
    monkeypatch.setattr(a.settings, "aws_role_arn", None)
    result = a.collect(db)
    assert result.status == "ok" and result.runs == 1
    cmd = calls[0]
    assert cmd[:2] == ["/usr/bin/prowler", "aws"] and "json-ocsf" in cmd
    assert cmd[cmd.index("--profile") + 1] == "audit-readonly"
    assert "s3_bucket_public_access" in cmd and "linux_firewall_enabled" not in cmd
    assert not any(part.startswith(("AKIA", "ASIA")) or "secret_access_key" in part.lower()
                   or part in ("--aws-access-key-id", "--aws-secret-access-key") for part in cmd)


def test_prowler_adapter_reports_crash(db, monkeypatch):
    a = ProwlerCliAdapter(runner=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    monkeypatch.setattr(a, "binary", lambda: "/usr/bin/prowler")
    monkeypatch.setattr(a.settings, "aws_profile", "p")
    assert a.collect(db).status == "error"


def test_collectors_endpoint_reports_adapter_state(as_role):
    data = as_role("auditor").get("/api/checks/collectors").json()
    names = {a["adapter"] for a in data["adapters"]}
    assert names == {"inbox", "prowler"}
    assert data["interval_hours"] >= 1
