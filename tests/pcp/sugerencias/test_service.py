"""10.2-10.3 (openspec/changes/gestor-pcp/tasks.md Fase 10) --
pcp-sugerencias: el mismo artículo en dos PCPs abiertos cerca de su fecha de
entrega solicitada sugiere una agrupación de cotización con la cantidad
agregada, sin fusionar ni modificar los PCPs subyacentes (spec "Suggestion
Never Auto-merges PCPs"); un precio reciente vigente (`activa=true`,
`mantenimiento_hasta` no vencido) se sugiere como referencia al abrir un
renglón de ese artículo, uno vencido no.

Ambas son consultas puras (D12: "las sugerencias son consultas, no tablas")
sobre `pcp`/`pcp_renglones` y `v_precios_especiales_vigentes`
(0012_pcp_extras.sql M6, ya vigente desde PR2) -- no hay ningún schema nuevo
en esta fase.

RED hasta que 10.1 cree services/pcp/sugerencias/{repository,service}.py.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon
from services.pcp.sugerencias.service import (
    sugerir_agrupacion_por_renglon,
    sugerir_precios_recientes_por_renglon,
)

# ---------------------------------------------------------------------------
# 10.2 -- agrupación por cantidad
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_mismo_articulo_en_dos_pcp_por_vencer_sugiere_agrupacion_con_cantidad_agregada(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_producto,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
):
    fecha_cercana = (date.today() + timedelta(days=5)).isoformat()
    item_1 = seed_item_proceso_factory(numero_renglon=1, cantidad="10")
    item_2 = seed_item_proceso_factory(numero_renglon=2, cantidad="15")
    presupuesto_1 = seed_presupuesto_factory()
    presupuesto_2 = seed_presupuesto_factory()

    pcp_1 = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_1["id"], fecha_entrega_solicitada=fecha_cercana),
        usuario_id=seed_usuario_sistema["id"],
    )
    pcp_2 = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_2["id"], fecha_entrega_solicitada=fecha_cercana),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon_1 = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp_1["id"],
        body=PcpRenglonCreate(item_proceso_id=item_1["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon_2 = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp_2["id"],
        body=PcpRenglonCreate(item_proceso_id=item_2["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )

    try:
        pcp_1_antes = service_client.table("pcp").select("*").eq("id", pcp_1["id"]).execute().data[0]
        pcp_2_antes = service_client.table("pcp").select("*").eq("id", pcp_2["id"]).execute().data[0]

        sugerencia = sugerir_agrupacion_por_renglon(
            service_client, renglon_id=renglon_1["id"], drogueria_id=seed_drogueria["id"]
        )

        assert sugerencia is not None
        assert sugerencia["producto_id"] == seed_producto["id"]
        assert sugerencia["cantidad_agregada"] == Decimal("25")
        assert set(sugerencia["pcp_ids"]) == {pcp_1["id"], pcp_2["id"]}
        assert set(sugerencia["renglon_ids"]) == {renglon_1["id"], renglon_2["id"]}

        # Viendo el otro renglón la sugerencia es la misma -- "cuando Compras
        # ve cualquiera de los dos renglones" (spec, "Suggestion surfaces for
        # a repeated article").
        sugerencia_desde_el_otro = sugerir_agrupacion_por_renglon(
            service_client, renglon_id=renglon_2["id"], drogueria_id=seed_drogueria["id"]
        )
        assert sugerencia_desde_el_otro is not None
        assert sugerencia_desde_el_otro["pcp_ids"] == sugerencia["pcp_ids"]

        # Ignorar la sugerencia nunca fusiona ni modifica los PCPs
        # subyacentes (spec "Suggestion Never Auto-merges PCPs") -- no hay
        # ningún code path de escritura en sugerir_agrupacion_por_renglon, así
        # que ambos PCPs quedan bit a bit iguales a como estaban antes de
        # calcularla.
        pcp_1_despues = service_client.table("pcp").select("*").eq("id", pcp_1["id"]).execute().data[0]
        pcp_2_despues = service_client.table("pcp").select("*").eq("id", pcp_2["id"]).execute().data[0]
        assert pcp_1_despues == pcp_1_antes
        assert pcp_2_despues == pcp_2_antes
    finally:
        service_client.table("pcp").delete().eq("id", pcp_1["id"]).execute()
        service_client.table("pcp").delete().eq("id", pcp_2["id"]).execute()


@pytest.mark.integration
def test_articulo_en_un_solo_pcp_por_vencer_no_sugiere_agrupacion(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
):
    """Triangulación negativa de 10.2: un solo PCP involucrado no alcanza el
    "más de un pcp_id distinto" que exige D12 -- nada que agrupar."""
    fecha_cercana = (date.today() + timedelta(days=5)).isoformat()
    item = seed_item_proceso_factory(numero_renglon=1)
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"], fecha_entrega_solicitada=fecha_cercana),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )

    try:
        sugerencia = sugerir_agrupacion_por_renglon(
            service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"]
        )
        assert sugerencia is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_pcp_fuera_de_la_ventana_de_dias_no_sugiere_agrupacion(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
):
    """Triangulación negativa de 10.2: dos PCPs abiertos con el mismo
    producto, pero cuya fecha_entrega_solicitada cae fuera de la ventana de
    `dias`, no son "PCPs cercanos a su fecha de entrega solicitada" (D12) --
    ninguna sugerencia."""
    fecha_lejana = (date.today() + timedelta(days=90)).isoformat()
    item_1 = seed_item_proceso_factory(numero_renglon=1)
    item_2 = seed_item_proceso_factory(numero_renglon=2)
    presupuesto_1 = seed_presupuesto_factory()
    presupuesto_2 = seed_presupuesto_factory()

    pcp_1 = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_1["id"], fecha_entrega_solicitada=fecha_lejana),
        usuario_id=seed_usuario_sistema["id"],
    )
    pcp_2 = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto_2["id"], fecha_entrega_solicitada=fecha_lejana),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon_1 = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp_1["id"],
        body=PcpRenglonCreate(item_proceso_id=item_1["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp_2["id"],
        body=PcpRenglonCreate(item_proceso_id=item_2["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )

    try:
        sugerencia = sugerir_agrupacion_por_renglon(
            service_client,
            renglon_id=renglon_1["id"],
            drogueria_id=seed_drogueria["id"],
            dias=15,
        )
        assert sugerencia is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp_1["id"]).execute()
        service_client.table("pcp").delete().eq("id", pcp_2["id"]).execute()


# ---------------------------------------------------------------------------
# 10.3 -- reuso de precio reciente
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_precio_reciente_vigente_se_sugiere_como_referencia(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    item = seed_item_proceso_factory(numero_renglon=1)
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
        body=PcpRenglonCreate(item_proceso_id=item["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    vencimiento = date.today() + timedelta(days=30)
    precio = (
        service_client.table("precios_proveedor")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "proveedor_id": seed_proveedor_pcp["id"],
                "producto_id": seed_producto["id"],
                "item_proceso_id": item["id"],
                "precio_unitario": "55.00",
                "cantidad_minima": "1",
                "cantidad_maxima": "100",
                "mantenimiento_hasta": vencimiento.isoformat(),
            }
        )
        .execute()
        .data[0]
    )

    try:
        referencias = sugerir_precios_recientes_por_renglon(
            service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"]
        )

        assert len(referencias) == 1
        referencia = referencias[0]
        # supplier, date (mantenimiento_hasta), quantity band -- spec "Valid
        # recent price is surfaced as a reference".
        assert referencia["precio_proveedor_id"] == precio["id"]
        assert referencia["proveedor"] == "Proveedor PCP Test"
        assert referencia["mantenimiento_hasta"] == vencimiento.isoformat()
        assert referencia["dias_restantes"] == 30
        assert Decimal(str(referencia["precio_unitario"])) == Decimal("55.00")
        assert Decimal(str(referencia["cantidad_minima"])) == Decimal("1")
        assert Decimal(str(referencia["cantidad_maxima"])) == Decimal("100")
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq("id", precio["id"]).execute()


@pytest.mark.integration
def test_precio_vencido_no_se_sugiere_como_referencia(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    """Simula, con un INSERT directo, una fila vieja cuya ventana ya venció
    (`fecha_oferta = mantenimiento_hasta` = hace 30 días, satisface
    `ck_pp_mant`) -- mismo criterio que
    tests/pcp/negociacion/test_service.py::test_precio_con_mantenimiento_hasta_vencido_no_es_considerado_valido:
    la vigencia es una preocupación de lectura, y acá la resuelve
    `v_precios_especiales_vigentes` (D12), no una reimplementación en
    Python."""
    item = seed_item_proceso_factory(numero_renglon=1)
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
        body=PcpRenglonCreate(item_proceso_id=item["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    hace_30_dias = (date.today() - timedelta(days=30)).isoformat()
    vencido = (
        service_client.table("precios_proveedor")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "proveedor_id": seed_proveedor_pcp["id"],
                "producto_id": seed_producto["id"],
                "item_proceso_id": item["id"],
                "precio_unitario": "42.00",
                "fecha_oferta": hace_30_dias,
                "mantenimiento_hasta": hace_30_dias,
            }
        )
        .execute()
        .data[0]
    )

    try:
        referencias = sugerir_precios_recientes_por_renglon(
            service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"]
        )
        assert referencias == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq("id", vencido["id"]).execute()


@pytest.mark.integration
def test_precio_inactivo_no_se_sugiere_como_referencia(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    """Triangulación negativa de 10.3 sobre el otro criterio del filtro
    (`activa=false`, no solo `mantenimiento_hasta` vencido) -- confirma que
    ambas condiciones de `v_precios_especiales_vigentes` (D12) se respetan,
    no solo la de fecha."""
    item = seed_item_proceso_factory(numero_renglon=1)
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
        body=PcpRenglonCreate(item_proceso_id=item["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    vencimiento = date.today() + timedelta(days=30)
    inactivo = (
        service_client.table("precios_proveedor")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "proveedor_id": seed_proveedor_pcp["id"],
                "producto_id": seed_producto["id"],
                "item_proceso_id": item["id"],
                "precio_unitario": "60.00",
                "mantenimiento_hasta": vencimiento.isoformat(),
                "activa": False,
            }
        )
        .execute()
        .data[0]
    )

    try:
        referencias = sugerir_precios_recientes_por_renglon(
            service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"]
        )
        assert referencias == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("precios_proveedor").delete().eq("id", inactivo["id"]).execute()
