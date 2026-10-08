from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import dummy_password_hash, hash_password, verify_password
from app.auth.roles import RoleName
from app.database.base import utc_now
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.role_service import resolve_roles


class UserNotFoundError(Exception):
    pass


class DuplicateEmailError(Exception):
    pass


class SelfLockoutError(Exception):
    pass


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.strip().lower()))


def get_user_by_id(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError
    return user


def list_users(session: Session, offset: int, limit: int) -> tuple[list[User], int]:
    total = session.scalar(select(func.count()).select_from(User)) or 0
    users = session.scalars(select(User).order_by(User.id).offset(offset).limit(limit))
    return list(users), total


def commit_user(session: Session, user: User) -> User:
    email = user.email
    user_id = user.id
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_user_by_email(session, email)
        if existing is not None and existing.id != user_id:
            raise DuplicateEmailError from None
        raise
    session.refresh(user)
    return user


def create_user(session: Session, data: UserCreate) -> User:
    if get_user_by_email(session, data.email) is not None:
        raise DuplicateEmailError
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password.get_secret_value()),
        roles=resolve_roles(session, data.roles),
    )
    session.add(user)
    return commit_user(session, user)


def update_user(
    session: Session, user_id: int, data: UserUpdate, actor_id: int
) -> User:
    user = get_user_by_id(session, user_id)
    if user.id == actor_id and (
        data.is_active is False
        or (data.roles is not None and RoleName.ADMIN not in data.roles)
    ):
        raise SelfLockoutError
    if data.email is not None:
        existing = get_user_by_email(session, data.email)
        if existing is not None and existing.id != user.id:
            raise DuplicateEmailError
        user.email = data.email
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.roles is not None:
        user.roles = resolve_roles(session, data.roles)
    # Role-only edits also change the account's update timestamp.
    user.updated_at = utc_now()
    return commit_user(session, user)


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(session, email)
    hashed = user.hashed_password if user else dummy_password_hash()
    valid_password = verify_password(password, hashed)
    if user is None or not valid_password or not user.is_active:
        return None
    return user
