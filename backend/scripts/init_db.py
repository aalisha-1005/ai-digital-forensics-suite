"""Initialise the local database.

  python -m scripts.init_db --admin-user admin            # prompts for a password (not echoed)
  python -m scripts.init_db --admin-user admin --seed-demo
  DFIS_ADMIN_PASSWORD=... python -m scripts.init_db --admin-user admin   # non-interactive

No credentials are stored in source code. Demo investigator passwords are randomly generated and
printed once to your terminal.
"""
import argparse
import getpass
import os
import sys

from app import migrations
from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password, validate_password_strength
from app.services import ml
from app import config


def ensure_roles(db):
    for name in ("administrator", "investigator"):
        if not db.query(Role).filter_by(name=name).first():
            db.add(Role(name=name))
    db.commit()


def create_user(db, username, full_name, password, role):
    err = validate_password_strength(password)
    if err:
        sys.exit(err)
    r = db.query(Role).filter_by(name=role).one()
    u = User(username=username, full_name=full_name, password_hash=hash_password(password), role_id=r.id)
    db.add(u)
    db.commit()
    return u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-user", default="admin")
    ap.add_argument("--seed-demo", action="store_true", help="add clearly labelled SYNTHETIC cases and evidence")
    args = ap.parse_args()
    migrations.run()
    db = SessionLocal()
    ensure_roles(db)
    if not db.query(User).filter_by(username=args.admin_user).first():
        pw = os.getenv("DFIS_ADMIN_PASSWORD") or getpass.getpass(f"Password for new administrator '{args.admin_user}' (min 12 chars): ")
        create_user(db, args.admin_user, "Local Administrator", pw, "administrator")
        print(f"created administrator '{args.admin_user}'")
    else:
        print(f"administrator '{args.admin_user}' already exists")
    if not (config.MODEL_DIR / "model.joblib").exists():
        card = ml.train(config.MODEL_DIR)
        print(f"trained local model (synthetic data), holdout accuracy {card['holdout_accuracy']}")
    if args.seed_demo:
        from scripts.seed_demo import seed
        seed(db)


if __name__ == "__main__":
    main()
