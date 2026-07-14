import pytest


@pytest.fixture
def limpiar_eventos(service_client, seed_drogueria):
    """eventos/eventos_recurrentes no cascadean desde droguerias — limpiar a mano
    antes de que seed_drogueria borre la fila padre."""
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("eventos").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("eventos_recurrentes").delete().eq("drogueria_id", drog_id).execute()
