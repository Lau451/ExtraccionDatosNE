# Shim de reexport (migración terceros-modelo, Fase 3 / D5): la implementación
# real vive en services/shared/auth.py, compartida entre
# services/presupuestacion/ y services/terceros/ — el blocker original de D5
# solo mencionaba config/database/exceptions, pero services/terceros/*/router.py
# necesita UsuarioPerfil/require_roles igual que los demás. Este módulo se
# conserva para no romper los ~20 imports existentes de
# services.presupuestacion.core.auth.
from services.shared.auth import (
    UserClaims,
    UsuarioPerfil,
    get_current_claims,
    get_current_user,
    require_roles,
)

__all__ = [
    "UserClaims",
    "UsuarioPerfil",
    "get_current_claims",
    "get_current_user",
    "require_roles",
]
