"""tests/oc_entregas/test_router.py -- tabla de autorización de
GET/PUT /ordenes-compra/{orden_compra_id}/entregas/planificacion (T3): rol
fuera de _ROLES_ENTREGAS -> 403; OC de otra droguería -> 404; ciclo feliz de
planificación -> 200 con advertencias; gate -> 409; validación -> 422.

Ciclo HTTP completo (TestClient + JWT real vía crear_usuario_con_token) --
mismo criterio que tests/oc_presupuesto/test_router.py: este router corre
enteramente con SERVICE client (ver oc_entregas/repository.py), así que un JWT
real solo ejercita `Depends(require_roles(...))`, no RLS."""

import secrets
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.oc_entregas.router import router
from services.shared.exceptions import register_exception_handlers
from tests.oc_entregas.fixtures import caso_planificacion


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.integration
def test_rol_fuera_de_roles_entregas_es_rechazado_con_403(
    service_client, seed_drogueria, crear_usuario_con_token
):
    # "compras" entrega físicamente (compras/router.py::_ROLES_ENTREGA) pero
    # no planifica -- no está en _ROLES_ENTREGAS.
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.get(
        "/ordenes-compra/00000000-0000-0000-0000-000000000000/entregas/planificacion",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403


@pytest.mark.integration
def test_oc_de_otra_drogueria_da_404(
    service_client, seed_drogueria, seed_caso_planificacion, crear_usuario_con_token
):
    otra_drogueria = (
        service_client.table("droguerias")
        .insert(
            {
                "nombre": "Otra Droguería (oc_entregas router test)",
                "razon_social": "Otra Droguería SA",
                "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
                "ciudad": "Rosario",
                "provincia": "Santa Fe",
                "contacto_email": "otra-oc-entregas@seed.local",
                "contacto_telefono": "0000000000",
            }
        )
        .execute()
        .data[0]
    )
    try:
        usuario_id, token = crear_usuario_con_token(rol="comercial", drogueria_id=otra_drogueria["id"])
        client = _cliente_de_prueba()

        respuesta = client.get(
            f"/ordenes-compra/{seed_caso_planificacion['orden_compra_id']}/entregas/planificacion",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 404
    finally:
        service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_get_planificacion_devuelve_renglones_confirmados_y_plan_sugerido(
    service_client, seed_drogueria, seed_caso_planificacion, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.get(
        f"/ordenes-compra/{seed_caso_planificacion['orden_compra_id']}/entregas/planificacion",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["puede_planificar"] is True
    assert cuerpo["descartados"] == 1
    assert cuerpo["pendientes"] == 0
    assert cuerpo["cantidad_entregas_sugerida"] == 3
    ids_confirmados = {r["oc_item_id"] for r in cuerpo["renglones"]}
    assert ids_confirmados == {
        seed_caso_planificacion["oc_item_con_pack"]["id"],
        seed_caso_planificacion["oc_item_sin_pack"]["id"],
    }
    renglon_con_pack = next(
        r for r in cuerpo["renglones"] if r["oc_item_id"] == seed_caso_planificacion["oc_item_con_pack"]["id"]
    )
    assert renglon_con_pack["unidades_por_presentacion"] == 25
    sugerido_con_pack = next(
        s
        for s in cuerpo["plan_sugerido"]
        if s["oc_item_id"] == seed_caso_planificacion["oc_item_con_pack"]["id"]
    )
    # Comparación por valor, no por string exacto: `cantidad` viaja NUMERIC
    # desde Postgres vía PostgREST (a veces como float, p.ej. 110.0), así que
    # un resultado matemáticamente igual puede serializarse "35.0" en vez de
    # "35" -- Decimal('35.0') == Decimal('35') de todas formas.
    assert [Decimal(c) for c in sugerido_con_pack["cantidades"]] == [
        Decimal("50"),
        Decimal("25"),
        Decimal("35"),
    ]


@pytest.mark.integration
def test_get_planificacion_con_renglon_pendiente_bloquea_el_gate(
    service_client, seed_drogueria, seed_caso_planificacion, crear_usuario_con_token
):
    caso_planificacion.agregar_renglon_pendiente(service_client, caso=seed_caso_planificacion)
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.get(
        f"/ordenes-compra/{seed_caso_planificacion['orden_compra_id']}/entregas/planificacion",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["puede_planificar"] is False
    assert cuerpo["pendientes"] == 1


@pytest.mark.integration
def test_put_planificacion_con_renglon_pendiente_da_409(
    service_client, seed_drogueria, seed_caso_planificacion, crear_usuario_con_token
):
    caso_planificacion.agregar_renglon_pendiente(service_client, caso=seed_caso_planificacion)
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.put(
        f"/ordenes-compra/{seed_caso_planificacion['orden_compra_id']}/entregas/planificacion",
        json={
            "entregas": [
                {
                    "numero_entrega": 1,
                    "items": [
                        {"oc_item_id": seed_caso_planificacion["oc_item_con_pack"]["id"], "cantidad": "110"},
                        {"oc_item_id": seed_caso_planificacion["oc_item_sin_pack"]["id"], "cantidad": "10"},
                    ],
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 409


@pytest.mark.integration
def test_put_planificacion_con_suma_incorrecta_da_422(
    service_client, seed_drogueria, seed_caso_planificacion, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    respuesta = client.put(
        f"/ordenes-compra/{seed_caso_planificacion['orden_compra_id']}/entregas/planificacion",
        json={
            "entregas": [
                {
                    "numero_entrega": 1,
                    "items": [
                        {"oc_item_id": seed_caso_planificacion["oc_item_con_pack"]["id"], "cantidad": "40"},
                        {"oc_item_id": seed_caso_planificacion["oc_item_sin_pack"]["id"], "cantidad": "10"},
                    ],
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 422


@pytest.mark.integration
def test_put_planificacion_ok_crea_plan_con_advertencia_y_replanifica_sin_error(
    service_client, seed_drogueria, seed_caso_planificacion, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()
    oc_item_con_pack = seed_caso_planificacion["oc_item_con_pack"]["id"]
    oc_item_sin_pack = seed_caso_planificacion["oc_item_sin_pack"]["id"]

    body = {
        "entregas": [
            {
                "numero_entrega": 1,
                "items": [
                    {"oc_item_id": oc_item_con_pack, "cantidad": "60"},  # no múltiplo de 25 -> advertencia
                    {"oc_item_id": oc_item_sin_pack, "cantidad": "10"},
                ],
            },
            {
                "numero_entrega": 2,
                "items": [{"oc_item_id": oc_item_con_pack, "cantidad": "50"}],
            },
        ]
    }

    respuesta = client.put(
        f"/ordenes-compra/{seed_caso_planificacion['orden_compra_id']}/entregas/planificacion",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo["entregas"]) == 2
    assert len(cuerpo["advertencias"]) == 1
    assert cuerpo["advertencias"][0]["oc_item_id"] == oc_item_con_pack
    assert cuerpo["advertencias"][0]["cantidad_sugerida"] == "50"

    oc_actualizada = (
        service_client.table("ordenes_compra")
        .select("cantidad_entregas")
        .eq("id", seed_caso_planificacion["orden_compra_id"])
        .limit(1)
        .execute()
        .data[0]
    )
    assert oc_actualizada["cantidad_entregas"] == 2

    # Replanificar (D4: el plan sigue 'pendiente') reemplaza sin error, sin
    # duplicar filas -- 2da vez con 3 entregas.
    body_v2 = {
        "entregas": [
            {"numero_entrega": 1, "items": [{"oc_item_id": oc_item_con_pack, "cantidad": "50"}]},
            {"numero_entrega": 2, "items": [{"oc_item_id": oc_item_con_pack, "cantidad": "60"}]},
            {
                "numero_entrega": 3,
                "items": [
                    {"oc_item_id": oc_item_sin_pack, "cantidad": "10"},
                ],
            },
        ]
    }
    respuesta_v2 = client.put(
        f"/ordenes-compra/{seed_caso_planificacion['orden_compra_id']}/entregas/planificacion",
        json=body_v2,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert respuesta_v2.status_code == 200
    assert len(respuesta_v2.json()["entregas"]) == 3

    filas_entregas = (
        service_client.table("entregas_oc")
        .select("id")
        .eq("orden_compra_id", seed_caso_planificacion["orden_compra_id"])
        .execute()
        .data
    )
    assert len(filas_entregas) == 3  # el plan viejo (2 entregas) se borró, no quedó mezclado
