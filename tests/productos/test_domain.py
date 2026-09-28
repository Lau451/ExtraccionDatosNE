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
    ],
)
def test_parsear_unidades_por_presentacion(texto, esperado):
    assert parsear_unidades_por_presentacion(texto) == esperado
