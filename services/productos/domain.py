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

# Hardening (revisión RDD de T1+T2, oc-entregas-planificacion): N sin tope
# reventaría el INSERT/UPDATE contra `productos.unidades_por_presentacion
# INTEGER` (int4, tope 2147483647) con "integer out of range" en vez de
# simplemente no ofrecer el tamaño de pack -- mismo criterio que
# `_parsear_cantidad_entregas` (extraccion/service.py) y que el backfill de la
# migración 0031.
_INT4_MAX = 2_147_483_647


def parsear_unidades_por_presentacion(texto: str | None) -> int | None:
    """Extrae el tamaño de pack numérico de `productos.presentacion` cuando
    coincide EXACTAMENTE con "Presentación x N" (ej. "Presentación x 25" ->
    25). El patrón ya es ASCII estricto (`[0-9]+`, sin `\\d` Unicode), así que
    dígitos no ASCII simplemente no matchean -- no hace falta filtrarlos
    aparte. N debe ser > 0 y no puede superar el tope de int4 (Postgres
    INTEGER) -- "Presentación x 0" y un N fuera de rango no son un tamaño de
    pack válido y se descartan igual que un formato no reconocido. Cualquier
    otro texto, o None/vacío, devuelve None."""
    if not texto:
        return None
    coincidencia = _PATRON_PRESENTACION_NUMERICA.match(texto)
    if coincidencia is None:
        return None
    numero = int(coincidencia.group(1))
    return numero if 0 < numero <= _INT4_MAX else None
