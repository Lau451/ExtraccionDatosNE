import pytest


@pytest.fixture
def seed_proceso_comercial_factory(service_client, seed_drogueria):
    creados = []

    def _seed(nombre: str = "Proceso de test", clase: str = "cotizacion", **overrides):
        fila = {
            "drogueria_id": seed_drogueria["id"],
            "nombre": nombre,
            "clase": clase,
            **overrides,
        }
        proceso = service_client.table("procesos_comerciales").insert(fila).execute().data[0]
        creados.append(proceso)
        return proceso

    yield _seed
    for proceso in creados:
        service_client.table("historial_cambios").delete().eq(
            "proceso_comercial_id", proceso["id"]
        ).execute()
        service_client.table("procesos_comerciales").delete().eq("id", proceso["id"]).execute()
