# Shim de reexport (migración terceros-modelo, Fase 2 / D5): la implementación
# real vive en services/shared/config.py, compartida entre
# services/presupuestacion/ y services/terceros/. Este módulo se conserva
# para no romper los ~20 imports existentes de
# services.presupuestacion.core.config.
from services.shared.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
