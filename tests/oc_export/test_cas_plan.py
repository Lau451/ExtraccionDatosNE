"""tests/oc_export/test_cas_plan.py -- migración 0033: RPC `marcar_oc_exportada` /
`hash_plan_oc` y triggers que congelan el plan de una OC exportada. Requieren que 0033 esté
aplicada en el proyecto TEST; si no lo está se saltean (no es un pase)."""

import uuid

import pytest
from postgrest.exceptions import APIError

SQLSTATE_OC_EXPORTADA = "OC409"


@pytest.fixture
def requiere_0033(service_client):
    try:
        service_client.rpc("hash_plan_oc", {"p_orden_compra_id": str(uuid.uuid4())}).execute()
    except APIError as exc:
        if exc.code == "PGRST202":  # función inexistente en el schema cache
            pytest.skip("La migración 0033 no está aplicada en el proyecto TEST")
        raise


def _hash(service_client, orden_id: str) -> str:
    return service_client.rpc("hash_plan_oc", {"p_orden_compra_id": orden_id}).execute().data


def _marcar(
    service_client, caso, usuario_id: str, plan_hash: str, drogueria_id: str | None = None
) -> str:
    return (
        service_client.rpc(
            "marcar_oc_exportada",
            {
                "p_orden_compra_id": caso["orden_compra_id"],
                "p_drogueria_id": drogueria_id or caso["oc_item_con_pack"]["drogueria_id"],
                "p_usuario_id": usuario_id,
                "p_archivo": "OC_cas_test.csv",
                "p_plan_hash": plan_hash,
            },
        )
        .execute()
        .data
    )


def _oc(service_client, orden_id: str) -> dict:
    return (
        service_client.table("ordenes_compra")
        .select("exportado_at, exportado_por, archivo_exportado")
        .eq("id", orden_id)
        .execute()
        .data[0]
    )


@pytest.fixture
def usuario(crear_usuario_con_token, seed_drogueria):
    usuario_id, _ = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    return usuario_id


@pytest.mark.integration
def test_marcar_con_el_hash_vigente_marca_y_la_segunda_vez_da_ya_exportada(
    requiere_0033, service_client, caso_exportable, usuario
):
    orden_id = caso_exportable["orden_compra_id"]
    plan_hash = _hash(service_client, orden_id)

    assert _marcar(service_client, caso_exportable, usuario, plan_hash) == "ok"
    oc = _oc(service_client, orden_id)
    assert oc["exportado_at"] is not None and oc["exportado_por"] == usuario
    assert oc["archivo_exportado"] == "OC_cas_test.csv"
    assert _marcar(service_client, caso_exportable, usuario, plan_hash) == "ya_exportada"


@pytest.mark.integration
def test_marcar_con_el_plan_cambiado_no_marca(
    requiere_0033, service_client, caso_exportable, usuario
):
    orden_id = caso_exportable["orden_compra_id"]
    plan_hash = _hash(service_client, orden_id)
    service_client.table("entregas_oc").update({"fecha_entrega_planificada": "2026-12-31"}).eq(
        "orden_compra_id", orden_id
    ).eq("numero_entrega", 1).execute()

    assert _hash(service_client, orden_id) != plan_hash
    assert _marcar(service_client, caso_exportable, usuario, plan_hash) == "plan_cambiado"
    assert _oc(service_client, orden_id)["exportado_at"] is None


@pytest.mark.integration
def test_marcar_de_otra_drogueria_da_no_encontrada(
    requiere_0033, service_client, caso_exportable, usuario
):
    assert (
        _marcar(service_client, caso_exportable, usuario, "x", drogueria_id=str(uuid.uuid4()))
        == "no_encontrada"
    )


@pytest.fixture
def oc_exportada(requiere_0033, service_client, caso_exportable, usuario):
    orden_id = caso_exportable["orden_compra_id"]
    assert _marcar(service_client, caso_exportable, usuario, _hash(service_client, orden_id)) == "ok"
    return caso_exportable


@pytest.mark.integration
def test_trigger_rechaza_insert_y_delete_del_plan_de_una_oc_exportada(
    service_client, oc_exportada
):
    orden_id = oc_exportada["orden_compra_id"]
    with pytest.raises(APIError) as exc:
        service_client.table("entregas_oc").insert(
            {
                "orden_compra_id": orden_id,
                "drogueria_id": oc_exportada["oc_item_con_pack"]["drogueria_id"],
                "numero_entrega": 9,
                "fecha_entrega_planificada": "2026-12-01",
                "cantidad_items": 0,
                "estado": "pendiente",
            }
        ).execute()
    assert exc.value.code == SQLSTATE_OC_EXPORTADA

    with pytest.raises(APIError) as exc:
        service_client.table("entregas_oc").delete().eq("orden_compra_id", orden_id).eq(
            "estado", "pendiente"
        ).execute()
    assert exc.value.code == SQLSTATE_OC_EXPORTADA


@pytest.mark.integration
def test_trigger_rechaza_cambiar_la_cantidad_planificada_de_una_oc_exportada(
    service_client, oc_exportada
):
    entrega = (
        service_client.table("entregas_oc")
        .select("id")
        .eq("orden_compra_id", oc_exportada["orden_compra_id"])
        .eq("numero_entrega", 1)
        .execute()
        .data[0]
    )
    with pytest.raises(APIError) as exc:
        service_client.table("entregas_oc_items").update({"cantidad_planificada": "1"}).eq(
            "entrega_oc_id", entrega["id"]
        ).execute()
    assert exc.value.code == SQLSTATE_OC_EXPORTADA


@pytest.mark.integration
def test_trigger_deja_pasar_estado_y_registro_de_entregas_reales_tras_exportar(
    service_client, oc_exportada
):
    """Flujos legítimos posteriores a la exportación: cambio de estado de una entrega y
    registro de una entrega real (fecha_entrega_real, cantidad_planificada = 0)."""
    orden_id = oc_exportada["orden_compra_id"]
    service_client.table("entregas_oc").update({"estado": "en_transito"}).eq(
        "orden_compra_id", orden_id
    ).eq("numero_entrega", 1).execute()

    real = (
        service_client.table("entregas_oc")
        .insert(
            {
                "orden_compra_id": orden_id,
                "drogueria_id": oc_exportada["oc_item_con_pack"]["drogueria_id"],
                "numero_entrega": 9,
                "fecha_entrega_real": "2026-10-20",
                "cantidad_items": 1,
                "estado": "entregada",
            }
        )
        .execute()
        .data[0]
    )
    service_client.table("entregas_oc_items").insert(
        {
            "entrega_oc_id": real["id"],
            "drogueria_id": oc_exportada["oc_item_con_pack"]["drogueria_id"],
            "oc_item_id": oc_exportada["oc_item_con_pack"]["id"],
            "cantidad_entregada": "5",
        }
    ).execute()
