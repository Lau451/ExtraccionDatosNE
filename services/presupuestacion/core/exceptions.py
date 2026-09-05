# Shim de reexport (migración terceros-modelo, Fase 2 / D5): la implementación
# real vive en services/shared/exceptions.py, compartida entre
# services/presupuestacion/ y services/terceros/ (D3 reusa este mismo set de
# excepciones, no agrega tipos nuevos). Este módulo se conserva para no romper
# los ~20 imports existentes de services.presupuestacion.core.exceptions.
from services.shared.exceptions import (
    STATUS_MAP,
    ConflictError,
    DomainError,
    ExtraccionNoDisponibleError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    register_exception_handlers,
)

__all__ = [
    "STATUS_MAP",
    "ConflictError",
    "DomainError",
    "ExtraccionNoDisponibleError",
    "ForbiddenError",
    "NotFoundError",
    "ValidationError",
    "AuthenticationError",
    "register_exception_handlers",
]
