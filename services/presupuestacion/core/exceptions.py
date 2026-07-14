from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ValidationError(DomainError):
    pass


STATUS_MAP: dict[type[DomainError], int] = {
    AuthenticationError: 401,
    ForbiddenError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
}


def register_exception_handlers(app: FastAPI) -> None:
    async def _handler(request: Request, exc: DomainError) -> JSONResponse:
        status_code = STATUS_MAP.get(type(exc), 500)
        return JSONResponse(status_code=status_code, content={"detail": exc.message})

    for error_type in STATUS_MAP:
        app.add_exception_handler(error_type, _handler)
