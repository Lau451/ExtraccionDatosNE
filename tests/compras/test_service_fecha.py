"""Una entrega sin fecha real queda con la fecha de Argentina, no la del
servidor (`reloj_noche_argentina`: 22:30 del 8/11 en Buenos Aires)."""

from decimal import Decimal

from services.presupuestacion.compras import service
from services.presupuestacion.compras.models import EntregaItemRequest


def test_entrega_sin_fecha_real_usa_la_fecha_de_argentina(monkeypatch, reloj_noche_argentina):
    filas_entrega: list[dict] = []
    monkeypatch.setattr(
        service.repo,
        "buscar_orden_compra",
        lambda client, orden_compra_id: {"id": orden_compra_id, "drogueria_id": "d", "estado": "emitida"},
    )
    monkeypatch.setattr(
        service.repo, "listar_oc_items", lambda client, orden_compra_id: [{"id": "it", "producto_id": None}]
    )
    monkeypatch.setattr(service.repo, "listar_entregas_por_orden", lambda client, orden_compra_id: [])
    monkeypatch.setattr(
        service.repo, "crear_entrega", lambda client, fila: filas_entrega.append(fila) or {"id": "e"}
    )
    monkeypatch.setattr(service.repo, "insertar_entrega_items", lambda client, filas: None)
    monkeypatch.setattr(
        service, "_recalcular_estado_orden_compra", lambda client, orden_compra_id: "entregada"
    )

    service.crear_entrega(
        None,
        orden_compra_id="oc",
        items=[EntregaItemRequest(oc_item_id="it", cantidad_entregada=Decimal("1"))],
        fecha_entrega_planificada=None,
        fecha_entrega_real=None,
        observaciones=None,
    )

    assert [fila["fecha_entrega_real"] for fila in filas_entrega] == ["2026-11-08"]
