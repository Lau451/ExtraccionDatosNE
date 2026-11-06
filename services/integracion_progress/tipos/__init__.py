"""Tipos de archivo que entran desde Progress. Agregar un tipo = agregar su carpeta
con `parser.py` (bytes → filas + errores por línea) y `destino.py` (a qué fachada se
entrega) y registrarlo en `_TIPOS_ENTRADA`."""

from types import ModuleType

from services.integracion_progress.tipos.presupuestos import destino as destino_presupuestos
from services.integracion_progress.tipos.presupuestos import parser as parser_presupuestos

# Se guardan los módulos (no las funciones) para que `parsear`/`entregar` se
# resuelvan en cada llamada.
_TIPOS_ENTRADA: dict[str, tuple[ModuleType, ModuleType]] = {
    "presupuestos": (parser_presupuestos, destino_presupuestos),
}


def tipo_entrada(tipo: str) -> tuple[ModuleType, ModuleType]:
    """(parser, destino) del tipo. ValueError si el tipo no existe."""
    try:
        return _TIPOS_ENTRADA[tipo]
    except KeyError:
        raise ValueError(f"Tipo de archivo de entrada desconocido: '{tipo}'") from None
