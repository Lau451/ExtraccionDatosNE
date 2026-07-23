import pytest


@pytest.fixture
def limpiar_drogueria_creada(service_client):
    creadas = []
    yield creadas
    for drogueria_id in creadas:
        service_client.table("droguerias").delete().eq("id", drogueria_id).execute()
