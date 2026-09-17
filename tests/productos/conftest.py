import pytest


@pytest.fixture
def limpiar_catalogo(service_client, seed_drogueria):
    """productos/categorias/marcas/envases/caracteristicas no tienen ON DELETE
    CASCADE desde droguerias — hay que limpiarlos a mano antes de que
    seed_drogueria borre la fila padre (mismo criterio que
    tests/imports/conftest.py). producto_caracteristicas se borra primero:
    tiene FK a productos sin ON DELETE CASCADE, asi que un producto con
    caracteristicas asignadas no se puede borrar hasta limpiar el puente."""
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("producto_caracteristicas").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("productos").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("categorias").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("marcas").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("envases").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("caracteristicas").delete().eq("drogueria_id", drog_id).execute()
