"""tests/oc_presupuesto/test_router.py -- tabla de autorización del endpoint
GET /ordenes-compra/{orden_compra_id}/presupuestos-candidatos (design.md D13,
tasks.md 2.11): rol fuera de _ROLES_MATCHING -> 403; OC de otra droguería
(RLS) -> 404; OC anclada por proceso comercial (cliente_id IS NULL) -> 422.

Y (Phase 3, tasks.md 3.13) la tabla de errores de D13 para los 4 endpoints de
vinculación: GET matching, POST/DELETE vinculo, POST descartar.

Ciclo HTTP completo (TestClient + JWT real vía crear_usuario_con_token), no
invocando el endpoint como función de Python: llamar a router.py directo NO
ejercita `Depends(require_roles(...))` -- FastAPI solo lo resuelve sobre un
request real (mismo criterio que tests/pcp/gestion/test_router.py). Este
router no está montado en ninguna app (eso es Phase 4, task 4.1): se arma una
FastAPI() descartable solo para este test.

Confirmar RED antes de 2.10 (deben fallar por ImportError/AttributeError
antes de que exista router.py, pasar después)."""

import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.oc_presupuesto.router import router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.integration
def test_rol_fuera_de_roles_matching_es_rechazado_con_403(
    service_client, seed_drogueria, crear_usuario_con_token
):
    # "compras" tiene lectura/escritura en otros módulos (p.ej. entregas) pero
    # NO está en _ROLES_MATCHING (D12: admin/gerencia/lider_comercial/comercial).
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.get(
        "/ordenes-compra/00000000-0000-0000-0000-000000000000/presupuestos-candidatos",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403


@pytest.mark.integration
def test_oc_de_otra_drogueria_da_404_por_rls_sin_confirmar_su_existencia(
    service_client, seed_drogueria, seed_caso_samco_rafaela, crear_usuario_con_token
):
    otra_drogueria = (
        service_client.table("droguerias")
        .insert(
            {
                "nombre": "Otra Droguería (oc_presupuesto router test)",
                "razon_social": "Otra Droguería SA",
                "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
                "ciudad": "Rosario",
                "provincia": "Santa Fe",
                "contacto_email": "otra-oc-presupuesto@seed.local",
                "contacto_telefono": "0000000000",
            }
        )
        .execute()
        .data[0]
    )
    try:
        usuario_id, token = crear_usuario_con_token(
            rol="comercial", drogueria_id=otra_drogueria["id"]
        )
        client = _cliente_de_prueba()

        respuesta = client.get(
            f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/presupuestos-candidatos",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 404
    finally:
        # fk_usuarios_drogueria: hay que borrar la fila de `usuarios` ANTES de
        # la droguería -- el teardown de crear_usuario_con_token borra el
        # usuario de auth recién DESPUÉS de que este test termine (orden
        # inverso de fixtures), así que acá todavía existe.
        service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_oc_anclada_por_proceso_comercial_sin_cliente_da_422(
    service_client, seed_drogueria, crear_usuario_con_token
):
    proceso = (
        service_client.table("procesos_comerciales")
        .insert(
            {
                "drogueria_id": seed_drogueria["id"],
                "clase": "cotizacion",
                "nombre": "Proceso sin cliente (oc_presupuesto router test)",
            }
        )
        .execute()
        .data[0]
    )
    orden_compra = (
        service_client.table("ordenes_compra")
        .insert(
            {
                "proceso_comercial_id": proceso["id"],
                "drogueria_id": seed_drogueria["id"],
                "numero_oc": f"OC-TEST-{secrets.token_hex(6)}",
            }
        )
        .execute()
        .data[0]
    )

    try:
        _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
        client = _cliente_de_prueba()

        respuesta = client.get(
            f"/ordenes-compra/{orden_compra['id']}/presupuestos-candidatos",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 422
    finally:
        service_client.table("ordenes_compra").delete().eq("id", orden_compra["id"]).execute()
        service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()


# =============================================================================
# Phase 3, 3.13 -- tabla de errores de D13 para los 4 endpoints de
# vinculación: GET matching, POST/DELETE vinculo, POST descartar.
# =============================================================================


@pytest.mark.integration
def test_matching_endpoint_devuelve_200_con_columnas_completas(
    service_client, seed_drogueria, seed_caso_samco_rafaela, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.get(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/matching",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["presupuesto_id"] == seed_caso_samco_rafaela["presupuesto_id"]
    assert len(cuerpo["renglones_oc"]) == 2


@pytest.mark.integration
def test_confirmar_vinculo_endpoint_200_hereda_producto_y_reemplaza_sin_error(
    service_client, seed_drogueria, seed_caso_samco_rafaela, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()
    oc_item = seed_caso_samco_rafaela["oc_items"][0]
    presupuesto_item = seed_caso_samco_rafaela["presupuesto_items"][0]

    respuesta = client.post(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/items/{oc_item['id']}/vinculo",
        json={"presupuesto_item_id": presupuesto_item["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 200
    renglon = next(
        r for r in respuesta.json()["renglones_oc"] if r["oc_item_id"] == oc_item["id"]
    )
    assert renglon["estado"] == "confirmado"
    assert renglon["vinculo_origen"] == "precio_exacto"

    # Re-confirmar el mismo renglón (D13: idempotente, reemplaza sin error).
    respuesta_2 = client.post(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/items/{oc_item['id']}/vinculo",
        json={"presupuesto_item_id": presupuesto_item["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta_2.status_code == 200


@pytest.mark.integration
def test_confirmar_vinculo_endpoint_presupuesto_item_excluido_da_422(
    service_client, seed_drogueria, seed_caso_samco_rafaela, crear_usuario_con_token
):
    presupuesto_item = seed_caso_samco_rafaela["presupuesto_items"][0]
    service_client.table("presupuesto_items").update({"excluido": True}).eq(
        "id", presupuesto_item["id"]
    ).execute()
    try:
        _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
        client = _cliente_de_prueba()
        oc_item = seed_caso_samco_rafaela["oc_items"][0]

        respuesta = client.post(
            f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/items/{oc_item['id']}/vinculo",
            json={"presupuesto_item_id": presupuesto_item["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 422
    finally:
        service_client.table("presupuesto_items").update({"excluido": False}).eq(
            "id", presupuesto_item["id"]
        ).execute()


@pytest.mark.integration
def test_confirmar_vinculo_endpoint_oc_item_ajeno_a_la_oc_da_404(
    service_client, seed_drogueria, seed_caso_samco_rafaela, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()
    presupuesto_item = seed_caso_samco_rafaela["presupuesto_items"][0]

    respuesta = client.post(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}"
        "/items/00000000-0000-0000-0000-000000000000/vinculo",
        json={"presupuesto_item_id": presupuesto_item["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 404


@pytest.mark.integration
def test_confirmar_vinculo_endpoint_presupuesto_item_inexistente_da_404(
    service_client, seed_drogueria, seed_caso_samco_rafaela, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()
    oc_item = seed_caso_samco_rafaela["oc_items"][0]

    respuesta = client.post(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/items/{oc_item['id']}/vinculo",
        json={"presupuesto_item_id": "00000000-0000-0000-0000-000000000000"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 404


@pytest.mark.integration
def test_deshacer_y_descartar_endpoints_200_vuelven_a_pendiente_y_sin_presupuesto(
    service_client, seed_drogueria, seed_caso_samco_rafaela, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()
    oc_item = seed_caso_samco_rafaela["oc_items"][0]
    presupuesto_item = seed_caso_samco_rafaela["presupuesto_items"][0]
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/items/{oc_item['id']}/vinculo",
        json={"presupuesto_item_id": presupuesto_item["id"]},
        headers=headers,
    )

    respuesta_undo = client.delete(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/items/{oc_item['id']}/vinculo",
        headers=headers,
    )
    assert respuesta_undo.status_code == 200
    renglon = next(
        r for r in respuesta_undo.json()["renglones_oc"] if r["oc_item_id"] == oc_item["id"]
    )
    assert renglon["estado"] == "pendiente"

    respuesta_descartar = client.post(
        f"/ordenes-compra/{seed_caso_samco_rafaela['orden_compra_id']}/items/{oc_item['id']}/descartar",
        headers=headers,
    )
    assert respuesta_descartar.status_code == 200
    renglon = next(
        r
        for r in respuesta_descartar.json()["renglones_oc"]
        if r["oc_item_id"] == oc_item["id"]
    )
    assert renglon["estado"] == "sin_presupuesto"
