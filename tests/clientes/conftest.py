import pytest

from services.presupuestacion.clientes.service import obtener_cliente


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
    service_client.table("condiciones_pago").delete().eq("drogueria_id", seed_drogueria["id"]).execute()


@pytest.fixture
def seed_cliente_factory(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_terceros_de_clientes
):
    """Sembra un cliente como lo deja la importación (docs/arquitectura/maestros-progress.md):
    una fila en `terceros` y su rol en `clientes`, con el mismo id. Devuelve la forma
    combinada tercero+rol (`ClienteOut`) leída con `obtener_cliente`.

    Depende de `seed_usuario_sistema` para que su teardown borre observaciones y
    formatos (que referencian al usuario) antes de que se borre el usuario."""
    creados = []

    def _seed(
        nombre: str = "Cliente de test",
        activo: bool = True,
        email: str | None = None,
        tipo: str = "otro",
    ):
        tercero = (
            service_client.table("terceros")
            .insert({"drogueria_id": seed_drogueria["id"], "razon_social": nombre, "email": email})
            .execute()
            .data[0]
        )
        service_client.table("clientes").insert(
            {"id": tercero["id"], "drogueria_id": seed_drogueria["id"], "tipo": tipo, "activo": activo}
        ).execute()
        creados.append(tercero["id"])
        return obtener_cliente(service_client, cliente_id=tercero["id"], drogueria_id=seed_drogueria["id"])

    yield _seed
    for cliente_id in creados:
        service_client.table("cliente_observaciones").delete().eq(
            "cliente_id", cliente_id
        ).execute()
        service_client.table("cliente_formato_documentos").delete().eq(
            "cliente_id", cliente_id
        ).execute()
