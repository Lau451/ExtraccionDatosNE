"""tests/oc_resumen/test_router.py -- autorización y forma de
GET /ordenes-compra/{orden_compra_id}/resumen (odd/tasks/oc-resumen.md, T1).
Ciclo HTTP completo (TestClient + JWT real), mismo criterio que
tests/oc_entregas/test_router.py."""

import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.core.auth import UsuarioPerfil, get_current_user
from services.presupuestacion.oc_resumen.router import _ROLES_LECTURA, router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


def _get(client: TestClient, orden_compra_id: str, token: str):
    return client.get(
        f"/ordenes-compra/{orden_compra_id}/resumen",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_rol_fuera_de_roles_lectura_es_rechazado_con_403():
    # "sistema" es un rol válido de usuarios (ck_usuarios_rol) fuera de _ROLES_LECTURA, pero
    # ck_usuarios_es_sistema impide sembrarlo como usuario común: se inyecta el perfil.
    assert "sistema" not in _ROLES_LECTURA
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: UsuarioPerfil(
        id="u-1", drogueria_id="d1", rol="sistema"
    )

    respuesta = TestClient(app).get("/ordenes-compra/oc-1/resumen")

    assert respuesta.status_code == 403


@pytest.mark.integration
def test_oc_inexistente_da_404(seed_drogueria, crear_usuario_con_token):
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])

    respuesta = _get(_cliente_de_prueba(), "00000000-0000-0000-0000-000000000000", token)

    assert respuesta.status_code == 404


@pytest.mark.integration
def test_oc_de_otra_drogueria_da_404(
    service_client, seed_drogueria, seed_caso_resumen, crear_usuario_con_token
):
    otra_drogueria = (
        service_client.table("droguerias")
        .insert(
            {
                "nombre": "Otra Droguería (oc_resumen router test)",
                "razon_social": "Otra Droguería SA",
                "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
                "ciudad": "Rosario",
                "provincia": "Santa Fe",
                "contacto_email": "otra-oc-resumen@seed.local",
                "contacto_telefono": "0000000000",
            }
        )
        .execute()
        .data[0]
    )
    usuario_id = None
    try:
        usuario_id, token = crear_usuario_con_token(rol="comercial", drogueria_id=otra_drogueria["id"])

        respuesta = _get(_cliente_de_prueba(), seed_caso_resumen["orden_compra_id"], token)

        assert respuesta.status_code == 404
    finally:
        if usuario_id is not None:
            service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_compras_puede_leer_el_resumen_completo(
    seed_drogueria, seed_caso_resumen, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])

    respuesta = _get(_cliente_de_prueba(), seed_caso_resumen["orden_compra_id"], token)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["orden_compra_id"] == seed_caso_resumen["orden_compra_id"]
    assert cuerpo["cliente"]["razon_social"].startswith("Cliente oc_entregas test")
    assert [r["numero_renglon"] for r in cuerpo["renglones"]] == [1, 2, 3]
    assert [r["estado_vinculo"] for r in cuerpo["renglones"]] == [
        "confirmado",
        "confirmado",
        "sin_presupuesto",
    ]
    assert cuerpo["renglones"][0]["producto"]["codigo_interno"].startswith("OCE-TEST-")
    assert cuerpo["renglones"][1]["producto"] is None
    assert [e["numero_entrega"] for e in cuerpo["entregas"]] == [1, 2]
    assert cuerpo["entregas"][0]["items"][0]["oc_item_id"] == seed_caso_resumen["oc_item_con_pack"]["id"]
    # Decimal viaja como string en JSON (Pydantic v2).
    assert isinstance(cuerpo["renglones"][0]["cantidad"], str)
    assert cuerpo["exportacion"] is None
