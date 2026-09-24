"""Router de import legado de presupuestos (odd/tasks/presupuestos-legacy-import.md
T1). Mismo criterio que tests/pcp/imports/test_router.py (8.8): ciclo HTTP
completo (TestClient + JWT real) porque invocar la función del endpoint
directamente no ejercita `Depends(require_roles(...))`. Se arma una
`FastAPI()` descartable con el router de `services/pcp/imports` (mismo router
que ya monta `/pcp/imports/legacy`, ahora también expone
`/pcp/imports/presupuestos-legacy`).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.pcp.imports.router import router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


def _payload(*, codigo_cliente: str, numero_presupuesto: str) -> dict:
    return {
        "filas": [
            {
                "codigo_cliente": codigo_cliente,
                "razon_social_cliente": "Hospital Router Presupuesto Test",
                "numero_presupuesto": numero_presupuesto,
                "renglon": 1,
                "descripcion_producto": "Producto router test",
                "cantidad_producto": "10",
            }
        ]
    }


@pytest.mark.integration
def test_importar_con_rol_no_autorizado_es_rechazado_sin_crear_nada(
    service_client, seed_drogueria, seed_cliente_pcp_factory, crear_usuario_con_token
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-ROUTER-001")
    # "comercial" no está en ROLES_ESCRITURA_PCP (mismo gate que /pcp/imports/legacy).
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.post(
        "/pcp/imports/presupuestos-legacy",
        json=_payload(codigo_cliente="CLI-PRE-ROUTER-001", numero_presupuesto="PRE-ROUTER-001"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403
    mapa = (
        service_client.table("presupuesto_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", "PRE-ROUTER-001")
        .execute()
        .data
    )
    assert mapa == []


@pytest.mark.integration
def test_importar_con_rol_autorizado_devuelve_200_y_crea_el_presupuesto(
    service_client, seed_drogueria, seed_cliente_pcp_factory, crear_usuario_con_token
):
    seed_cliente_pcp_factory(codigo_interno="CLI-PRE-ROUTER-002")
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.post(
        "/pcp/imports/presupuestos-legacy",
        json=_payload(codigo_cliente="CLI-PRE-ROUTER-002", numero_presupuesto="PRE-ROUTER-002"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    try:
        assert cuerpo[0]["accion"] == "creado"
        assert cuerpo[0]["renglones_procesados"] == 1
        assert cuerpo[0]["renglones_sin_producto"] == 1
    finally:
        presupuesto = (
            service_client.table("presupuestos")
            .select("*")
            .eq("id", cuerpo[0]["presupuesto_id"])
            .execute()
            .data[0]
        )
        service_client.table("presupuestos").delete().eq("id", presupuesto["id"]).execute()
        service_client.table("procesos_comerciales").delete().eq(
            "id", presupuesto["proceso_comercial_id"]
        ).execute()
