#!/usr/bin/env python3
"""PDPL-Ready Linux evidence collector.

Read-only. Standard library only (Python 3.6+). Runs on the host being assessed and prints
findings as a JSON array of OCSF "Detection Finding" objects - the same shape as Prowler's
JSON-OCSF output - so PDPL-Ready ingests both the same way.

It never changes the system: it reads configuration files and runs read-only commands
(lsblk, sshd -T, systemctl is-active, ufw status, nft list ruleset, iptables -S,
apt-get -s upgrade, dnf --cacheonly updateinfo, auditctl -l, timedatectl show).
Run as root for complete results (sshd -T and auditctl need it); without root some checks
report MANUAL instead of guessing.

Usage:
  sudo python3 pdpl_linux_collector.py --output host-findings.ocsf.json
  python3 pdpl_linux_collector.py --fixture tests/fixtures/linux/web-01   # replay a recorded host
Then import the file in PDPL-Ready (Automated checks > Import findings) or drop it in the inbox folder.
"""
import argparse
import fnmatch
import glob
import json
import os
import re
import socket
import stat
import subprocess
import sys
import time

COLLECTOR_VERSION = "0.1.0"
PRODUCT_UID = "pdpl-ready-linux"
SEVERITY_IDS = {"informational": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}

# Each check: (id, title, severity, description, remediation)
CHECKS = {
    "linux_disk_encryption_enabled": (
        "Filesystems holding data are on encrypted volumes", "high",
        "Mounted data filesystems (/, /home, /var, /srv, /data) should sit on dm-crypt/LUKS volumes.",
        "Encrypt data volumes with LUKS (cryptsetup) or use encrypted cloud volumes."),
    "linux_ssh_root_login_disabled": (
        "SSH does not allow direct root login", "high",
        "PermitRootLogin should be 'no' so administrators log in as themselves and escalate.",
        "Set 'PermitRootLogin no' in /etc/ssh/sshd_config and reload sshd."),
    "linux_ssh_password_auth_disabled": (
        "SSH requires keys, not passwords", "medium",
        "PasswordAuthentication should be 'no' to block password guessing.",
        "Set 'PasswordAuthentication no' in /etc/ssh/sshd_config after deploying keys."),
    "linux_ssh_strong_ciphers": (
        "SSH offers only strong ciphers and MACs", "medium",
        "CBC-mode, arcfour, 3DES ciphers and MD5/SHA1-96 MACs weaken encryption in transit.",
        "Remove weak entries from the Ciphers and MACs lines in sshd_config."),
    "linux_auditd_running": (
        "The audit daemon is running", "high",
        "auditd records security-relevant events needed to investigate a breach.",
        "Install and enable auditd: systemctl enable --now auditd."),
    "linux_auditd_rules_present": (
        "Audit rules are loaded", "medium",
        "auditd without rules records very little. Rules should watch identity files, sudoers and logins.",
        "Add rules under /etc/audit/rules.d/ and load them with augenrules --load."),
    "linux_log_retention_configured": (
        "System logs are kept for the required period", "medium",
        "logrotate settings determine how long logs survive. Compared with --min-log-retention-days.",
        "Increase 'rotate' in /etc/logrotate.conf (e.g. 'weekly' + 'rotate 13' = about 90 days)."),
    "linux_time_sync_enabled": (
        "The clock is synchronised", "low",
        "Accurate timestamps are needed to reconstruct incidents and meet notification deadlines.",
        "Enable systemd-timesyncd, chrony or ntpd."),
    "linux_firewall_enabled": (
        "A host firewall is active", "high",
        "A host firewall (ufw, firewalld, nftables or iptables) limits exposure of services.",
        "Enable ufw or firewalld, or load an nftables ruleset with a default-deny input policy."),
    "linux_pending_security_updates": (
        "No security updates are pending", "high",
        "Pending security updates leave known vulnerabilities open.",
        "Apply updates: apt-get upgrade / dnf upgrade --security."),
    "linux_automatic_security_updates_enabled": (
        "Security updates install automatically", "low",
        "unattended-upgrades or dnf-automatic shortens the window of exposure.",
        "Enable unattended-upgrades (Debian/Ubuntu) or dnf-automatic (RHEL family)."),
    "linux_sensitive_file_permissions": (
        "Sensitive system files have restrictive permissions", "high",
        "Password hashes, group secrets and SSH host keys must not be readable by other users.",
        "chmod 0640 /etc/shadow /etc/gshadow; chmod 0600 /etc/ssh/ssh_host_*_key; owner root."),
}

