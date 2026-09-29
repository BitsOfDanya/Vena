"""Explicit, idempotent user provisioning: python -m app.db.seed_users."""

import argparse
import getpass
import os
import re
from uuid import uuid4

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import PASSWORDS
from app.db.models import User
from app.db.session import SessionLocal


def create_user(
    session: Session, username: str, email: str, password: str, role: str = "dispatcher"
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
        return False  # Never reset an existing user's password, role or activity.
    session.add(
        User(
            id=uuid4().hex,
            username=username,
            email=email,
            password_hash=PASSWORDS.hash(password),
            role=role,
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
) -> int:
    return sum(
        create_user(session, f"user{i}", f"user{i}@{domain}", password, role)
        for i in range(1, count + 1)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--email-domain", default="example.com")
    parser.add_argument("--role", choices=["admin", "dispatcher", "viewer"], default="dispatcher")
    parser.add_argument("--username", help="Create one account instead of the 20 demo users")
    parser.add_argument("--email", help="Email for --username")
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error("count must be between 1 and 1000")
    with SessionLocal.begin() as session:
        if args.username:
            if not args.email:
                parser.error("--email is required with --username")
            password = os.environ.get("VENA_USER_PASSWORD") or getpass.getpass("Password: ")
            created = int(create_user(session, args.username, args.email, password, args.role))
        else:
            created = seed_users(
                session,
                args.count,
                args.email_domain,
                os.environ.get("VENA_USER_PASSWORD", "0987654321"),
                args.role,
            )
    print(f"Created {created} users; existing accounts unchanged.")


if __name__ == "__main__":
    main()
