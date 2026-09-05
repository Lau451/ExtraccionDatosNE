import pytest

from services.presupuestacion.clientes.models import ClienteCreate, ClienteUpdate
from services.presupuestacion.clientes.service import actualizar_cliente, crear_cliente


@pytest.fixture
def limpiar_terceros_de_clientes(service_client, seed_drogueria):
    """Fase 8 (design.md D5): un "cliente" ya es un `tercero` + rol
    `clientes`, no una fila propia. Borrar `terceros` alcanza: `fk_cli_tercero`
    y `fk_tc_tercero` (terceros_contactos) cascadean desde ahí
    (0008_terceros_modelo.sql). No se reusa el fixture homónimo de
    tests/terceros/conftest.py porque los conftest.py de directorios
    hermanos no comparten fixtures en pytest."""
    yield
    service_client.table("terceros").delete().eq("drogueria_id", seed_drogueria["id"]).execute()


@pytest.fixture
def seed_cliente_factory(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_terceros_de_clientes
):
    """Sembra un cliente reusando el propio `crear_cliente` de producción
    (crea `terceros` + rol `clientes` vía services.terceros.api) en vez de
    insertar directamente en la tabla `clientes`, que ya no tiene columnas
    de identidad (nombre/dirección/...) desde la migración 0008. Devuelve
    la forma combinada tercero+rol (`ClienteOut`)."""
    creados = []

    def _seed(nombre: str = "Cliente de test", activo: bool = True, **overrides):
        cliente = crear_cliente(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=ClienteCreate(nombre=nombre, **overrides),
            usuario_id=seed_usuario_sistema["id"],
        )
        if not activo:
            cliente = actualizar_cliente(
                service_client,
                cliente_id=cliente["id"],
                drogueria_id=seed_drogueria["id"],
                body=ClienteUpdate(activo=False),
                usuario_id=seed_usuario_sistema["id"],
            )
        creados.append(cliente["id"])
        return cliente

    yield _seed
    for cliente_id in creados:
        service_client.table("cliente_observaciones").delete().eq(
            "cliente_id", cliente_id
        ).execute()
        service_client.table("cliente_formato_documentos").delete().eq(
            "cliente_id", cliente_id
        ).execute()
