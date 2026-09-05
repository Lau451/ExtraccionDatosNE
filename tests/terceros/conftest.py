import uuid

import pytest


@pytest.fixture
def limpiar_terceros(service_client, seed_drogueria):
    """terceros/clientes/proveedores/catalogos no tienen ON DELETE CASCADE desde
    droguerias -- hay que limpiarlos a mano antes de que seed_drogueria borre la
    fila padre (mismo criterio que tests/catalogo/conftest.py). Borrar
    `terceros` primero alcanza para limpiar clientes/proveedores/direcciones/
    contactos/legacy_map: todos cascadean desde terceros (fk_*_tercero ON
    DELETE CASCADE, 0008_terceros_modelo.sql). Los catálogos no dependen de
    terceros, así que se limpian después, sin ese problema de orden."""
    yield
    drog_id = seed_drogueria["id"]
    service_client.table("terceros").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("condiciones_pago").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("formas_pago").delete().eq("drogueria_id", drog_id).execute()
    service_client.table("sectores_contacto").delete().eq("drogueria_id", drog_id).execute()


@pytest.fixture
def seed_tercero_factory(service_client, seed_drogueria, limpiar_terceros):
    def _seed(razon_social: str = "Tercero de test", **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "razon_social": razon_social,
            **overrides,
        }
        return service_client.table("terceros").insert(fila).execute().data[0]

    return _seed


@pytest.fixture
def seed_condicion_pago_factory(service_client, seed_drogueria, limpiar_terceros):
    def _seed(nombre: str | None = None, **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "nombre": nombre or f"Condición {uuid.uuid4().hex[:8]}",
            **overrides,
        }
        return service_client.table("condiciones_pago").insert(fila).execute().data[0]

    return _seed


@pytest.fixture
def seed_forma_pago_factory(service_client, seed_drogueria, limpiar_terceros):
    def _seed(nombre: str | None = None, **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "nombre": nombre or f"Forma {uuid.uuid4().hex[:8]}",
            **overrides,
        }
        return service_client.table("formas_pago").insert(fila).execute().data[0]

    return _seed


@pytest.fixture
def seed_sector_contacto_factory(service_client, seed_drogueria, limpiar_terceros):
    def _seed(nombre: str | None = None, **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "nombre": nombre or f"Sector {uuid.uuid4().hex[:8]}",
            **overrides,
        }
        return service_client.table("sectores_contacto").insert(fila).execute().data[0]

    return _seed


@pytest.fixture
def seed_direccion_factory(service_client, seed_drogueria, seed_tercero_factory):
    def _seed(tercero_id: str | None = None, **overrides):
        if tercero_id is None:
            tercero_id = seed_tercero_factory()["id"]
        fila = {
            "tercero_id": tercero_id,
            "drogueria_id": seed_drogueria["id"],
            "calle": "Calle Falsa 123",
            **overrides,
        }
        return service_client.table("tercero_direcciones").insert(fila).execute().data[0]

    return _seed


@pytest.fixture
def seed_contacto_factory(service_client, seed_drogueria, seed_tercero_factory):
    def _seed(tercero_id: str | None = None, **overrides):
        if tercero_id is None:
            tercero_id = seed_tercero_factory()["id"]
        fila = {
            "tercero_id": tercero_id,
            "drogueria_id": seed_drogueria["id"],
            "nombre": f"Contacto {uuid.uuid4().hex[:8]}",
            **overrides,
        }
        return service_client.table("terceros_contactos").insert(fila).execute().data[0]

    return _seed
