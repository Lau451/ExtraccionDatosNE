import pytest


@pytest.fixture
def seed_proceso_cotizacion(service_client, seed_drogueria):
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "clase": "cotizacion",
        "nombre": "Proceso cotización de test",
    }
    proceso = service_client.table("procesos_comerciales").insert(fila).execute().data[0]
    yield proceso
    service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()


@pytest.fixture
def seed_proceso_licitacion(service_client, seed_drogueria):
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "clase": "licitacion",
        "nombre": "Proceso licitación de test",
    }
    proceso = service_client.table("procesos_comerciales").insert(fila).execute().data[0]
    yield proceso
    service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()


@pytest.fixture
def seed_presupuesto_factory(service_client, seed_drogueria, seed_usuario_sistema):
    # Depende de seed_usuario_sistema (aunque no lo use en el setup) para garantizar que
    # presupuestos/presupuesto_items (aprobado_por, presentado_por, precio_ajustado_por)
    # se borren ANTES que el usuario -- mismo motivo que la dependencia a producto en
    # seed_item_proceso_factory.
    creados = []

    def _seed(proceso_id: str, **overrides):
        fila = {
            "proceso_comercial_id": proceso_id,
            "drogueria_id": seed_drogueria["id"],
            "estado": "generado",
            "monto_total": "0",
            "cantidad_items": 0,
            "items_sin_precio": 0,
            **overrides,
        }
        presupuesto = service_client.table("presupuestos").insert(fila).execute().data[0]
        creados.append(presupuesto)
        return presupuesto

    yield _seed
    for presupuesto in creados:
        service_client.table("historial_cambios").delete().eq(
            "presupuesto_id", presupuesto["id"]
        ).execute()
        service_client.table("presupuesto_items").delete().eq(
            "presupuesto_id", presupuesto["id"]
        ).execute()
        service_client.table("presupuestos").delete().eq("id", presupuesto["id"]).execute()


@pytest.fixture
def seed_item_proceso_factory(service_client, seed_drogueria, seed_producto, seed_producto_factory):
    # Depende explícitamente de los fixtures de producto (aunque no los use en el setup)
    # para garantizar que items_proceso.producto_id se borre ANTES que productos en el
    # teardown -- FK fk_ip_prod. El orden de teardown de pytest sigue el grafo de
    # dependencias, no el orden de aparición en la firma del test.
    creados = []
    contador = {"n": 0}

    def _seed(proceso_id: str, producto_id: str | None = None, **overrides):
        contador["n"] += 1
        fila = {
            "proceso_comercial_id": proceso_id,
            "drogueria_id": seed_drogueria["id"],
            "numero_renglon": contador["n"],
            "descripcion": f"Renglón de test {contador['n']}",
            "cantidad": "10",
            "producto_id": producto_id,
            **overrides,
        }
        item = service_client.table("items_proceso").insert(fila).execute().data[0]
        creados.append(item)
        return item

    yield _seed
    for item in creados:
        service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def seed_presupuesto_item_factory(service_client, seed_drogueria, seed_producto, seed_producto_factory):
    # Misma razón que en seed_item_proceso_factory: presupuesto_items.producto_id (fk_pi_prod)
    # también referencia productos sin CASCADE.
    creados = []

    def _seed(presupuesto_id: str, item_proceso_id: str, **overrides):
        fila = {
            "presupuesto_id": presupuesto_id,
            "drogueria_id": seed_drogueria["id"],
            "item_proceso_id": item_proceso_id,
            **overrides,
        }
        presupuesto_item = service_client.table("presupuesto_items").insert(fila).execute().data[0]
        creados.append(presupuesto_item)
        return presupuesto_item

    yield _seed
    for presupuesto_item in creados:
        service_client.table("presupuesto_items").delete().eq("id", presupuesto_item["id"]).execute()
