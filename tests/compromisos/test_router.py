"""tests/compromisos/test_router.py -- GET /compromisos-entregas (openspec/changes/
oc-export-progress, D9/D10). Ciclo HTTP completo con JWT real por rol. El router lee con el
client del usuario (la vista es security_invoker), así que estos tests ejercitan la RLS de
verdad: aislamiento por droguería y lectura de cada rol de _ROLES_LECTURA."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.compromisos.router import _ROLES_LECTURA, router
from services.shared.exceptions import register_exception_handlers
from tests.compromisos.conftest import dias


def _cliente_de_prueba() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    return TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _plan_vencida_futura_lejana():
    return [
        (1, dias(-3), [("oc_item_con_pack", "60"), ("oc_item_sin_pack", "10")]),
        (2, dias(10), [("oc_item_con_pack", "50")]),
        (3, dias(400), [("oc_item_con_pack", "1")]),
    ]


def _de_la_oc(cuerpo: list[dict], caso: dict) -> list[dict]:
    return [fila for fila in cuerpo if fila["orden_compra_id"] == caso["orden_compra_id"]]


@pytest.mark.integration
def test_solo_aparecen_ocs_exportadas(
    seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    usuario_id, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    client = _cliente_de_prueba()

    antes = client.get("/compromisos-entregas", headers=_auth(token))
    marcar_exportada(caso, usuario_id=usuario_id)
    despues = client.get("/compromisos-entregas", headers=_auth(token))

    assert antes.status_code == 200, antes.text
    assert _de_la_oc(antes.json(), caso) == []
    assert despues.status_code == 200, despues.text
    # entrega 1 (2 renglones) + entrega 2; la 3 queda fuera del rango por defecto (+6 meses)
    assert len(_de_la_oc(despues.json(), caso)) == 3


@pytest.mark.integration
def test_clasifica_vencida_y_futura_con_dias_de_atraso_y_orden(
    seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    usuario_id, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    marcar_exportada(caso, usuario_id=usuario_id)

    respuesta = _cliente_de_prueba().get("/compromisos-entregas", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    filas = _de_la_oc(respuesta.json(), caso)
    assert [(f["situacion"], f["numero_entrega"], f["numero_renglon"]) for f in filas] == [
        ("vencida", 1, 1),
        ("vencida", 1, 2),
        ("futura", 2, 1),
    ]
    assert filas[0]["dias_atraso"] == 3
    assert filas[2]["dias_atraso"] == 0
    assert filas[0]["fecha_entrega_planificada"] == dias(-3).isoformat()
    assert filas[0]["cliente"].startswith("Cliente oc_entregas test")


@pytest.mark.integration
def test_rango_explicito_incluye_futuras_lejanas_y_excluye_vencidas(
    seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    usuario_id, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    marcar_exportada(caso, usuario_id=usuario_id)

    respuesta = _cliente_de_prueba().get(
        "/compromisos-entregas",
        params={"desde": dias(300).isoformat(), "hasta": dias(500).isoformat()},
        headers=_auth(token),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert [f["numero_entrega"] for f in _de_la_oc(respuesta.json(), caso)] == [3]


@pytest.mark.integration
def test_aislamiento_por_drogueria(
    seed_drogueria,
    otra_drogueria,
    sembrar_oc_con_plan,
    marcar_exportada,
    crear_usuario_con_token,
):
    usuario_id, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    otro_usuario_id, otro_token = crear_usuario_con_token(
        rol="compras", drogueria_id=otra_drogueria["id"]
    )
    propia = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    ajena = sembrar_oc_con_plan(drogueria_id=otra_drogueria["id"], plan=_plan_vencida_futura_lejana())
    marcar_exportada(propia, usuario_id=usuario_id)
    marcar_exportada(ajena, usuario_id=otro_usuario_id)
    client = _cliente_de_prueba()

    mias = client.get("/compromisos-entregas", headers=_auth(token)).json()
    suyas = client.get("/compromisos-entregas", headers=_auth(otro_token)).json()

    assert len(_de_la_oc(mias, propia)) == 3
    assert _de_la_oc(mias, ajena) == []
    assert {f["drogueria_id"] for f in mias} == {seed_drogueria["id"]}
    assert len(_de_la_oc(suyas, ajena)) == 3
    assert _de_la_oc(suyas, propia) == []


@pytest.mark.integration
@pytest.mark.parametrize("rol", [rol for rol in _ROLES_LECTURA if rol != "superadmin"])
def test_cada_rol_de_lectura_ve_las_filas_de_su_drogueria(
    rol, seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    usuario_id, token = crear_usuario_con_token(rol=rol, drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    marcar_exportada(caso, usuario_id=usuario_id)

    respuesta = _cliente_de_prueba().get("/compromisos-entregas", headers=_auth(token))

    assert respuesta.status_code == 200, f"{rol}: {respuesta.text}"
    assert len(_de_la_oc(respuesta.json(), caso)) == 3, rol


@pytest.mark.integration
def test_rol_fuera_de_roles_lectura_es_rechazado_con_403(crear_usuario_con_token):
    _, token = crear_usuario_con_token(rol="sistema", drogueria_id=None)

    respuesta = _cliente_de_prueba().get("/compromisos-entregas", headers=_auth(token))

    assert respuesta.status_code == 403


@pytest.mark.integration
def test_rango_invalido_da_422(seed_drogueria, crear_usuario_con_token):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba()

    invertido = client.get(
        "/compromisos-entregas",
        params={"desde": dias(10).isoformat(), "hasta": dias(1).isoformat()},
        headers=_auth(token),
    )
    demasiado_largo = client.get(
        "/compromisos-entregas",
        params={"desde": dias(0).isoformat(), "hasta": dias(800).isoformat()},
        headers=_auth(token),
    )

    assert invertido.status_code == 422
    assert demasiado_largo.status_code == 422


@pytest.mark.integration
def test_entrega_real_de_compras_no_figura_como_compromiso(
    service_client, seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    """Requiere 0034 aplicada (sin ella la vista lista la entrega real y este test falla).
    Una entrega física registrada por compras.crear_entrega (estado parcial/pendiente,
    cantidad_planificada = 0, fecha_entrega_real) no es un compromiso a cumplir."""
    usuario_id, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    marcar_exportada(caso, usuario_id=usuario_id)
    entrega = (
        service_client.table("entregas_oc")
        .insert(
            {
                "orden_compra_id": caso["orden_compra_id"],
                "drogueria_id": seed_drogueria["id"],
                "numero_entrega": 4,
                "fecha_entrega_planificada": dias(5).isoformat(),
                "fecha_entrega_real": dias(0).isoformat(),
                "cantidad_items": 1,
                "estado": "parcial",
            }
        )
        .execute()
        .data[0]
    )
    service_client.table("entregas_oc_items").insert(
        {
            "entrega_oc_id": entrega["id"],
            "drogueria_id": seed_drogueria["id"],
            "oc_item_id": caso["oc_item_con_pack"]["id"],
            "cantidad_entregada": "5",
            "cantidad_rechazada": "1",
        }
    ).execute()

    respuesta = _cliente_de_prueba().get("/compromisos-entregas", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    assert 4 not in {f["numero_entrega"] for f in _de_la_oc(respuesta.json(), caso)}


@pytest.mark.integration
def test_cada_fila_trae_posicion_y_tamano_del_plan(
    seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    """Requiere 0035 aplicada."""
    usuario_id, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    marcar_exportada(caso, usuario_id=usuario_id)

    respuesta = _cliente_de_prueba().get("/compromisos-entregas", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    filas = _de_la_oc(respuesta.json(), caso)
    # la entrega 3 queda fuera del rango por defecto, pero cuenta en el plan
    assert [(f["numero_entrega"], f["posicion_en_plan"], f["entregas_en_plan"]) for f in filas] == [
        (1, 1, 3),
        (1, 1, 3),
        (2, 2, 3),
    ]


@pytest.mark.integration
def test_el_plan_ignora_entregas_reales_y_cuenta_las_cerradas(
    service_client, seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    """Requiere 0035 aplicada. Plan numerado 1, 3 y 4 con una entrega real de compras en el
    medio (numero_entrega 2, cantidad_planificada = 0): no cuenta ni corre la posición. La
    entrega 1, ya entregada, sale de la vista pero sigue siendo parte del plan."""
    usuario_id, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(
        drogueria_id=seed_drogueria["id"],
        plan=[
            (1, dias(-10), [("oc_item_con_pack", "10")]),
            (3, dias(5), [("oc_item_con_pack", "20")]),
            (4, dias(20), [("oc_item_sin_pack", "5")]),
        ],
    )
    real = (
        service_client.table("entregas_oc")
        .insert(
            {
                "orden_compra_id": caso["orden_compra_id"],
                "drogueria_id": seed_drogueria["id"],
                "numero_entrega": 2,
                "fecha_entrega_planificada": dias(7).isoformat(),
                "fecha_entrega_real": dias(0).isoformat(),
                "cantidad_items": 1,
                "estado": "parcial",
            }
        )
        .execute()
        .data[0]
    )
    service_client.table("entregas_oc_items").insert(
        {
            "entrega_oc_id": real["id"],
            "drogueria_id": seed_drogueria["id"],
            "oc_item_id": caso["oc_item_con_pack"]["id"],
            "cantidad_entregada": "5",
        }
    ).execute()
    service_client.table("entregas_oc").update({"estado": "entregada"}).eq(
        "id", caso["entregas"][1]["id"]
    ).execute()
    marcar_exportada(caso, usuario_id=usuario_id)

    respuesta = _cliente_de_prueba().get("/compromisos-entregas", headers=_auth(token))

    assert respuesta.status_code == 200, respuesta.text
    filas = _de_la_oc(respuesta.json(), caso)
    assert [(f["numero_entrega"], f["posicion_en_plan"], f["entregas_en_plan"]) for f in filas] == [
        (3, 2, 3),
        (4, 3, 3),
    ]


@pytest.mark.integration
def test_superadmin_sin_drogueria_da_422(crear_usuario_con_token):
    _, token = crear_usuario_con_token(rol="superadmin", drogueria_id=None)

    respuesta = _cliente_de_prueba().get("/compromisos-entregas", headers=_auth(token))

    assert respuesta.status_code == 422


_PROXIMA = "/compromisos-entregas/proxima-fecha"


@pytest.mark.integration
def test_proxima_fecha_es_la_primera_estrictamente_posterior(
    seed_drogueria, sembrar_oc_con_plan, marcar_exportada, crear_usuario_con_token
):
    usuario_id, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    caso = sembrar_oc_con_plan(drogueria_id=seed_drogueria["id"], plan=_plan_vencida_futura_lejana())
    marcar_exportada(caso, usuario_id=usuario_id)
    client = _cliente_de_prueba()

    def proxima(despues_de):
        respuesta = client.get(_PROXIMA, params={"despues_de": despues_de.isoformat()}, headers=_auth(token))
        assert respuesta.status_code == 200, respuesta.text
        return respuesta.json()

    # la base de TEST puede tener otras OC exportadas: se acota a fechas que solo siembra este caso
    assert proxima(dias(399)) == {"fecha": dias(400).isoformat()}
    assert proxima(dias(400)) != {"fecha": dias(400).isoformat()}
    assert proxima(dias(800)) == {"fecha": None}


@pytest.mark.integration
def test_proxima_fecha_no_ve_compromisos_de_otra_drogueria(
    seed_drogueria,
    otra_drogueria,
    sembrar_oc_con_plan,
    marcar_exportada,
    crear_usuario_con_token,
):
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])
    otro_usuario_id, otro_token = crear_usuario_con_token(rol="compras", drogueria_id=otra_drogueria["id"])
    ajena = sembrar_oc_con_plan(
        drogueria_id=otra_drogueria["id"], plan=[(1, dias(700), [("oc_item_con_pack", "1")])]
    )
    marcar_exportada(ajena, usuario_id=otro_usuario_id)
    client = _cliente_de_prueba()
    params = {"despues_de": dias(699).isoformat()}

    mia = client.get(_PROXIMA, params=params, headers=_auth(token))
    suya = client.get(_PROXIMA, params=params, headers=_auth(otro_token))

    assert mia.status_code == 200, mia.text
    assert mia.json() == {"fecha": None}
    assert suya.json() == {"fecha": dias(700).isoformat()}


@pytest.mark.integration
def test_proxima_fecha_valida_parametro_rol_y_drogueria(seed_drogueria, crear_usuario_con_token):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    _, token_sistema = crear_usuario_con_token(rol="sistema", drogueria_id=None)
    _, token_superadmin = crear_usuario_con_token(rol="superadmin", drogueria_id=None)
    client = _cliente_de_prueba()
    params = {"despues_de": dias(0).isoformat()}

    assert client.get(_PROXIMA, headers=_auth(token)).status_code == 422
    assert client.get(_PROXIMA, params={"despues_de": "31/10/2026"}, headers=_auth(token)).status_code == 422
    assert client.get(_PROXIMA, params=params, headers=_auth(token_sistema)).status_code == 403
    assert client.get(_PROXIMA, params=params, headers=_auth(token_superadmin)).status_code == 422
