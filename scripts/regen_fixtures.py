"""Regenerate the committed findings fixtures.

  python scripts/regen_fixtures.py

Writes:
  fixtures/prowler/nour-clinic-week1.ocsf.json   first weekly AWS scan (synthetic, Prowler 5.50.0 OCSF shape)
  fixtures/prowler/nour-clinic-week6.ocsf.json   latest scan, with the public-bucket regression
  fixtures/linux-output/<host>.ocsf.json         Linux collector output replayed from fixtures/linux/<host>
"""
import json
import sys
from argparse import Namespace
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app import demo_aws  # noqa: E402

WEEK1 = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
WEEK6 = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(REPO), f"({len(data)} findings)")


def main() -> None:
    write(REPO / "fixtures/prowler/nour-clinic-week1.ocsf.json", demo_aws.findings_for_week(1, WEEK1))
    write(REPO / "fixtures/prowler/nour-clinic-week6.ocsf.json", demo_aws.findings_for_week(6, WEEK6))
    spec = spec_from_file_location("collector", REPO / "collectors/linux/pdpl_linux_collector.py")
    col = module_from_spec(spec)
    spec.loader.exec_module(col)
    opts = Namespace(hostname=None, min_log_retention_days=90)
    for host in ("clinic-db-01", "clinic-web-01"):
        probe = col.FixtureProbe(str(REPO / "fixtures/linux" / host))
        write(REPO / f"fixtures/linux-output/{host}.ocsf.json", col.collect(probe, opts, now=WEEK6.timestamp()))


if __name__ == "__main__":
    main()
