"""Command line: python -m app.cli <command>

  migrate                 apply database migrations
  create-admin USER NAME  create an Admin (password read from PDPL_ADMIN_PASSWORD or prompted)
  seed-demo [--reset]     load the fictional demo clinic
  import-findings FILE [--org ID]
                          import a Prowler JSON-OCSF / collector findings file
  orgs                    list organisations and their ids
  collect                 run one scheduled collection now
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pdpl-ready")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    ca = sub.add_parser("create-admin")
    ca.add_argument("username")
    ca.add_argument("display_name")
    sd = sub.add_parser("seed-demo")
    sd.add_argument("--reset", action="store_true", help="wipe the database first")
    sd.add_argument("--if-empty", action="store_true", help="only seed when no users exist")
    imp = sub.add_parser("import-findings")
    imp.add_argument("file")
    imp.add_argument("--org", type=int, default=None, help="organisation id (default: PDPL_COLLECT_ORG_ID)")
    sub.add_parser("orgs")
    sub.add_parser("collect")
    args = p.parse_args(argv)

    from . import migrate
    from .db import init_engine, org_session, session_factory

    if args.cmd == "migrate":
        migrate.upgrade()
        print("database is up to date")
        return 0

    init_engine()
    if args.cmd == "create-admin":
        from . import audit
        from .models import User
        from .security import MIN_PASSWORD_LEN, hash_password

        pw = os.environ.get("PDPL_ADMIN_PASSWORD") or getpass.getpass("Password: ")
        if len(pw) < MIN_PASSWORD_LEN:
            print(f"password must be at least {MIN_PASSWORD_LEN} characters", file=sys.stderr)
            return 2
        with session_factory()() as db:
            u = User(username=args.username, display_name=args.display_name,
                     password_hash=hash_password(pw), role="admin")
            db.add(u)
            db.flush()
            audit.record(db, None, "user.create", "user", u.id, {"username": u.username, "role": "admin"},
                         actor_name="cli")
            db.commit()
        print(f"created admin {args.username}")
        return 0

    if args.cmd == "seed-demo":
        from .demo import seed_demo

        result = seed_demo(reset=args.reset, only_if_empty=args.if_empty)
        print(result)
        return 0

    if args.cmd == "import-findings":
        from .evidence.service import import_findings_file

        from .config import get_settings
        from .models import Organisation

        org_id = args.org or get_settings().collect_org_id
        with session_factory()() as db:
            org = db.get(Organisation, org_id)
        if org is None or org.archived:
            print(f"no active organisation with id {org_id} (see: orgs)", file=sys.stderr)
            return 2
        with org_session(org_id) as db, open(args.file, "rb") as fh:
            run = import_findings_file(db, fh.read(), os.path.basename(args.file), actor=None,
                                       source="prowler-import")
            db.commit()
            print(f"imported run {run.id} into {org.name}: {run.total} findings ({run.failed} failing)")
        return 0

    if args.cmd == "orgs":
        from sqlalchemy import select

        from .models import Organisation

        with session_factory()() as db:
            for o in db.execute(select(Organisation).order_by(Organisation.id)).scalars():
                print(f"{o.id:>4}  {o.name}{'  (archived)' if o.archived else ''}")
        return 0

    if args.cmd == "collect":
        from .scheduler import collect_once

        print(collect_once())
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
