import pytest


@pytest.fixture
def seed_comparativa_factory(service_client, seed_drogueria):
    creados = []

    def _seed(proceso_comercial_id: str, **overrides):
        fila = {
            "proceso_comercial_id": proceso_comercial_id,
            "drogueria_id": seed_drogueria["id"],
            **overrides,
        }
        comparativa = service_client.table("comparativas").insert(fila).execute().data[0]
        creados.append(comparativa)
        return comparativa

    yield _seed
    for comparativa in creados:
        service_client.table("notificaciones").delete().eq(
            "comparativa_id", comparativa["id"]
        ).execute()
        service_client.table("ofertas_items").delete().eq(
            "comparativa_id", comparativa["id"]
        ).execute()
        service_client.table("comparativas").delete().eq("id", comparativa["id"]).execute()


@pytest.fixture
def seed_oferta_item_factory(service_client, seed_drogueria, seed_proveedor):
    # Depende de seed_proveedor (aunque no lo use en el setup) para garantizar que
    # ofertas_items.proveedor_id se borre ANTES que el proveedor -- fk_oi_prov sin
    # CASCADE, mismo motivo que en matching/presupuestos/extraccion.
    creados = []

    def _seed(comparativa_id: str, **overrides):
        fila = {
            "comparativa_id": comparativa_id,
            "drogueria_id": seed_drogueria["id"],
            "proveedor": "Proveedor de test",
            "precio_unitario": "10.00",
            **overrides,
        }
        oferta = service_client.table("ofertas_items").insert(fila).execute().data[0]
        creados.append(oferta)
        return oferta

    yield _seed
    for oferta in creados:
        service_client.table("ofertas_items").delete().eq("id", oferta["id"]).execute()
