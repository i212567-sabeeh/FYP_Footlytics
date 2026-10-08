from fastapi import APIRouter, Request

from app.auth.dependencies import CurrentUser, unauthorized
from app.auth.tokens import create_access_token
from app.database.dependencies import DatabaseSession
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.signup import SignupCreate, SignupReceipt
from app.schemas.user import UserRead
from app.services.signup_service import submit_signup
from app.services.user_service import authenticate_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/signup", response_model=SignupReceipt, status_code=202)
def signup(data: SignupCreate, session: DatabaseSession) -> SignupReceipt:
    submit_signup(session, data)
    return SignupReceipt()


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest, request: Request, session: DatabaseSession
) -> TokenResponse:
    user = authenticate_user(session, data.email, data.password.get_secret_value())
    if user is None:
        raise unauthorized()
    return TokenResponse(
        access_token=create_access_token(user.id, request.app.state.settings)
    )


@router.get("/me", response_model=UserRead)
def current_user(user: CurrentUser) -> UserRead:
    return UserRead.from_user(user)
