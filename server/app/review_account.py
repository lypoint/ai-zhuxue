"""Run on the API host: python -m app.review_account create|disable (see --help)."""
import argparse
import json
import os
from pathlib import Path
import secrets

from .db import SessionLocal
from .services.review_accounts import create_review_account, disable_review_account


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create")
    create.add_argument("--credentials-file", type=Path, required=True,
                        help="Private file outside the public checkout; must not exist")
    disable = commands.add_parser("disable")
    disable.add_argument("--username", required=True)
    args = parser.parse_args()
    if args.action == "disable":
        with SessionLocal.begin() as db:
            result = disable_review_account(db, args.username.lower())
        print(json.dumps(result))
        return
    path = args.credentials_file.expanduser().resolve()
    public_root = Path(__file__).resolve().parents[2]
    if path.is_relative_to(public_root):
        parser.error("Credentials must be stored outside the public checkout")
    username = "review" + "".join(secrets.choice("23456789") for _ in range(5))
    # Lowercase ASCII and digits; no punctuation or ambiguous characters.
    words = ("apple", "river", "sunny", "maple", "tiger", "green", "peach", "happy",
             "panda", "cloud", "lemon", "ocean", "music", "seven", "stone", "water")
    password = "".join(secrets.choice(words) for _ in range(3)) + "".join(secrets.choice("23456789") for _ in range(6))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as output:
            with SessionLocal.begin() as db:
                guardian = create_review_account(db, username, password)
                output.write(json.dumps({"username": username, "password": password,
                                         "family_id": guardian.family_id, "seats": 100,
                                         "membership": "permanent"}, indent=2) + "\n")
                output.flush()
                os.fsync(output.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    print("Review account created; credentials saved to the private file.")


if __name__ == "__main__":
    main()
