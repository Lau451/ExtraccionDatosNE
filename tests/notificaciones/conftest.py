import pytest


@pytest.fixture
def limpiar_notificaciones(service_client, seed_drogueria):
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("notificacion_entregas").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("notificaciones").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("notificacion_preferencias").delete().eq("drogueria_id", drog_id).execute()
