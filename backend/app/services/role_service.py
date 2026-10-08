from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.roles import ROLE_DISPLAY_NAMES, RoleName
from app.models.user import Role


def ensure_roles(session: Session) -> None:
    """Insert missing canonical roles; the caller owns the transaction."""
    existing = set(session.scalars(select(Role.name)))
    for name, display_name in ROLE_DISPLAY_NAMES.items():
        if name not in existing:
            session.add(Role(name=name.value, display_name=display_name))
    session.flush()


def resolve_roles(session: Session, names: list[RoleName]) -> list[Role]:
    roles = list(session.scalars(select(Role).where(Role.name.in_(names))))
    if len(roles) != len(names):
        raise RuntimeError("Required roles are missing; run migrations/role seeding")
    return roles
