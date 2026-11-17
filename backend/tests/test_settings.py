import pytest


def test_settings_show_unverified_legal_defaults(as_role):
    data = as_role("auditor").get("/api/settings").json()
    keys = {d["key"]: d for d in data["legal_defaults"]}
    assert keys["breach_regulator_hours"]["value"] == 72 and keys["breach_regulator_hours"]["verified"] is False
    assert data["catalog"]["unverified"] == data["catalog"]["requirements"] == 52
    assert data["timezone"] == "Africa/Cairo"
    # credentials are never exposed, only whether something is configured
    assert set(data["aws"]) == {"profile_configured", "role_configured"}


def test_admin_updates_organisation(as_role):
    c = as_role("admin")
    r = c.put("/api/settings/organization", json={"name": "Acme Clinic", "name_ar": "عيادة أكمي", "dpo": "Dr. A"})
    assert r.status_code == 200
    assert as_role("dpo").get("/api/settings").json()["organization"]["name"] == "Acme Clinic"


@pytest.mark.parametrize("role", ["dpo", "it", "auditor"])
def test_only_admin_changes_organisation(as_role, role):
    assert as_role(role).put("/api/settings/organization", json={"name": "X"}).status_code == 403
