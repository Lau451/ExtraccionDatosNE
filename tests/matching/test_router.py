"""HTTP tests for the matching screen endpoints (presupuestador-v1 T3a):
GET /procesos-comerciales/{id}/matching and GET /matching/procesos.

Full HTTP cycle (TestClient + real JWT via crear_usuario_con_token), so
`Depends(require_roles(...))` and the user client's RLS are exercised."""

import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.matching.router import router
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def proceso_con_renglones(
    service_client, seed_drogueria, seed_proceso_con_cliente, seed_producto_con_nombre
):
    """Rengl\u00f3n 1 confirmed to a producto, rengl\u00f3n 2 sugerido with two
    candidatos, rengl\u00f3n 3 pendiente with none."""
    confirmado = seed_producto_con_nombre("Amoxicilina 500mg x16")
    mejor = seed_producto_con_nombre("Ibuprofeno 600mg x30")
    peor = seed_producto_con_nombre("Ibuprofeno 400mg x20")
    filas = [
        {
            "proceso_comercial_id": seed_proceso_con_cliente["id"],
            "drogueria_id": seed_drogueria["id"],
            "numero_renglon": numero,
            "descripcion": descripcion,
            "cantidad": "10.00",
            "estado_matching": estado,
            "producto_id": producto_id,
            "confianza_matching": confianza,
        }
        # Inserted out of order: the endpoint orders by numero_renglon.
        for numero, descripcion, estado, producto_id, confianza in (
            (2, "Ibuprofeno 600 mg comp x 30", "sugerido", None, "92.00"),
            (1, "Amoxicilina 500", "confirmado", confirmado["id"], None),
            (3, "Gasa est\u00e9ril 10x10", "pendiente", None, None),
        )
    ]
    items = service_client.table("items_proceso").insert(filas).execute().data
    por_renglon = {item["numero_renglon"]: item for item in items}
    service_client.table("matching_candidatos").insert(
        [
            {
                "item_proceso_id": por_renglon[2]["id"],
                "drogueria_id": seed_drogueria["id"],
                "producto_id": producto["id"],
                "confianza": confianza,
                "metodo": "fuzzy",
            }
            for producto, confianza in ((peor, "71.00"), (mejor, "92.00"))
        ]
    ).execute()
    yield {
        "proceso": seed_proceso_con_cliente,
        "items": por_renglon,
        "productos": {"confirmado": confirmado, "mejor": mejor, "peor": peor},
    }
    # Removing the items cascades to their candidatos; the proceso fixture then
    # deletes the proceso.
    service_client.table("items_proceso").delete().in_(
        "id", [item["id"] for item in items]
    ).execute()


@pytest.mark.integration
def test_matching_de_proceso_lista_renglones_con_producto_y_candidatos(
    seed_drogueria, proceso_con_renglones, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    proceso = proceso_con_renglones["proceso"]
    items = proceso_con_renglones["items"]
    productos = proceso_con_renglones["productos"]

    respuesta = _cliente_de_prueba().get(
        f"/procesos-comerciales/{proceso['id']}/matching",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["proceso_comercial_id"] == proceso["id"]
    assert cuerpo["nombre"] == "Proceso de test con cliente"
    assert cuerpo["clase"] == "cotizacion"
    assert cuerpo["cliente"] == "Hospital de test"

    def _producto(clave: str) -> dict:
        producto = productos[clave]
        return {
            "id": producto["id"],
            "nombre": producto["nombre"],
            "codigo_interno": producto["codigo_interno"],
        }

    assert cuerpo["renglones"] == [
        {
            "item_proceso_id": items[1]["id"],
            "numero_renglon": 1,
            "descripcion": "Amoxicilina 500",
            "cantidad": "10.00",
            "estado_matching": "confirmado",
            "confianza_matching": None,
            "producto": _producto("confirmado"),
            "candidatos": [],
        },
        {
            "item_proceso_id": items[2]["id"],
            "numero_renglon": 2,
            "descripcion": "Ibuprofeno 600 mg comp x 30",
            "cantidad": "10.00",
            "estado_matching": "sugerido",
            "confianza_matching": "92.00",
            "producto": None,
            # Best candidato first.
            "candidatos": [
                {"producto": _producto("mejor"), "confianza": "92.00", "metodo": "fuzzy", "elegido": False},
                {"producto": _producto("peor"), "confianza": "71.00", "metodo": "fuzzy", "elegido": False},
            ],
        },
        {
            "item_proceso_id": items[3]["id"],
            "numero_renglon": 3,
            "descripcion": "Gasa est\u00e9ril 10x10",
            "cantidad": "10.00",
            "estado_matching": "pendiente",
            "confianza_matching": None,
            "producto": None,
            "candidatos": [],
        },
    ]


@pytest.mark.integration
def test_matching_de_proceso_rechaza_un_rol_fuera_de_matching(
    seed_drogueria, seed_proceso_con_cliente, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])

    respuesta = _cliente_de_prueba().get(
        f"/procesos-comerciales/{seed_proceso_con_cliente['id']}/matching",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert respuesta.status_code == 403


@pytest.mark.integration
def test_matching_de_proceso_de_otra_drogueria_da_404(
    service_client, seed_proceso_con_cliente, crear_usuario_con_token
):
    otra_drogueria = (
        service_client.table("droguerias")
        .insert(
            {
                "nombre": "Otra Droguer\u00eda (matching router test)",
                "razon_social": "Otra Droguer\u00eda SA",
                "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
                "ciudad": "Rosario",
                "provincia": "Santa Fe",
                "contacto_email": "otra-matching@seed.local",
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

        respuesta = _cliente_de_prueba().get(
            f"/procesos-comerciales/{seed_proceso_con_cliente['id']}/matching",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert respuesta.status_code == 404
        assert respuesta.json()["detail"] == "No se encontr\u00f3 el proceso comercial"
    finally:
        service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_matching_de_proceso_con_id_invalido_da_422(seed_drogueria, crear_usuario_con_token):
    # A non-UUID id used to reach PostgREST and come back as a 500.
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])

    respuesta = _cliente_de_prueba().get(
        "/procesos-comerciales/abc/matching", headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 422


@pytest.mark.integration
def test_matching_procesos_lista_los_procesos_con_renglones_sin_resolver(
    seed_drogueria, proceso_con_renglones, crear_usuario_con_token
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    proceso = proceso_con_renglones["proceso"]

    respuesta = _cliente_de_prueba().get(
        "/matching/procesos", headers={"Authorization": f"Bearer {token}"}
    )

    assert respuesta.status_code == 200
    del_proceso = [p for p in respuesta.json() if p["proceso_comercial_id"] == proceso["id"]]
    assert del_proceso == [
        {
            "proceso_comercial_id": proceso["id"],
            "proceso": "Proceso de test con cliente",
            "clase": "cotizacion",
            "cliente": "Hospital de test",
            "pendientes": 1,
            "sugeridos": 1,
        }
    ]
