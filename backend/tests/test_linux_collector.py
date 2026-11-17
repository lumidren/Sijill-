"""Tests for the dependency-free Linux collector, replayed against recorded host fixtures."""
import ast
import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COLLECTOR = REPO / "collectors" / "linux" / "pdpl_linux_collector.py"
HOSTS = REPO / "fixtures" / "linux"

spec = importlib.util.spec_from_file_location("pdpl_linux_collector", COLLECTOR)
col = importlib.util.module_from_spec(spec)
spec.loader.exec_module(col)

OPTS = Namespace(hostname=None, min_log_retention_days=90)
NOW = 1_794_000_000


def collect(host, **kw):
    opts = Namespace(**{**vars(OPTS), **kw})
    return {f["metadata"]["event_code"]: f for f in col.collect(col.FixtureProbe(str(HOSTS / host)), opts, now=NOW)}


def statuses(host, **kw):
    return {k: v["status_code"] for k, v in collect(host, **kw).items()}


def test_every_check_runs_and_reports_once():
    out = collect("clinic-db-01")
    assert set(out) == set(col.CHECKS) == set(col.RUNNERS)


def test_hardened_host_passes_everything():
    assert set(statuses("clinic-db-01").values()) == {"PASS"}


def test_regressed_host_differs_by_exactly_one_check():
    before, after = statuses("clinic-db-01"), statuses("clinic-db-01-week3")
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"linux_ssh_password_auth_disabled"}
    assert after["linux_ssh_password_auth_disabled"] == "FAIL"


def test_weak_host_fails_the_expected_checks():
    s = statuses("clinic-web-01")
    assert s["linux_time_sync_enabled"] == "PASS"
    assert all(v == "FAIL" for k, v in s.items() if k != "linux_time_sync_enabled")
    msg = collect("clinic-web-01")["linux_pending_security_updates"]["message"]
    assert "3 security updates" in msg and "tzdata" not in msg  # non-security update ignored


def test_host_without_tools_reports_manual_not_pass_or_fail():
    assert set(statuses("minimal-host").values()) == {"MANUAL"}


def test_log_retention_threshold_is_configurable():
    assert statuses("clinic-db-01", min_log_retention_days=180)["linux_log_retention_configured"] == "FAIL"
    assert statuses("clinic-web-01", min_log_retention_days=28)["linux_log_retention_configured"] == "PASS"


def test_output_has_the_ocsf_shape_the_engine_ingests():
    f = collect("clinic-web-01")["linux_firewall_enabled"]
    assert f["class_uid"] == 2004 and f["status_code"] == "FAIL"
    assert f["metadata"]["product"]["uid"] == "sijill-linux"
    assert f["resources"][0]["uid"] == "clinic-web-01"
    assert f["time"] == NOW and f["time_dt"].endswith("Z")
    assert f["finding_info"]["uid"] and f["severity"] in {"Low", "Medium", "High", "Critical", "Informational"}
    json.dumps(f)  # serialisable


def test_logrotate_parser_reads_only_global_settings():
    text = "daily\nrotate 30\n/var/log/app.log {\n  rotate 1\n  weekly\n}\n"
    assert col._logrotate_days(text) == 30
    assert col._logrotate_days("monthly\n") == 120  # default rotate 4


def test_sshd_config_fallback_when_sshd_t_unavailable(tmp_path):
    host = tmp_path / "h"
    (host / "fs/etc/ssh/sshd_config.d").mkdir(parents=True)
    (host / "fs/etc/ssh/sshd_config").write_text(
        "Include /etc/ssh/sshd_config.d/*.conf\nPermitRootLogin yes\nMatch User backup\n  PasswordAuthentication yes\n")
    (host / "fs/etc/ssh/sshd_config.d/50-cloud.conf").write_text("PermitRootLogin no\nPasswordAuthentication no\n")
    s = statuses(str(host))
    # first value wins and the included drop-in comes first; Match blocks are ignored
    assert s["linux_ssh_root_login_disabled"] == "PASS"
    assert s["linux_ssh_password_auth_disabled"] == "PASS"


def test_a_crashing_check_becomes_manual(monkeypatch):
    def boom(probe, opts):
        raise RuntimeError("probe exploded")
    monkeypatch.setitem(col.RUNNERS, "linux_firewall_enabled", boom)
    f = collect("clinic-db-01")["linux_firewall_enabled"]
    assert f["status_code"] == "MANUAL" and "RuntimeError" in f["message"]


def test_cli_writes_a_file(tmp_path):
    out = tmp_path / "f.json"
    assert col.main(["--fixture", str(HOSTS / "clinic-web-01"), "--output", str(out), "--time", str(NOW)]) == 0
    data = json.loads(out.read_text())
    assert len(data) == len(col.CHECKS)


READ_ONLY_PROGRAMS = {"lsblk", "sshd", "systemctl", "auditctl", "timedatectl", "ufw", "nft", "iptables", "apt-get", "dnf"}


def test_collector_only_runs_read_only_commands():
    """Static guarantee: every probe.run([...]) uses an allow-listed program with read-only arguments."""
    tree = ast.parse(COLLECTOR.read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run":
            arg = node.args[0]
            if isinstance(arg, ast.List):
                calls.append([e.value if isinstance(e, ast.Constant) else "?" for e in arg.elts])
    assert calls, "no commands found"
    for cmd in calls:
        assert cmd[0] in READ_ONLY_PROGRAMS, cmd
        if cmd[0] == "systemctl":
            assert cmd[1] == "is-active"
        if cmd[0] == "apt-get":
            assert "-s" in cmd  # simulate only
        if cmd[0] == "dnf":
            assert "--cacheonly" in cmd and "upgrade" not in cmd
        if cmd[0] == "ufw":
            assert cmd[1:] == ["status"]
        if cmd[0] == "iptables":
            assert cmd[1:] == ["-S"]
        if cmd[0] == "nft":
            assert cmd[1:] == ["list", "ruleset"]


@pytest.mark.parametrize("bad", ["import requests", "import yaml", "import psutil"])
def test_collector_has_no_third_party_imports(bad):
    assert bad not in COLLECTOR.read_text(encoding="utf-8")
