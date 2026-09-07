"""4.9 (openspec/changes/gestor-pcp/tasks.md Fase 4) -- pcp-gestion router:
require_roles() rechaza un rol no autorizado en los endpoints de escritura,
antes de que el servicio toque la tabla `pcp`.

Ciclo HTTP completo (TestClient + JWT real vía crear_usuario_con_token) en vez
de invocar la función del endpoint directamente en Python: llamar al endpoint
como función de Python no ejercita `Depends(require_roles(...))` -- FastAPI
solo lo invoca cuando resuelve dependencias sobre un request real. Este PR no
monta `services/pcp/gestion/router.py` en ninguna app (eso es 5.7); se arma
una `FastAPI()` descartable solo para este test.

RED hasta que 4.9 cree services/pcp/gestion/router.py.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.pcp.gestion.router import router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.integration
def test_crear_pcp_con_rol_no_autorizado_es_rechazado_sin_crear_fila(
    service_client, seed_drogueria, seed_presupuesto_factory, crear_usuario_con_token
):
    presupuesto = seed_presupuesto_factory()
    # "comercial" tiene lectura/escritura en otros módulos (p.ej. terceros)
    # pero NO está en _ROLES_ESCRITURA_PCP (D11: solo admin/gerencia/compras).
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.post(
        "/pcp",
        json={"presupuesto_id": presupuesto["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403
    en_bd = (
        service_client.table("pcp")
        .select("id")
        .eq("presupuesto_id", presupuesto["id"])
        .execute()
        .data
    )
    assert en_bd == []


@pytest.mark.integration
def test_cambiar_estado_con_rol_no_autorizado_es_rechazado_sin_modificar_fila(
    service_client, seed_drogueria, seed_pcp_factory, crear_usuario_con_token
):
    pcp = seed_pcp_factory()
    # "lider_comercial" tampoco está en _ROLES_ESCRITURA_PCP.
    _, token = crear_usuario_con_token(rol="lider_comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.patch(
        f"/pcp/{pcp['id']}/estado",
        json={"estado": "en_gestion"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403
    en_bd = service_client.table("pcp").select("estado").eq("id", pcp["id"]).execute().data[0]
    assert en_bd["estado"] == "nueva"


@pytest.mark.integration
def test_crear_pcp_con_rol_autorizado_devuelve_201_o_200_y_crea_la_fila(
    service_client, seed_drogueria, seed_presupuesto_factory, crear_usuario_con_token
):
    """Contraparte GREEN del rechazo: confirma que _ROLES_ESCRITURA_PCP no
    está vacío ni mal armado (p.ej. que 'compras' no quedó afuera por error
    al escribir la constante)."""
    presupuesto = seed_presupuesto_factory()
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.post(
        "/pcp",
        json={"presupuesto_id": presupuesto["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    try:
        assert respuesta.status_code < 300
        cuerpo = respuesta.json()
        assert cuerpo["presupuesto_id"] == presupuesto["id"]
        assert cuerpo["drogueria_id"] == seed_drogueria["id"]
    finally:
        service_client.table("pcp").delete().eq("presupuesto_id", presupuesto["id"]).execute()