DATA_MOUNTS = ("/", "/home", "/var", "/srv", "/data", "/var/lib")
WEAK_CIPHER = re.compile(r"(cbc|arcfour|3des|blowfish|cast128)", re.I)
WEAK_MAC = re.compile(r"(hmac-md5|-96@|hmac-sha1-96|umac-64)", re.I)


class SystemProbe(object):
    """Reads the live system. Everything is read-only."""

    def read(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except (OSError, IOError):
            return None

    def glob(self, pattern):
        return sorted(glob.glob(pattern))

    def stat(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return None
        return {"mode": stat.S_IMODE(st.st_mode), "uid": st.st_uid, "gid": st.st_gid}

    def run(self, cmd):
        """Returns (returncode, stdout) or (None, '') if the program is missing."""
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            out, _ = p.communicate(timeout=60)
            return p.returncode, out.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            return None, ""

    def hostname(self):
        return socket.gethostname()

    def is_root(self):
        return hasattr(os, "geteuid") and os.geteuid() == 0


class FixtureProbe(object):
    """Replays a recorded host: <dir>/fs/... files, <dir>/commands.json, <dir>/stat.json, <dir>/host.json."""

    def __init__(self, root):
        self.root = root
        self.commands = self._json("commands.json", {})
        self.stats = self._json("stat.json", {})
        self.host = self._json("host.json", {})

    def _json(self, name, default):
        p = os.path.join(self.root, name)
        if not os.path.exists(p):
            return default
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _fs(self, path):
        return os.path.join(self.root, "fs", path.lstrip("/"))

    def read(self, path):
        try:
            with open(self._fs(path), "r", encoding="utf-8") as fh:
                return fh.read()
        except (OSError, IOError):
            return None

    def glob(self, pattern):
        base = os.path.join(self.root, "fs")
        out = set()
        for p in glob.glob(self._fs(pattern)):
            out.add("/" + os.path.relpath(p, base).replace(os.sep, "/"))
        out.update(p for p in self.stats if fnmatch.fnmatch(p, pattern))
        return sorted(out)

    def stat(self, path):
        s = self.stats.get(path)
        if s is None:
            return None
        return {"mode": int(str(s["mode"]), 8), "uid": s.get("uid", 0), "gid": s.get("gid", 0)}

    def run(self, cmd):
        r = self.commands.get(" ".join(cmd))
        if r is None:
            return None, ""
        return r.get("rc", 0), r.get("out", "")

    def hostname(self):
        return self.host.get("hostname", "fixture-host")

    def is_root(self):
        return bool(self.host.get("root", True))


# ---------------------------------------------------------------- helpers

def _sshd_config(probe):
    """Effective sshd settings: `sshd -T` when possible, else parsed config files."""
    rc, out = probe.run(["sshd", "-T"])
    settings = {}
    if rc == 0 and out.strip():
        for line in out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                settings[parts[0].lower()] = parts[1].strip()
        return settings, "sshd -T"
    text = probe.read("/etc/ssh/sshd_config")
    if text is None:
        return None, ""
    files = [text]
    for inc in re.findall(r"^\s*Include\s+(\S+)", text, re.M | re.I):
        for p in probe.glob(inc if inc.startswith("/") else "/etc/ssh/" + inc):
            t = probe.read(p)
            if t:
                files.insert(0, t)  # included files come first in typical Debian layouts
    for t in files:
        for line in t.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.lower().startswith("match "):
                if line.lower().startswith("match "):
                    break  # ignore Match blocks
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                key = parts[0].lower()
                if key not in settings:  # first value wins in sshd_config
                    settings[key] = parts[1].strip()
    return settings, "/etc/ssh/sshd_config"


def _is_active(probe, unit):
    rc, out = probe.run(["systemctl", "is-active", unit])
    if rc is None:
        return None
    return out.strip() == "active"


# ---------------------------------------------------------------- checks
# Each returns (status, message, resources) where status is PASS, FAIL or MANUAL.

def check_disk_encryption(probe, opts):
    rc, out = probe.run(["lsblk", "-J", "-o", "NAME,TYPE,FSTYPE,MOUNTPOINT"])
    if rc != 0 or not out.strip():
        return "MANUAL", "lsblk is not available; verify volume encryption manually.", []
    try:
        tree = json.loads(out).get("blockdevices", [])
    except ValueError:
        return "MANUAL", "Could not parse lsblk output.", []
    mounts = {}

    def walk(nodes, encrypted):
        for n in nodes:
            enc = encrypted or n.get("type") == "crypt"
            mp = n.get("mountpoint")
            if mp in DATA_MOUNTS:
                mounts[mp] = enc
            walk(n.get("children") or [], enc)

    walk(tree, False)
    if not mounts:
        return "MANUAL", "No data filesystems found in lsblk output.", []
    plain = sorted(m for m, enc in mounts.items() if not enc)
    if plain:
        return "FAIL", "Unencrypted data filesystems: " + ", ".join(plain), plain
    return "PASS", "All data filesystems are on encrypted volumes: " + ", ".join(sorted(mounts)), sorted(mounts)


def check_ssh_root_login(probe, opts):
    s, src = _sshd_config(probe)
    if s is None:
        return "MANUAL", "No sshd configuration found (SSH server may not be installed).", []
    val = s.get("permitrootlogin", "prohibit-password").lower()
    if val == "no":
        return "PASS", "PermitRootLogin is 'no' (%s)." % src, []
    return "FAIL", "PermitRootLogin is '%s' (%s); expected 'no'." % (val, src), []


def check_ssh_password_auth(probe, opts):
    s, src = _sshd_config(probe)
    if s is None:
        return "MANUAL", "No sshd configuration found.", []
    val = s.get("passwordauthentication", "yes").lower()
    if val == "no":
        return "PASS", "PasswordAuthentication is 'no' (%s)." % src, []
    return "FAIL", "PasswordAuthentication is '%s' (%s); expected 'no'." % (val, src), []


def check_ssh_ciphers(probe, opts):
    s, src = _sshd_config(probe)
    if s is None:
        return "MANUAL", "No sshd configuration found.", []
    weak = []
    for c in s.get("ciphers", "").split(","):
        if c and WEAK_CIPHER.search(c):
            weak.append(c)
    for m in s.get("macs", "").split(","):
        if m and WEAK_MAC.search(m):
            weak.append(m)
    if weak:
        return "FAIL", "Weak SSH algorithms enabled: " + ", ".join(weak), weak
    return "PASS", "No weak ciphers or MACs configured (%s)." % src, []


def check_auditd_running(probe, opts):
    active = _is_active(probe, "auditd")
    if active is None:
        return "MANUAL", "systemctl not available; verify auditd manually.", []
    if active:
        return "PASS", "auditd is active.", []
    return "FAIL", "auditd is not running.", []


def check_auditd_rules(probe, opts):
    rc, out = probe.run(["auditctl", "-l"])
    if rc is None or (rc != 0 and not probe.is_root()):
        return "MANUAL", "auditctl needs root; run the collector with sudo.", []
    rules = [line for line in out.splitlines() if line.strip() and "no rules" not in line.lower()]
    if rc == 0 and len(rules) >= 3:
        return "PASS", "%d audit rules loaded." % len(rules), []
    return "FAIL", "Only %d audit rules loaded." % len(rules), []


def _logrotate_days(text):
    period = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}
    days, count = 7, 4  # logrotate defaults: weekly, rotate 4 is the common distribution default
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line in period:
            days = period[line]
        m = re.match(r"rotate\s+(\d+)$", line)
        if m:
            count = int(m.group(1))
        if line.endswith("{"):
            break  # only global settings
    return days * count


def check_log_retention(probe, opts):
    text = probe.read("/etc/logrotate.conf")
    need = opts.min_log_retention_days
    if text is None:
        return "MANUAL", "No /etc/logrotate.conf; verify log retention manually.", []
    days = _logrotate_days(text)
    if days >= need:
        return "PASS", "logrotate keeps about %d days of logs (minimum %d)." % (days, need), []
    return "FAIL", "logrotate keeps about %d days of logs; at least %d expected." % (days, need), []


def check_time_sync(probe, opts):
    rc, out = probe.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
    if rc is None:
        for unit in ("chronyd", "chrony", "ntpd", "ntp", "systemd-timesyncd"):
            if _is_active(probe, unit):
                return "PASS", "%s is active." % unit, []
        return "MANUAL", "Could not determine time synchronisation.", []
    if out.strip() == "yes":
        return "PASS", "System clock is NTP-synchronised.", []
    return "FAIL", "System clock is not synchronised.", []


def check_firewall(probe, opts):
    rc, out = probe.run(["ufw", "status"])
    if rc == 0 and "status: active" in out.lower():
        return "PASS", "ufw is active.", []
    if _is_active(probe, "firewalld"):
        return "PASS", "firewalld is active.", []
    rc, out = probe.run(["nft", "list", "ruleset"])
    if rc == 0 and re.search(r"hook input .*policy drop", out):
        return "PASS", "nftables input chain has a drop policy.", []
    rc2, out2 = probe.run(["iptables", "-S"])
    if rc2 == 0 and ("-P INPUT DROP" in out2 or "-A INPUT" in out2 and "-j DROP" in out2):
        return "PASS", "iptables INPUT drops by default.", []
    if rc is None and rc2 is None and not probe.is_root():
        return "MANUAL", "Firewall state needs root to read; run with sudo.", []
    return "FAIL", "No active host firewall found (ufw, firewalld, nftables, iptables).", []


def check_pending_updates(probe, opts):
    rc, out = probe.run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"])
    if rc == 0:
        sec = [line.split()[1] for line in out.splitlines() if line.startswith("Inst ") and "security" in line.lower()]
        if sec:
            return "FAIL", "%d security updates pending: %s" % (len(sec), ", ".join(sec[:10])), sec
        return "PASS", "No pending security updates (apt).", []
    rc, out = probe.run(["dnf", "-q", "--cacheonly", "updateinfo", "list", "--security"])
    if rc == 0:
        pkgs = [line.split()[-1] for line in out.splitlines() if line.strip()]
        if pkgs:
            return "FAIL", "%d security updates pending: %s" % (len(pkgs), ", ".join(pkgs[:10])), pkgs
        return "PASS", "No pending security updates (dnf).", []
    return "MANUAL", "No supported package manager found (apt, dnf).", []


def check_auto_updates(probe, opts):
    conf = probe.read("/etc/apt/apt.conf.d/20auto-upgrades")
    if conf is not None:
        if re.search(r'Unattended-Upgrade\s+"1"', conf):
            return "PASS", "unattended-upgrades is enabled.", []
        return "FAIL", "unattended-upgrades is installed but disabled.", []
    timer = _is_active(probe, "dnf-automatic.timer")
    if timer:
        return "PASS", "dnf-automatic timer is active.", []
    if timer is None:
        return "MANUAL", "Could not determine automatic update configuration.", []
    return "FAIL", "Automatic security updates are not enabled.", []


SENSITIVE = [
    ("/etc/shadow", 0o640),
    ("/etc/gshadow", 0o640),
    ("/etc/passwd", 0o644),
    ("/etc/group", 0o644),
    ("/etc/ssh/sshd_config", 0o644),
    ("/etc/sudoers", 0o440),
]


def check_file_permissions(probe, opts):
    bad, seen = [], 0
    targets = list(SENSITIVE) + [(p, 0o600) for p in probe.glob("/etc/ssh/ssh_host_*_key")]
    for path, max_mode in targets:
        st = probe.stat(path)
        if st is None:
            continue
        seen += 1
        extra = st["mode"] & ~max_mode
        if extra or st["uid"] != 0:
            bad.append("%s (mode %04o, uid %d)" % (path, st["mode"], st["uid"]))
    if not seen:
        return "MANUAL", "Could not read file permissions.", []
    if bad:
        return "FAIL", "Too permissive: " + "; ".join(bad), bad
    return "PASS", "%d sensitive files have restrictive permissions." % seen, []


RUNNERS = {
    "linux_disk_encryption_enabled": check_disk_encryption,
    "linux_ssh_root_login_disabled": check_ssh_root_login,
    "linux_ssh_password_auth_disabled": check_ssh_password_auth,
    "linux_ssh_strong_ciphers": check_ssh_ciphers,
    "linux_auditd_running": check_auditd_running,
    "linux_auditd_rules_present": check_auditd_rules,
    "linux_log_retention_configured": check_log_retention,
    "linux_time_sync_enabled": check_time_sync,
    "linux_firewall_enabled": check_firewall,
    "linux_pending_security_updates": check_pending_updates,
    "linux_automatic_security_updates_enabled": check_auto_updates,
    "linux_sensitive_file_permissions": check_file_permissions,
}


def finding(check_id, status, message, host, now, os_name):
    title, severity, desc, remediation = CHECKS[check_id]
    t = int(now)
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    return {
        "message": message,
        "metadata": {
            "event_code": check_id,
            "product": {"name": "PDPL-Ready Linux collector", "uid": PRODUCT_UID,
                        "vendor_name": "PDPL-Ready", "version": COLLECTOR_VERSION},
            "profiles": ["datetime"],
            "version": "1.4.0",
        },
        "severity_id": SEVERITY_IDS[severity],
        "severity": severity.capitalize(),
        "status": "New",
        "status_code": status,
        "status_detail": message,
        "status_id": 1,
        "activity_id": 1,
        "activity_name": "Create",
        "finding_info": {
            "created_time": t, "created_time_dt": iso, "desc": desc, "title": title,
            "uid": "pdpl-linux-%s-%s" % (host, check_id),
        },
        "resources": [{
            "name": host, "uid": host, "type": "Host", "region": "",
            "group": {"name": "linux"}, "labels": [], "data": {"details": message},
        }],
        "device": {"hostname": host, "name": host, "type": "Server", "type_id": 1,
                   "os": {"name": os_name or "Linux", "type": "Linux", "type_id": 100}},
        "category_name": "Findings", "category_uid": 2,
        "class_name": "Detection Finding", "class_uid": 2004,
        "type_uid": 200401, "type_name": "Detection Finding: Create",
        "remediation": {"desc": remediation, "references": []},
        "time": t, "time_dt": iso,
        "unmapped": {"provider": "linux"},
    }


def _os_name(probe):
    text = probe.read("/etc/os-release") or ""
    m = re.search(r'^PRETTY_NAME="?([^"\n]+)"?', text, re.M)
    return m.group(1) if m else "Linux"


def collect(probe, opts, now=None):
    now = time.time() if now is None else now
    host = opts.hostname or probe.hostname()
    os_name = _os_name(probe)
    out = []
    for check_id in sorted(RUNNERS):
        try:
            status, message, _ = RUNNERS[check_id](probe, opts)
        except Exception as exc:  # a broken probe must never stop the other checks
            status, message = "MANUAL", "Check failed to run: %s" % exc.__class__.__name__
        out.append(finding(check_id, status, message, host, now, os_name))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only PDPL-Ready evidence collector for Linux hosts.")
    ap.add_argument("--output", "-o", help="write findings to this file instead of stdout")
    ap.add_argument("--hostname", help="override the reported hostname")
    ap.add_argument("--min-log-retention-days", type=int, default=90)
    ap.add_argument("--fixture", help="replay a recorded host directory instead of reading this machine")
    ap.add_argument("--time", type=float, help=argparse.SUPPRESS)
    opts = ap.parse_args(argv)
    probe = FixtureProbe(opts.fixture) if opts.fixture else SystemProbe()
    findings = collect(probe, opts, now=opts.time)
    data = json.dumps(findings, indent=2)
    if opts.output:
        with open(opts.output, "w", encoding="utf-8") as fh:
            fh.write(data + "\n")
        fails = sum(1 for f in findings if f["status_code"] == "FAIL")
        sys.stderr.write("wrote %d findings (%d failing) to %s\n" % (len(findings), fails, opts.output))
    else:
        sys.stdout.write(data + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
