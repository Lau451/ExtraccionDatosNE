"""5.2-5.5 (openspec/changes/gestor-pcp/tasks.md Fase 5) -- pcp-renglones:
ancla en item_proceso_id (nunca presupuesto_items.id), detalle con datos de
producto + proveedores catalogados, selección de proveedores para negociar,
y el discriminador `origen`.

RED hasta que 5.6 cree services/pcp/renglones/{models,repository,service}.py.
"""

from postgrest.exceptions import APIError
from pydantic import ValidationError
import pytest

from services.pcp.catalogo.models import ProductoProveedorCreate
from services.pcp.catalogo.service import agregar_proveedor
from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.renglones import repository as repo
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import (
    crear_renglon,
    obtener_detalle_renglon,
    obtener_renglon,
    seleccionar_proveedores,
)
from services.shared.exceptions import ValidationError as ServiceValidationError

# ---------------------------------------------------------------------------
# 5.2a -- el renglón anclado en item_proceso_id sigue resolviendo después de
# que presupuesto_items se borra e inserta de nuevo (RN-PRICING-008)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_renglon_sobrevive_regeneracion_de_presupuesto_items(
    service_client,
    seed_drogueria,
    seed_proceso_comercial,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    limpiar_presupuestos,
):
    from services.presupuestacion.pricing.service import generar_presupuesto_para_endpoint

    primera = generar_presupuesto_para_endpoint(
        proceso_comercial_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        disparado_por=seed_usuario_sistema["id"],
    )
    limpiar_presupuestos.append(primera.presupuesto_id)
    assert primera.regenerado is False

    presupuesto_item_v1 = (
        service_client.table("presupuesto_items")
        .select("id")
        .eq("presupuesto_id", primera.presupuesto_id)
        .eq("item_proceso_id", seed_item_proceso["id"])
        .execute()
        .data[0]
    )

    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=primera.presupuesto_id),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )

    # Regeneración real: segunda corrida sobre el mismo proceso_comercial_id
    # borra e inserta de nuevo presupuesto_items (RN-PRICING-008).
    segunda = generar_presupuesto_para_endpoint(
        proceso_comercial_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        disparado_por=seed_usuario_sistema["id"],
    )
    assert segunda.regenerado is True
    assert segunda.presupuesto_id == primera.presupuesto_id

    presupuesto_item_v2 = (
        service_client.table("presupuesto_items")
        .select("id")
        .eq("presupuesto_id", segunda.presupuesto_id)
        .eq("item_proceso_id", seed_item_proceso["id"])
        .execute()
        .data[0]
    )
    # Prueba que hubo un DELETE+INSERT real, no un UPDATE in-place.
    assert presupuesto_item_v2["id"] != presupuesto_item_v1["id"]

    resuelto = obtener_renglon(service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"])
    assert resuelto["id"] == renglon["id"]
    assert resuelto["item_proceso_id"] == seed_item_proceso["id"]

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 5.2b -- rechazar una request que identifica el renglón solo por presupuesto_items.id
# ---------------------------------------------------------------------------


def test_crear_renglon_rechaza_identificacion_por_presupuesto_item_id():
    with pytest.raises(ValidationError) as exc_info:
        PcpRenglonCreate(item_proceso_id="item-real", presupuesto_item_id="pi-no-permitido")
    assert "presupuesto_item_id" in str(exc_info.value)


def test_crear_renglon_requiere_item_proceso_id():
    with pytest.raises(ValidationError):
        PcpRenglonCreate(presupuesto_item_id="pi-no-permitido")


# ---------------------------------------------------------------------------
# 5.3 -- detalle del renglón: datos de producto + proveedores catalogados
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_detalle_renglon_muestra_datos_de_producto_y_proveedores_catalogados_vacio(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
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

    detalle = obtener_detalle_renglon(
        service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"]
    )

    assert detalle["producto"]["id"] == seed_producto["id"]
    assert detalle["producto"]["nombre"] == seed_producto["nombre"]
    # Catálogo real (D3, PR6) sin ninguna asociación cargada para este
    # producto todavía -- caso legítimo de "Empty Catalog on Day One"
    # (spec pcp-catalogo-proveedores), no el placeholder de PR5.
    assert detalle["proveedores_catalogados"] == []

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 6.5 (wiring PR6) -- un proveedor catalogado real aparece en el detalle del
# renglón; el placeholder [] de PR5 quedó reemplazado por una lectura real.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_detalle_renglon_muestra_proveedor_catalogado_real(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    asociacion = agregar_proveedor(
        service_client,
        drogueria_id=seed_drogueria["id"],
        producto_id=seed_producto["id"],
        body=ProductoProveedorCreate(proveedor_id=seed_proveedor_pcp["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
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

    try:
        detalle = obtener_detalle_renglon(
            service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"]
        )

        assert len(detalle["proveedores_catalogados"]) == 1
        assert detalle["proveedores_catalogados"][0]["proveedor_id"] == seed_proveedor_pcp["id"]
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("producto_proveedores").delete().eq("id", asociacion["id"]).execute()


@pytest.mark.integration
def test_detalle_renglon_sin_producto_asociado_no_intenta_resolverlo(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_sin_producto,
    seed_presupuesto_factory,
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
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso_sin_producto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )

    detalle = obtener_detalle_renglon(
        service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"]
    )

    assert renglon["producto_id"] is None
    assert detalle["producto"] is None
    assert detalle["proveedores_catalogados"] == []

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 5.4 -- selección de un proveedor vs. todos los disponibles como objetivo de negociación
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_seleccionar_un_proveedor_registra_una_fila_pcp_renglon_resultados_sin_respuesta(
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

    resultado = seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    assert len(resultado) == 1
    assert resultado[0]["proveedor_id"] == seed_proveedor_pcp["id"]
    assert resultado[0]["resultado"] == "sin_respuesta"

    en_bd = (
        service_client.table("pcp_renglon_resultados")
        .select("*")
        .eq("pcp_renglon_id", renglon["id"])
        .execute()
        .data
    )
    assert len(en_bd) == 1

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_seleccionar_todos_los_proveedores_disponibles_registra_una_fila_por_cada_uno(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedores_pcp_factory,
):
    proveedores = seed_proveedores_pcp_factory(3)
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

    resultado = seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[p["id"] for p in proveedores],
    )

    assert len(resultado) == 3
    assert {r["proveedor_id"] for r in resultado} == {p["id"] for p in proveedores}
    assert all(r["resultado"] == "sin_respuesta" for r in resultado)

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_seleccionar_proveedores_sin_ninguno_lanza_error_de_validacion(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
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

    with pytest.raises(ServiceValidationError):
        seleccionar_proveedores(
            service_client, renglon_id=renglon["id"], drogueria_id=seed_drogueria["id"], proveedor_ids=[]
        )

    en_bd = (
        service_client.table("pcp_renglon_resultados")
        .select("id")
        .eq("pcp_renglon_id", renglon["id"])
        .execute()
        .data
    )
    assert len(en_bd) == 0

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 5.5 -- origen: la selección manual se etiqueta 'manual'; un valor fuera de
# manual/regla/import_legado se rechaza (CHECK de la base)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_renglon_manual_sin_origen_explicito_se_etiqueta_manual(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
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

    assert renglon["origen"] == "manual"

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_crear_renglon_con_origen_import_legado_explicito_se_acepta(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
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
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"], origen="import_legado"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert renglon["origen"] == "import_legado"

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_origen_invalido_es_rechazado_por_el_check_de_la_base(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )

    with pytest.raises(APIError) as exc_info:
        repo.crear_renglon(
            service_client,
            {
                "drogueria_id": seed_drogueria["id"],
                "pcp_id": pcp["id"],
                "item_proceso_id": seed_item_proceso["id"],
                "origen": "invalido",
            },
        )
    assert exc_info.value.code == "23514"  # check_violation (ck_pcpr_origen)

    en_bd = service_client.table("pcp_renglones").select("id").eq("pcp_id", pcp["id"]).execute().data
    assert len(en_bd) == 0

    service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
