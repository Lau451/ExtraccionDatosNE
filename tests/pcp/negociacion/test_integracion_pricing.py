"""7.8 (openspec/changes/gestor-pcp/tasks.md Fase 7) -- prueba de integración
más importante de este PR: un resultado `precio_obtenido` registrado por
`pcp-negociacion` es recogido automáticamente por
`services/presupuestacion/pricing/repository.py::buscar_precio_especial_puntual`,
confirmando la historia completa de "el resultado de una negociación de PCP
fluye al motor de pricing sin ningún paso manual" en la que se basó la
propuesta (design.md D4).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.negociacion.models import RegistrarResultadoNegociacion
from services.pcp.negociacion.service import registrar_resultado
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon, seleccionar_proveedores
from services.presupuestacion.pricing.repository import buscar_precio_especial_puntual


@pytest.mark.integration
def test_precio_obtenido_es_recogido_por_buscar_precio_especial_puntual(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        resultado = registrar_resultado(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_renglon_id=renglon["id"],
            proveedor_id=seed_proveedor_pcp["id"],
            body=RegistrarResultadoNegociacion(
                resultado="precio_obtenido",
                precio_unitario=Decimal("64.90"),
                mantenimiento_hasta=date.today() + timedelta(days=45),
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        precio_para_pricing = buscar_precio_especial_puntual(
            service_client, item_proceso_id=seed_item_proceso["id"], cantidad=Decimal("1")
        )

        assert precio_para_pricing is not None
        assert precio_para_pricing["id"] == resultado["precio_proveedor_id"]
        assert Decimal(str(precio_para_pricing["precio_unitario"])) == Decimal("64.90")
        assert precio_para_pricing["proveedor_id"] == seed_proveedor_pcp["id"]
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq(
            "item_proceso_id", seed_item_proceso["id"]
        ).execute()
