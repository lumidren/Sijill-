"""The demo seed must keep telling a coherent story."""
from app.demo import DEMO_PASSWORD, seed_demo
from app.evidence_files import verify
from app.models import EvidenceFile
from app.posture import current_score, open_regressions, snapshots


def test_demo_seed_story(db):
    assert "Nour Family Clinic" in seed_demo(reset=True)
    trend = [s.overall for s in snapshots(db)]
    assert len(trend) >= 8
    # the score climbs over the weeks, then dips in the latest scan
    assert trend[-1] < max(trend) and max(trend) > trend[0] + 0.2
    regs = open_regressions(db)
    assert {r["check_id"] for r in regs} >= {"s3_bucket_public_access", "s3_bucket_level_public_access_block"}
    counts = current_score(db).counts()
    # half-finished assessment: some answered, some not, every technical requirement has automated evidence
    assert counts["by_basis"]["attested"] >= 20 and counts["by_basis"]["not_assessed"] >= 5
    assert counts["technical_automated"] == counts["technical_total"] == 16
    assert counts["stale"] > 0 and counts["capped"] > 0
    # evidence files are stored with matching hashes
    files = db.query(EvidenceFile).all()
    assert len(files) >= 3 and all(verify(f) for f in files)


def test_demo_seed_does_not_overwrite_real_data(db):
    seed_demo(reset=True)
    assert "skipped" in seed_demo(only_if_empty=True)
    assert "not empty" in seed_demo()


def test_demo_users_can_sign_in(app_client):
    seed_demo(reset=True)
    for user in ("admin", "dpo", "it", "auditor"):
        r = app_client.post("/api/auth/login", json={"username": user, "password": DEMO_PASSWORD})
        assert r.status_code == 200
