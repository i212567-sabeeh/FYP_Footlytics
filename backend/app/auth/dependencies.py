from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.auth.roles import RoleName
from app.auth.tokens import decode_access_token
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.services.user_service import UserNotFoundError, get_user_by_id

bearer = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        user_id = decode_access_token(
            credentials.credentials, request.app.state.settings
        )
        user = get_user_by_id(session, user_id)
    except (InvalidTokenError, UserNotFoundError):
        raise unauthorized() from None
    if not user.is_active:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: RoleName) -> Callable[..., User]:
    """Require any listed role; admin bypass exists only when explicitly listed."""
    if not roles:
        raise ValueError("At least one required role must be supplied")
    allowed = frozenset(roles)

    def check_roles(user: CurrentUser) -> User:
        if not allowed.intersection(role.name for role in user.roles):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return check_roles


AdminUser = Annotated[User, Depends(require_roles(RoleName.ADMIN))]
