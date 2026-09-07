import uuid

import pytest


@pytest.fixture
def seed_cliente(service_client, seed_drogueria):
    # razon_social vive en terceros desde 0008_terceros_modelo.sql -- clientes
    # quedó como tabla de rol angosta (sobreviven id/drogueria_id/tipo/activo)
    # que comparte id con terceros (fk_cli_tercero). Insertar "nombre" directo
    # acá rompía con PGRST204 ("Could not find the 'nombre' column of
    # 'clientes'"); mismo bug preexistente que tests/conftest.py::seed_proveedor,
    # mismo fix de alta en dos pasos.
    tercero = (
        service_client.table("terceros")
        .insert({"drogueria_id": seed_drogueria["id"], "razon_social": "Hospital de test"})
        .execute()
        .data[0]
    )
    cliente = (
        service_client.table("clientes")
        .insert({"id": tercero["id"], "drogueria_id": seed_drogueria["id"], "tipo": "hospital"})
        .execute()
        .data[0]
    )
    yield cliente
    service_client.table("clientes").delete().eq("id", cliente["id"]).execute()
    service_client.table("terceros").delete().eq("id", tercero["id"]).execute()


@pytest.fixture
def seed_proceso_con_cliente(service_client, seed_drogueria, seed_cliente):
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "cliente_id": seed_cliente["id"],
        "clase": "cotizacion",
        "nombre": "Proceso de test con cliente",
    }
    proceso = service_client.table("procesos_comerciales").insert(fila).execute().data[0]
    yield proceso
    service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()


@pytest.fixture
def seed_item_sin_producto(service_client, seed_proceso_con_cliente, seed_drogueria):
    fila = {
        "proceso_comercial_id": seed_proceso_con_cliente["id"],
        "drogueria_id": seed_drogueria["id"],
        "numero_renglon": 1,
        "descripcion": "Ibuprofeno 600mg x30",
        "cantidad": "10",
    }
    item = service_client.table("items_proceso").insert(fila).execute().data[0]
    yield item
    service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def seed_alias(service_client, seed_cliente, seed_drogueria, seed_producto):
    fila = {
        "cliente_id": seed_cliente["id"],
        "drogueria_id": seed_drogueria["id"],
        "producto_id": seed_producto["id"],
        "descripcion_original": "Ibuprofeno 600mg x30",
        "descripcion_normalizada": "IBUPROFENO 600MG X30",
    }
    alias = service_client.table("cliente_producto_alias").insert(fila).execute().data[0]
    yield alias
    service_client.table("cliente_producto_alias").delete().eq("id", alias["id"]).execute()


@pytest.fixture
def seed_producto_con_nombre(service_client, seed_drogueria):
    def _crear(nombre: str):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "codigo_interno": f"TEST-{uuid.uuid4().hex[:8]}",
            "nombre": nombre,
        }
        return service_client.table("productos").insert(fila).execute().data[0]

    creados = []

    def _seed(nombre: str):
        producto = _crear(nombre)
        creados.append(producto)
        return producto

    yield _seed
    for producto in creados:
        service_client.table("productos").delete().eq("id", producto["id"]).execute()


@pytest.fixture
def limpiar_matching(service_client):
    item_ids: list[str] = []
    alias_ids: list[str] = []
    yield {"items": item_ids, "alias": alias_ids}
    for item_id in item_ids:
        service_client.table("matching_candidatos").delete().eq("item_proceso_id", item_id).execute()
        service_client.table("items_proceso").update(
            {"alias_id": None, "producto_id": None}
        ).eq("id", item_id).execute()
    for alias_id in alias_ids:
        service_client.table("cliente_producto_alias").delete().eq("id", alias_id).execute()
