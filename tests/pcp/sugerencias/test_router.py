"""10.4 (openspec/changes/gestor-pcp/tasks.md Fase 10) -- pcp-sugerencias
router: `require_roles(*ROLES_LECTURA_PCP)` gatea ambos endpoints de
lectura -- un rol no incluido en ese conjunto (D11) es rechazado antes de
que el servicio toque nada; un rol autorizado sí puede leer.

Mismo criterio que tests/pcp/catalogo/test_router.py (6.5): ciclo HTTP
completo (TestClient + JWT real) porque invocar la función del endpoint
directamente en Python no ejercita `Depends(require_roles(...))`. Este PR no
monta `services/pcp/sugerencias/router.py` en `main.py` por su cuenta -- eso
lo hace el agregador (`services/pcp/router.py`) -- así que se arma una
`FastAPI()` descartable solo para este test.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon
from services.pcp.sugerencias.router import router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.integration
def test_sugerencia_precios_recientes_con_rol_no_autorizado_es_rechazada(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    crear_usuario_con_token,
):
    # "comercial" no está en ROLES_LECTURA_PCP (D11: solo
    # superadmin/admin/gerencia/compras) -- ni siquiera puede leer
    # sugerencias, mismo criterio que el resto de services/pcp/.
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
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    try:
        respuesta = client.get(
            f"/pcp/sugerencias/renglones/{renglon['id']}/precios-recientes",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert respuesta.status_code == 403
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_sugerencia_precios_recientes_con_rol_autorizado_devuelve_200(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    crear_usuario_con_token,
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
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    try:
        respuesta = client.get(
            f"/pcp/sugerencias/renglones/{renglon['id']}/precios-recientes",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert respuesta.status_code == 200
        # Sin precios_proveedor sembrados en este test -- lista vacía, no un
        # error (spec/D12: la ausencia de una referencia no es una falla).
        assert respuesta.json() == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


@pytest.mark.integration
def test_sugerencia_agrupacion_con_rol_autorizado_devuelve_200(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    crear_usuario_con_token,
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
    _, token = crear_usuario_con_token(rol="gerencia", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    try:
        respuesta = client.get(
            f"/pcp/sugerencias/renglones/{renglon['id']}/agrupacion",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert respuesta.status_code == 200
        # Único PCP para este producto -- sin sugerencia (null), no un error.
        assert respuesta.json() is None
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
