import pytest


@pytest.fixture
def seed_cliente_factory(service_client, seed_drogueria, seed_usuario_sistema):
    # Depende de seed_usuario_sistema (aunque no lo use en el setup) para garantizar
    # que cliente_formato_documentos.actualizado_por / cliente_observaciones.creado_por
    # se borren ANTES que el usuario -- mismo motivo que en el resto de los módulos.
    creados = []

    def _seed(nombre: str = "Cliente de test", **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "nombre": nombre,
            "tipo": "hospital",
            **overrides,
        }
        cliente = service_client.table("clientes").insert(fila).execute().data[0]
        creados.append(cliente)
        return cliente

    yield _seed
    for cliente in creados:
        service_client.table("cliente_observaciones").delete().eq(
            "cliente_id", cliente["id"]
        ).execute()
        service_client.table("cliente_formato_documentos").delete().eq(
            "cliente_id", cliente["id"]
        ).execute()
        service_client.table("clientes").delete().eq("id", cliente["id"]).execute()
