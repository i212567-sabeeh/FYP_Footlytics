from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.auth.dependencies import AdminUser
from app.database.dependencies import DatabaseSession
from app.schemas.user import UserCreate, UserList, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["user administration"])
UserId = Annotated[int, Path(gt=0, le=2**63 - 1)]


@router.get("", response_model=UserList)
def list_users(
    session: DatabaseSession,
    admin: AdminUser,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> UserList:
    users, total = user_service.list_users(session, offset, limit)
    return UserList(
        items=[UserRead.from_user(user) for user in users],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    data: UserCreate, session: DatabaseSession, admin: AdminUser
) -> UserRead:
    return UserRead.from_user(user_service.create_user(session, data))


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UserId, session: DatabaseSession, admin: AdminUser) -> UserRead:
    return UserRead.from_user(user_service.get_user_by_id(session, user_id))


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: UserId, data: UserUpdate, session: DatabaseSession, admin: AdminUser
) -> UserRead:
    return UserRead.from_user(
        user_service.update_user(session, user_id, data, actor_id=admin.id)
    )
