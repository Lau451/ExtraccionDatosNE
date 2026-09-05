import pytest


@pytest.fixture
def limpiar_catalogo(service_client, seed_drogueria):
    """productos/proveedores/categorias no tienen ON DELETE CASCADE desde
    droguerias — hay que limpiarlos a mano antes de que seed_drogueria borre la
    fila padre (mismo criterio que tests/imports/conftest.py). Fase 8: un
    "proveedor" creado vía catalogo/service.py::crear_proveedor (wrapper de
    compatibilidad sobre services.terceros.api) es ahora un `tercero` + rol
    `proveedores` -- borrar `terceros` alcanza, `fk_prov_tercero` cascadea
    (0008_terceros_modelo.sql)."""
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("productos").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("terceros").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("categorias").delete().eq("drogueria_id", drog_id).execute()
