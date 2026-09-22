"""tests/oc_presupuesto/test_router.py -- tabla de autorización del endpoint
GET /ordenes-compra/{orden_compra_id}/presupuestos-candidatos (design.md D13,
tasks.md 2.11): rol fuera de _ROLES_MATCHING -> 403; OC de otra droguería
(RLS) -> 404; OC anclada por proceso comercial (cliente_id IS NULL) -> 422.

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
