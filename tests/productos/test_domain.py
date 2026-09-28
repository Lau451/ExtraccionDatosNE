import pytest

from services.productos.domain import parsear_unidades_por_presentacion

# =============================================================================
# T1 (oc-entregas-planificacion) -- parsear_unidades_por_presentacion. Único
# formato reconocido: "Presentación x N" exacto (N > 0). Cualquier otra
# variante ("Pres x 1(cajax100)", "x35"...) es ambigua y se descarta a NULL --
# mismo criterio que el backfill de la migración 0031.
# =============================================================================


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Presentación x 25", 25),
        ("Presentación x 1", 1),
        ("Pres x 1(cajax100)", None),
        ("x35", None),
        (None, None),
        ("", None),
        ("Presentación x 0", None),
        # Hardening (revisión RDD de T1+T2, oc-entregas-planificacion): N sin
        # tope reventaría el INSERT/UPDATE con "integer out of range" contra
        # `productos.unidades_por_presentacion INTEGER` (int4, tope 2147483647)
        # en vez de simplemente no ofrecer el tamaño de pack -- mismo criterio
        # que _parsear_cantidad_entregas (extraccion/service.py).
        ("Presentación x 2147483647", 2_147_483_647),  # tope int4 exacto, sigue OK
        ("Presentación x 2147483648", None),  # 1 por encima del tope -> None
        ("Presentación x 99999999999999", None),  # muy por encima del tope
    ],
)
def test_parsear_unidades_por_presentacion(texto, esperado):
    assert parsear_unidades_por_presentacion(texto) == esperado
