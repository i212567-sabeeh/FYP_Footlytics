"""An access request becomes a normal User only after an administrator approves."""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.club_access import ensure_club_access, is_admin
from app.auth.passwords import hash_password
from app.database.base import utc_now
from app.models.football import ClubMembership
from app.models.signup_request import SignupRequest, SignupStatus
from app.models.user import User
from app.schemas.football import Page
from app.schemas.signup import SignupApproval, SignupCreate, SignupRequestRead
from app.services.domain_common import DomainError, page_results
from app.services.role_service import resolve_roles
from app.services.user_service import (
    DuplicateEmailError,
    commit_user,
    get_user_by_email,
)


def submit_signup(session: Session, data: SignupCreate) -> None:
    # Hash duplicate submissions too, reducing timing differences. Return the
    # same receipt without replacing any existing password or request.
    hashed = hash_password(data.password.get_secret_value())
    existing = session.scalar(
        select(SignupRequest).where(SignupRequest.email == data.email)
    )
    if get_user_by_email(session, data.email) is not None or existing is not None:
        return
    # End the duplicate-check read before competing SQLite writers insert.
    session.rollback()
    session.add(
        SignupRequest(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hashed,
            requested_role=data.requested_role,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # A concurrent submission of the same normalized email is also a no-op.
        if (
            session.scalar(
                select(SignupRequest.id).where(SignupRequest.email == data.email)
            )
            is None
        ):
            raise


def list_requests(
    session: Session, status: SignupStatus, offset: int, limit: int
) -> Page[SignupRequestRead]:
    return page_results(
        session,
        select(SignupRequest)
        .where(SignupRequest.status == status)
        .order_by(SignupRequest.created_at, SignupRequest.id),
        SignupRequestRead,
        offset,
        limit,
    )


def _lock_pending(session: Session, actor: User, request_id: int) -> SignupRequest:
    # Same short-write pattern as match media: discard the auth read snapshot,
    # lock the row on PostgreSQL / serialize SQLite writers, then recheck access.
    session.rollback()
    session.execute(
        update(SignupRequest)
        .where(SignupRequest.id == request_id)
        .values(id=SignupRequest.id)
        .execution_options(synchronize_session=False)
    )
    if not actor.is_active or not is_admin(actor):
        raise DomainError(403, "Administrator approval is required")
    request = session.get(SignupRequest, request_id)
    if request is None:
        raise DomainError(404, "Signup request not found")
    if request.status != "pending":
        raise DomainError(
            409, "This signup request has already been reviewed. Refresh the list."
        )
    return request


def _review(request: SignupRequest, actor: User, status: SignupStatus) -> None:
    request.status = status
    request.reviewed_by_user_id = actor.id
    request.reviewed_at = utc_now()
    # Approval copies the hash to User; rejection discards it. Review history
    # contains no credentials and cannot later be used to silently reset a user.
    request.hashed_password = None


def approve_request(
    session: Session, actor: User, request_id: int, data: SignupApproval
) -> User:
    request = _lock_pending(session, actor, request_id)
    if request.requested_role is not None and data.roles != [request.requested_role]:
        raise DomainError(422, "Approval must assign the requested role.")
    if get_user_by_email(session, request.email) is not None:
        raise DomainError(
            409,
            "An account already uses this email. "
            "Manage that account or reject this request.",
        )
    if data.club_id is not None:
        ensure_club_access(session, actor, data.club_id, write=True)
    assert request.hashed_password is not None
    user = User(
        email=request.email,
        full_name=request.full_name,
        hashed_password=request.hashed_password,
        roles=resolve_roles(session, data.roles),
    )
    session.add(user)
    try:
        session.flush()
        if data.club_id is not None:
            session.add(ClubMembership(club_id=data.club_id, user_id=user.id))
        request.approved_user_id = user.id
        _review(request, actor, "approved")
        return commit_user(session, user)
    except IntegrityError:
        session.rollback()
        if get_user_by_email(session, request.email) is not None:
            raise DuplicateEmailError from None
        raise


def reject_request(session: Session, actor: User, request_id: int) -> SignupRequest:
    request = _lock_pending(session, actor, request_id)
    _review(request, actor, "rejected")
    session.commit()
    session.refresh(request)
    return request
