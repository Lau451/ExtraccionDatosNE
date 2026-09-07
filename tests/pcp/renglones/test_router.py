"""5.6 (openspec/changes/gestor-pcp/tasks.md Fase 5) -- pcp-renglones router:
require_roles() rechaza un rol no autorizado antes de que el servicio toque
`pcp_renglones`; un rol autorizado sí puede crear el renglón.

Mismo criterio que tests/pcp/gestion/test_router.py (4.9): ciclo HTTP
completo (TestClient + JWT real) porque invocar la función del endpoint
directamente en Python no ejercita `Depends(require_roles(...))`. Este PR
no monta `services/pcp/renglones/router.py` en `main.py` todavía por su
cuenta -- eso lo hace el agregador (5.7) -- así que se arma una `FastAPI()`
descartable solo para este test.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.renglones.router import router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.integration
def test_crear_renglon_con_rol_no_autorizado_es_rechazado_sin_crear_fila(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    # "comercial" no está en ROLES_ESCRITURA_PCP (D11: solo admin/gerencia/compras).
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    try:
        respuesta = client.post(
            f"/pcp/{pcp['id']}/renglones",
            json={"item_proceso_id": seed_item_proceso["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 403
        en_bd = (
            service_client.table("pcp_renglones").select("id").eq("pcp_id", pcp["id"]).execute().data
        )
        assert en_bd == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_crear_renglon_con_rol_autorizado_devuelve_200_y_crea_la_fila(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    crear_usuario_con_token,
):
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    try:
        respuesta = client.post(
            f"/pcp/{pcp['id']}/renglones",
            json={"item_proceso_id": seed_item_proceso["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code < 300
        cuerpo = respuesta.json()
        assert cuerpo["pcp_id"] == pcp["id"]
        assert cuerpo["item_proceso_id"] == seed_item_proceso["id"]
        assert cuerpo["origen"] == "manual"
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
