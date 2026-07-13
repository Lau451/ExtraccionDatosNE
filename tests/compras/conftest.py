import secrets

import pytest


@pytest.fixture
def limpiar_ordenes_compra(service_client):
    ids: list[str] = []
    yield ids
    for orden_compra_id in ids:
        entregas = (
            service_client.table("entregas_oc")
            .select("id")
            .eq("orden_compra_id", orden_compra_id)
            .execute()
            .data
        )
        for entrega in entregas:
            service_client.table("entregas_oc_items").delete().eq(
                "entrega_oc_id", entrega["id"]
            ).execute()
        for entrega in entregas:
            service_client.table("entregas_oc").delete().eq("id", entrega["id"]).execute()

        service_client.table("historial_cambios").delete().eq(
            "orden_compra_id", orden_compra_id
        ).execute()
        service_client.table("oc_items").delete().eq(
            "orden_compra_id", orden_compra_id
        ).execute()
        service_client.table("ordenes_compra").delete().eq("id", orden_compra_id).execute()


@pytest.fixture
def numero_oc_unico():
    def _generar() -> str:
        return f"OC-TEST-{secrets.token_hex(6)}"

    return _generar
