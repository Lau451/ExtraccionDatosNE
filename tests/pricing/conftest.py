from datetime import date

import pytest


@pytest.fixture
def seed_item_proceso(service_client, seed_proceso_comercial, seed_producto, seed_drogueria):
    fila = {
        "proceso_comercial_id": seed_proceso_comercial["id"],
        "drogueria_id": seed_drogueria["id"],
        "numero_renglon": 1,
        "descripcion": "Renglón de test",
        "cantidad": "10",
        "producto_id": seed_producto["id"],
    }
    item = service_client.table("items_proceso").insert(fila).execute().data[0]
    yield item
    service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def seed_costo_estandar(service_client, seed_producto, seed_drogueria):
    fila = {
        "producto_id": seed_producto["id"],
        "drogueria_id": seed_drogueria["id"],
        "costo_unitario": "100.00",
        "fecha_desde": date.today().isoformat(),
    }
    costo = service_client.table("costos_productos").insert(fila).execute().data[0]
    yield costo
    service_client.table("costos_productos").delete().eq("id", costo["id"]).execute()


@pytest.fixture
def seed_regla_pricing(service_client, seed_drogueria):
    fila = {
        "drogueria_id": seed_drogueria["id"],
        "nombre": "Regla de test",
        "margen_minimo_pct": "20",
        "margen_objetivo_pct": "30",
        "meses_ventana_mercado": 6,
        "prioridad": 0,
    }
    regla = service_client.table("reglas_pricing").insert(fila).execute().data[0]
    yield regla
    service_client.table("reglas_pricing").delete().eq("id", regla["id"]).execute()


@pytest.fixture
def limpiar_presupuestos(service_client):
    ids: list[str] = []
    yield ids
    for presupuesto_id in ids:
        service_client.table("historial_cambios").delete().eq("presupuesto_id", presupuesto_id).execute()
        service_client.table("presupuesto_items").delete().eq("presupuesto_id", presupuesto_id).execute()
        service_client.table("presupuestos").delete().eq("id", presupuesto_id).execute()
