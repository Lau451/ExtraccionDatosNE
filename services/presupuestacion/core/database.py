# Shim de reexport (migración terceros-modelo, Fase 2 / D5): la implementación
# real vive en services/shared/database.py, compartida entre
# services/presupuestacion/ y services/terceros/. Este módulo se conserva
# para no romper los ~20 imports existentes de
# services.presupuestacion.core.database.
from services.shared.database import get_bearer_token, get_service_client, get_user_client

__all__ = ["get_bearer_token", "get_service_client", "get_user_client"]
