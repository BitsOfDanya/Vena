import argparse
import getpass
import json
import os
import re
from uuid import uuid4

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import PASSWORDS
from app.db.models import User
from app.db.session import SessionLocal
from app.domain.scopes import normalize


def create_user(
    session: Session,
    username: str,
    email: str,
    password: str,
    role: str = "dispatcher",
    scopes: list[str] | None = None,
) -> bool:
    username = username.strip().lower()
    email = str(TypeAdapter(EmailStr).validate_python(email.strip().lower()))
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", username):
        raise ValueError("Invalid username")
    if role not in {"admin", "dispatcher", "viewer"} or not 10 <= len(password) <= 1024:
        raise ValueError("Invalid role or password length (10–1024 required)")
    existing = session.scalar(
        select(User).where(or_(User.username == username, User.email == email))
    )
    if existing:
        if existing.username != username or existing.email != email:
            raise ValueError(f"Username or email collision for {username}")
        return False
    session.add(
        User(
            id=uuid4().hex,
            username=username,
            email=email,
            password_hash=PASSWORDS.hash(password),
            role=role,
            scopes=normalize(scopes or []) or ["all"],
        )
    )
    session.flush()
    return True


def seed_users(
    session: Session,
    count: int = 20,
    domain: str = "example.com",
    password: str = "0987654321",
    role: str = "dispatcher",
    admin: str | None = None,
    scopes: dict[str, list[str]] | None = None,
) -> int:
    return sum(
        create_user(
            session,
            f"user{i}",
            f"user{i}@{domain}",
            password,
            "admin" if f"user{i}" == admin else role,
            (scopes or {}).get(f"user{i}"),
        )
        for i in range(1, count + 1)
    )


def seed_scopes(raw: str | None) -> dict[str, list[str]]:
    value = json.loads(raw or "{}")
    if not isinstance(value, dict) or not all(
        isinstance(items, list) and all(isinstance(item, str) for item in items)
        for items in value.values()
    ):
        raise ValueError('VENA_SEED_SCOPES must look like {"user18": ["complex:5"]}')
    return {str(name).strip().lower(): normalize(items) for name, items in value.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--email-domain", default="example.com")
    parser.add_argument("--role", choices=["admin", "dispatcher", "viewer"], default="dispatcher")
    parser.add_argument(
        "--admin",
        default=os.environ.get("VENA_SEED_ADMIN") or None,
        help="Seeded user created as administrator, e.g. user1 (default: VENA_SEED_ADMIN)",
    )
    parser.add_argument("--username", help="Create one account instead of the 20 demo users")
    parser.add_argument("--email", help="Email for --username")
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error("count must be between 1 and 1000")
    seeded = {f"user{i}" for i in range(1, args.count + 1)}
    if not args.username and args.admin and args.admin not in seeded:
        parser.error(f"--admin must be one of user1..user{args.count}")
    try:
        scopes = seed_scopes(os.environ.get("VENA_SEED_SCOPES"))
    except ValueError as error:
        parser.error(str(error))
    with SessionLocal.begin() as session:
        if args.username:
            if not args.email:
                parser.error("--email is required with --username")
            password = os.environ.get("VENA_USER_PASSWORD") or getpass.getpass("Password: ")
            created = int(
                create_user(
                    session,
                    args.username,
                    args.email,
                    password,
                    args.role,
                    scopes.get(args.username.strip().lower()),
                )
            )
        else:
            created = seed_users(
                session,
                args.count,
                args.email_domain,
                os.environ.get("VENA_USER_PASSWORD", "0987654321"),
                args.role,
                args.admin,
                scopes,
            )
    print(f"Created {created} users; existing accounts unchanged.")


if __name__ == "__main__":
    main()
