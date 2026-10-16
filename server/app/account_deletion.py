"""Operator queue: python -m app.account_deletion list|complete (see --help)."""
import argparse
import json

from .db import SessionLocal
from .models import AccountDeletionRequest
from .services.account_deletion import complete_deletion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("list")
    complete = commands.add_parser("complete")
    complete.add_argument("--family-id", type=int, required=True)
    complete.add_argument("--confirm-family-id", type=int, required=True,
                          help="Repeat the family ID to confirm irreversible erasure")
    args = parser.parse_args()
    if args.action == "complete" and args.family_id != args.confirm_family_id:
        parser.error("Confirmation must match the family ID")
    with SessionLocal.begin() as db:
        if args.action == "list":
            print(json.dumps([{"family_id": r.family_id, "requested_at": r.created_at.isoformat()}
                              for r in db.query(AccountDeletionRequest)
                              .filter_by(completed_at=None).order_by(AccountDeletionRequest.created_at)], indent=2))
        else:
            try:
                row = complete_deletion(db, args.family_id)
            except ValueError as exc:
                parser.error(str(exc))
            print(json.dumps({"family_id": row.family_id, "completed_at": row.completed_at.isoformat()}))


if __name__ == "__main__":
    main()
