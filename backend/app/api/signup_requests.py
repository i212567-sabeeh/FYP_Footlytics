from fastapi import APIRouter

from app.api.pagination import PaginationQuery
from app.auth.dependencies import AdminUser
from app.database.dependencies import DatabaseSession
from app.models.signup_request import SignupStatus
from app.schemas.football import Identifier, Page
from app.schemas.signup import SignupApproval, SignupRequestRead
from app.schemas.user import UserRead
from app.services import signup_service

router = APIRouter(prefix="/signup-requests", tags=["signup approval"])


@router.get("", response_model=Page[SignupRequestRead])
def list_requests(
    session: DatabaseSession,
    admin: AdminUser,
    page: PaginationQuery,
    status: SignupStatus = "pending",
):
    return signup_service.list_requests(session, status, page.offset, page.limit)


@router.post("/{request_id}/approve", response_model=UserRead, status_code=201)
def approve(
    request_id: Identifier,
    data: SignupApproval,
    session: DatabaseSession,
    admin: AdminUser,
):
    return UserRead.from_user(
        signup_service.approve_request(session, admin, request_id, data)
    )


@router.post("/{request_id}/reject", response_model=SignupRequestRead)
def reject(request_id: Identifier, session: DatabaseSession, admin: AdminUser):
    return signup_service.reject_request(session, admin, request_id)
