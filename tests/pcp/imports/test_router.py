"""8.8 (openspec/changes/gestor-pcp/tasks.md Fase 8) + T2 (odd/tasks/
presupuestos-legacy-import.md, agreed design 2026-09-24) -- router de import
legado de PCP: `require_roles()` rechaza un rol no autorizado antes de que el
servicio toque ninguna tabla; un rol autorizado sí crea el PCP, siempre que
su `numero_presupuesto` ya haya sido importado (T2 -- el import de PCP ya
nunca crea placeholders). Este `router` monta también
`/pcp/imports/presupuestos-legacy` (mismo router que
`services/pcp/imports/router.py`), así que el setup de estos tests importa el
presupuesto por ese mismo ciclo HTTP antes de importar el PCP.

Mismo criterio que tests/pcp/catalogo/test_router.py (6.5): ciclo HTTP
completo (TestClient + JWT real) porque invocar la función del endpoint
directamente no ejercita `Depends(require_roles(...))`. Este PR no monta
`services/pcp/imports/router.py` en `main.py` por su cuenta -- eso lo hace el
agregador (`services/pcp/router.py`) -- así que se arma una `FastAPI()`
descartable solo para este test.
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


def _payload_presupuesto(*, codigo_cliente: str, numero_presupuesto: str, renglon: int = 1) -> dict:
    return {
        "filas": [
            {
                "codigo_cliente": codigo_cliente,
                "razon_social_cliente": "Hospital Router Test",
                "numero_presupuesto": numero_presupuesto,
                "renglon": renglon,
                "descripcion_producto": "Producto router test",
                "cantidad_producto": "10",
            }
        ]
    }


def _payload(*, codigo_cliente: str, numero_pcp: str, numero_presupuesto: str) -> dict:
    return {
        "filas": [
            {
                "codigo_cliente": codigo_cliente,
                "razon_social_cliente": "Hospital Router Test",
                "numero_pcp": numero_pcp,
                "numero_presupuesto": numero_presupuesto,
                "renglon": 1,
                "descripcion_producto": "Producto router test",
                "cantidad_producto": "10",
            }
        ]
    }


@pytest.mark.integration
def test_importar_con_rol_no_autorizado_es_rechazado_sin_crear_ningun_pcp(
    service_client, seed_drogueria, seed_cliente_pcp_factory, crear_usuario_con_token
):
    seed_cliente_pcp_factory(codigo_interno="CLI-ROUTER-001")
    # "comercial" no está en ROLES_ESCRITURA_PCP (D11: solo admin/gerencia/compras).
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.post(
        "/pcp/imports/legacy",
        json=_payload(
            codigo_cliente="CLI-ROUTER-001",
            numero_pcp="PCP-ROUTER-001",
            numero_presupuesto="PRE-ROUTER-001",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403
    mapa = (
        service_client.table("pcp_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", "PCP-ROUTER-001")
        .execute()
        .data
    )
    assert mapa == []


@pytest.mark.integration
def test_importar_con_rol_autorizado_devuelve_200_y_crea_el_pcp(
    service_client, seed_drogueria, seed_cliente_pcp_factory, crear_usuario_con_token
):
    seed_cliente_pcp_factory(codigo_interno="CLI-ROUTER-002")
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    # T2: el import de PCP exige un presupuesto ya importado -- se arma acá
    # mismo, por el ciclo HTTP hermano que ya expone este router.
    respuesta_presupuesto = client.post(
        "/pcp/imports/presupuestos-legacy",
        json=_payload_presupuesto(codigo_cliente="CLI-ROUTER-002", numero_presupuesto="PRE-ROUTER-002"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta_presupuesto.status_code == 200

    respuesta = client.post(
        "/pcp/imports/legacy",
        json=_payload(
            codigo_cliente="CLI-ROUTER-002",
            numero_pcp="PCP-ROUTER-002",
            numero_presupuesto="PRE-ROUTER-002",
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    try:
        assert cuerpo[0]["accion"] == "creado"
        assert cuerpo[0]["renglones_procesados"] == 1
    finally:
        pcp = service_client.table("pcp").select("*").eq("id", cuerpo[0]["pcp_id"]).execute().data[0]
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("presupuestos").delete().eq("id", pcp["presupuesto_id"]).execute()
        service_client.table("procesos_comerciales").delete().eq(
            "id", pcp["proceso_comercial_id"]
        ).execute()
