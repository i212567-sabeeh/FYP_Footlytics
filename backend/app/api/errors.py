from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.domain_common import DomainError
from app.services.user_service import (
    DuplicateEmailError,
    SelfLockoutError,
    UserNotFoundError,
)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic errors otherwise echo submitted passwords in their input field.
        details = [
            {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": details})

    @app.exception_handler(DuplicateEmailError)
    async def duplicate_email(
        request: Request, exc: DuplicateEmailError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": "Email already in use"})

    @app.exception_handler(UserNotFoundError)
    async def not_found(request: Request, exc: UserNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "User not found"})

    @app.exception_handler(SelfLockoutError)
    async def self_lockout(request: Request, exc: SelfLockoutError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "You cannot deactivate yourself or remove your own admin role"
            },
        )
