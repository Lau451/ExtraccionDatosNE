import pytest


@pytest.fixture
def limpiar_automatizaciones(service_client, seed_drogueria):
    """acciones_ejecutadas debe borrarse ANTES que reglas_automatizacion (FK regla_id
    sin CASCADE) y antes que eventos (FK evento_id sin CASCADE) -- por eso depende
    de seed_drogueria para forzar el orden de teardown vía el grafo de dependencias."""
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("acciones_ejecutadas").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("reglas_automatizacion").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("notificacion_entregas").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("notificaciones").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("eventos").delete().eq("drogueria_id", drog_id).execute()
