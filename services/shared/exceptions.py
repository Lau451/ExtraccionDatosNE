import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_MENSAJE_GENERICO = "Error interno del servidor"


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


class ExtraccionNoDisponibleError(DomainError):
    """El CSV crudo de la extracción no es accesible desde este servicio."""


STATUS_MAP: dict[type[DomainError], int] = {
    AuthenticationError: 401,
    ForbiddenError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
    ExtraccionNoDisponibleError: 503,
}


class _UnhandledExceptionMiddleware(BaseHTTPMiddleware):
    """T5 (2026-09-25, ver odd/tasks/extraccion-multi-tenant.md): Starlette trata
    `Exception`/500 como un caso especial -- `FastAPI.build_middleware_stack()`
    (starlette/applications.py) lo enruta a `ServerErrorMiddleware`, el middleware MÁS
    EXTERNO de todo el stack, agregado ANTES que cualquier middleware de usuario
    (incluido CORSMiddleware). Un `app.add_exception_handler(Exception, ...)` corre ahí,
    fuera de CORSMiddleware: la respuesta que arma nunca pasa por CORS, así que el
    browser la recibe sin encabezados `access-control-allow-origin` y muestra
    "Failed to fetch" aunque el server sí respondió (síntoma observado: extracción
    persistida OK, pero `GET /api/documentos` siguiente explotaba con
    httpx.RemoteProtocolError y el frontend veía un fetch fallido sin CORS).

    Por eso el catch-all va acá, como middleware agregado por `register_exception_handlers()`
    -- que en ambos `main.py` (extraccion y presupuestacion) se llama ANTES de
    `app.add_middleware(CORSMiddleware, ...)`. `Starlette.add_middleware()` inserta al
    principio de la lista (`user_middleware.insert(0, ...)`) y esa lista se envuelve en
    orden inverso, así que el middleware agregado DESPUÉS queda más externo: con este
    orden de llamadas, CORSMiddleware queda afuera y este catch-all adentro, de modo que
    CORSMiddleware sí ve (y decora) la respuesta 500 que produce.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 -- catch-all intencional, ver docstring
            # Nunca se filtra el mensaje/traceback original en el body: solo se loguea.
            logger.exception(
                "Excepción inesperada en %s %s", request.method, request.url.path
            )
            return JSONResponse(status_code=500, content={"detail": _MENSAJE_GENERICO})


def register_exception_handlers(app: FastAPI) -> None:
    async def _handler(request: Request, exc: DomainError) -> JSONResponse:
        status_code = STATUS_MAP.get(type(exc), 500)
        return JSONResponse(status_code=status_code, content={"detail": exc.message})

    for error_type in STATUS_MAP:
        app.add_exception_handler(error_type, _handler)

    # Red de contención adicional (sin CORS -- ver ServerErrorMiddleware más arriba):
    # cubre cualquier excepción que por lo que sea no pase por el middleware de abajo
    # (p.ej. algo agregado por error por fuera de este stack). Nunca filtra internals.
    async def _fallback_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Excepción inesperada (fallback ServerErrorMiddleware, sin CORS) en %s %s",
            request.method,
            request.url.path,
        )
        return JSONResponse(status_code=500, content={"detail": _MENSAJE_GENERICO})

    app.add_exception_handler(Exception, _fallback_handler)

    # Catch-all real: agregado ANTES de que main.py registre CORSMiddleware, así que
    # queda adentro de CORS (ver docstring de _UnhandledExceptionMiddleware).
    app.add_middleware(_UnhandledExceptionMiddleware)
