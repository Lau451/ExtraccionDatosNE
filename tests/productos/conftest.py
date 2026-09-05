import pytest


@pytest.fixture
def limpiar_catalogo(service_client, seed_drogueria):
    """productos/categorias no tienen ON DELETE CASCADE desde droguerias — hay
    que limpiarlos a mano antes de que seed_drogueria borre la fila padre
    (mismo criterio que tests/imports/conftest.py)."""
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("productos").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("categorias").delete().eq("drogueria_id", drog_id).execute()
