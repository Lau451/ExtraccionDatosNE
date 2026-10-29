"""tests/oc_export/test_router.py -- POST /ordenes-compra/{id}/exportar-progress
(openspec/changes/oc-export-progress, D6/D7/D10). Ciclo HTTP completo con JWT real por
rol; el CSV se escribe en `tmp_path` sobreescribiendo `get_settings`."""

import csv
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.presupuestacion.oc_entregas.router import router as oc_entregas_router
from services.presupuestacion.oc_export.router import router as oc_export_router
from services.shared.config import get_settings
from services.shared.exceptions import register_exception_handlers


def _cliente_de_prueba(tmp_path) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(oc_export_router)
    app.include_router(oc_entregas_router)
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        progress_docs_dir=str(tmp_path), oc_export_encoding="cp1252"
    )
    return TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_comercial_exporta_y_queda_marcada(
    service_client, seed_drogueria, caso_exportable, crear_usuario_con_token, tmp_path
):
    usuario_id, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    orden_id = caso_exportable["orden_compra_id"]

    respuesta = _cliente_de_prueba(tmp_path).post(
        f"/ordenes-compra/{orden_id}/exportar-progress", headers=_auth(token)
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["filas"] == 3
    assert cuerpo["exportado_por"] == usuario_id
    archivo = tmp_path / "oc" / cuerpo["archivo"]
    assert archivo.name.startswith(f"OC_{caso_exportable['codigo_cliente']}_")
    with open(archivo, encoding="cp1252", newline="") as f:
        filas = list(csv.reader(f, delimiter=";"))
    assert len(filas) == 4  # encabezado + 3 filas renglón x entrega
    assert {fila[7] for fila in filas[1:]} == {"1", "2"}  # el renglón 3 (descartado) no sale
    assert filas[1][4] == caso_exportable["codigo_cliente"]

    oc = (
        service_client.table("ordenes_compra")
        .select("estado, exportado_at, exportado_por, archivo_exportado")
        .eq("id", orden_id)
        .execute()
        .data[0]
    )
    assert oc["exportado_at"] is not None
    assert oc["exportado_por"] == usuario_id
    assert oc["archivo_exportado"] == cuerpo["archivo"]
    assert oc["estado"] == "pendiente"  # C1: exportar no cambia el estado


@pytest.mark.integration
def test_compras_no_puede_exportar_403(
    seed_drogueria, caso_exportable, crear_usuario_con_token, tmp_path
):
    _, token = crear_usuario_con_token(rol="compras", drogueria_id=seed_drogueria["id"])

    respuesta = _cliente_de_prueba(tmp_path).post(
        f"/ordenes-compra/{caso_exportable['orden_compra_id']}/exportar-progress",
        headers=_auth(token),
    )

    assert respuesta.status_code == 403
    assert not (tmp_path / "oc").exists()


@pytest.mark.integration
def test_segunda_exportacion_da_409_y_no_deja_otro_archivo(
    seed_drogueria, caso_exportable, crear_usuario_con_token, tmp_path
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba(tmp_path)
    url = f"/ordenes-compra/{caso_exportable['orden_compra_id']}/exportar-progress"

    assert client.post(url, headers=_auth(token)).status_code == 200
    segunda = client.post(url, headers=_auth(token))

    assert segunda.status_code == 409
    assert len(list((tmp_path / "oc").iterdir())) == 1


@pytest.mark.integration
def test_put_planificacion_despues_de_exportar_da_409_y_get_muestra_exportacion(
    seed_drogueria, caso_exportable, crear_usuario_con_token, tmp_path
):
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])
    client = _cliente_de_prueba(tmp_path)
    orden_id = caso_exportable["orden_compra_id"]
    assert client.post(f"/ordenes-compra/{orden_id}/exportar-progress", headers=_auth(token)).status_code == 200

    put = client.put(
        f"/ordenes-compra/{orden_id}/entregas/planificacion",
        json={
            "entregas": [
                {
                    "numero_entrega": 1,
                    "items": [
                        {"oc_item_id": caso_exportable["oc_item_con_pack"]["id"], "cantidad": "110"},
                        {"oc_item_id": caso_exportable["oc_item_sin_pack"]["id"], "cantidad": "10"},
                    ],
                }
            ]
        },
        headers=_auth(token),
    )
    assert put.status_code == 409

    get = client.get(f"/ordenes-compra/{orden_id}/entregas/planificacion", headers=_auth(token))
    assert get.status_code == 200
    cuerpo = get.json()
    assert cuerpo["puede_planificar"] is False
    assert cuerpo["exportacion"]["archivo_exportado"].endswith(".csv")


@pytest.mark.integration
def test_oc_con_precondiciones_incumplidas_da_422_sin_archivo(
    service_client, seed_drogueria, caso_exportable, crear_usuario_con_token, tmp_path
):
    service_client.table("terceros_legacy_map").delete().eq(
        "tercero_id", caso_exportable["tercero_id"]
    ).execute()
    _, token = crear_usuario_con_token(rol="comercial", drogueria_id=seed_drogueria["id"])

    respuesta = _cliente_de_prueba(tmp_path).post(
        f"/ordenes-compra/{caso_exportable['orden_compra_id']}/exportar-progress",
        headers=_auth(token),
    )

    assert respuesta.status_code == 422
    assert "código de cliente" in respuesta.json()["detail"]
    assert not (tmp_path / "oc").exists()
