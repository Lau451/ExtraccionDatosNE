"""Reglas de negocio puras del catálogo de productos, sin dependencia de
Supabase ni de FastAPI -- a diferencia de service.py/repository.py, que sí
hablan con la DB."""

import re

# Único formato de `presentacion` (texto libre) del que se puede inferir un
# tamaño de pack numérico sin ambigüedad: "Presentación x N" exacto. Cualquier
# otra variante ("Pres x 1(cajax100)", "x35", "1 x 100"...) se deja en NULL --
# interpretarla sería adivinar (odd/tasks/oc-entregas-planificacion.md §
# Scope, T1). El mismo criterio se aplica en el backfill de la migración 0031.
_PATRON_PRESENTACION_NUMERICA = re.compile(r"^Presentación x ([0-9]+)$")


def parsear_unidades_por_presentacion(texto: str | None) -> int | None:
    """Extrae el tamaño de pack numérico de `productos.presentacion` cuando
    coincide EXACTAMENTE con "Presentación x N" (ej. "Presentación x 25" ->
    25). N debe ser > 0 -- "Presentación x 0" no es un tamaño de pack válido
    y se descarta igual que un formato no reconocido. Cualquier otro texto,
    o None/vacío, devuelve None."""
    if not texto:
        return None
    coincidencia = _PATRON_PRESENTACION_NUMERICA.match(texto)
    if coincidencia is None:
        return None
    numero = int(coincidencia.group(1))
    return numero if numero > 0 else None
