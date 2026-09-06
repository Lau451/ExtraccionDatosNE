"""6.5 (openspec/changes/gestor-pcp/tasks.md Fase 6) -- pcp-catalogo-proveedores
router: require_roles() rechaza un rol no autorizado antes de que el
servicio toque `producto_proveedores`; un rol autorizado sí puede crear la
asociación.

Mismo criterio que tests/pcp/renglones/test_router.py (5.6): ciclo HTTP
completo (TestClient + JWT real) porque invocar la función del endpoint
directamente en Python no ejercita `Depends(require_roles(...))`. Este PR no
monta `services/pcp/catalogo/router.py` en `main.py` por su cuenta -- eso lo
hace el agregador (`services/pcp/router.py`) -- así que se arma una
`FastAPI()` descartable solo para este test.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.pcp.catalogo.router import router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.integration
def test_agregar_proveedor_con_rol_no_autorizado_es_rechazado_sin_crear_fila(
    service_client, seed_drogueria, seed_producto, seed_proveedor_pcp, crear_usuario_con_token
):
    # "comercial" no está en ROLES_ESCRITURA_PCP (D11: solo admin/gerencia/compras).
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.post(
        f"/pcp/catalogo/productos/{seed_producto['id']}/proveedores",
        json={"proveedor_id": seed_proveedor_pcp["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403
    en_bd = (
        service_client.table("producto_proveedores")
        .select("id")
        .eq("producto_id", seed_producto["id"])
        .execute()
        .data
    )
    assert en_bd == []


@pytest.mark.integration
def test_agregar_proveedor_con_rol_autorizado_devuelve_200_y_crea_la_fila(
    service_client, seed_drogueria, seed_producto, seed_proveedor_pcp, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    try:
        respuesta = client.post(
            f"/pcp/catalogo/productos/{seed_producto['id']}/proveedores",
            json={"proveedor_id": seed_proveedor_pcp["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code < 300
        cuerpo = respuesta.json()
        assert cuerpo["producto_id"] == seed_producto["id"]
        assert cuerpo["proveedor_id"] == seed_proveedor_pcp["id"]
    finally:
        service_client.table("producto_proveedores").delete().eq(
            "producto_id", seed_producto["id"]
        ).execute()
