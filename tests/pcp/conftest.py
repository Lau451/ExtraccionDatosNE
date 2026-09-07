import pytest


@pytest.fixture
def limpiar_pcp_terceros(service_client, seed_drogueria):
    """proveedores es una tabla de rol cuyo id comparte identidad con terceros
    (0008_terceros_modelo.sql, fk_prov_tercero ON DELETE CASCADE) -- borrar
    terceros alcanza para limpiar la fila de proveedores asociada. Mismo
    criterio que tests/terceros/conftest.py::limpiar_terceros."""
    yield
    service_client.table("terceros").delete().eq("drogueria_id", seed_drogueria["id"]).execute()


@pytest.fixture
def seed_proveedor_pcp(service_client, seed_drogueria, limpiar_pcp_terceros):
    """Reemplazo local de tests/conftest.py::seed_proveedor (raíz) para los
    tests de tests/pcp/. Ese fixture compartido inserta razon_social
    directamente en `proveedores` -- columna que 0008_terceros_modelo.sql
    movió a `terceros`, por lo que está roto (PGRST204 "Could not find the
    'razon_social' column of 'proveedores'") para cualquier consumidor desde
    esa migración. Bug preexistente, no introducido por gestor-pcp; reportado
    en tasks.md/el resumen de esta PR en vez de corregirse en tests/conftest.py
    (afecta módulos fuera del alcance de esta fase). proveedores.id comparte
    identidad con terceros.id (fk_prov_tercero), así que el alta va en dos
    pasos: primero terceros, después proveedores con el mismo id."""
    tercero = (
        service_client.table("terceros")
        .insert({"drogueria_id": seed_drogueria["id"], "razon_social": "Proveedor PCP Test"})
        .execute()
        .data[0]
    )
    proveedor = (
        service_client.table("proveedores")
        .insert(
            {
                "id": tercero["id"],
                "drogueria_id": seed_drogueria["id"],
                "es_proveedor_compra": True,
            }
        )
        .execute()
        .data[0]
    )
    return proveedor
