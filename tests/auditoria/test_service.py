import pytest

from services.presupuestacion.auditoria.models import _COLUMNA_FK_POR_ENTIDAD
from services.presupuestacion.core.audit import registrar_cambios


def _listar(client, *, entidad, entidad_id):
    columna = _COLUMNA_FK_POR_ENTIDAD[entidad]
    return (
        client.table("historial_cambios")
        .select("*")
        .eq(columna, entidad_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


@pytest.mark.integration
def test_listar_historial_agrupa_por_batch_id(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema
):
    batch_id = registrar_cambios(
        service_client,
        entidad="proceso_comercial",
        entidad_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        cambios={"estado": ("abierto", "cerrado"), "nombre": ("Original", "Editado")},
        origen="usuario",
        usuario_id=seed_usuario_sistema["id"],
    )

    historial = _listar(
        service_client, entidad="proceso_comercial", entidad_id=seed_proceso_comercial["id"]
    )

    assert len(historial) == 2
    assert all(fila["batch_id"] == batch_id for fila in historial)
    campos = {fila["campo"] for fila in historial}
    assert campos == {"estado", "nombre"}

    service_client.table("historial_cambios").delete().eq("batch_id", batch_id).execute()


@pytest.mark.integration
def test_listar_historial_no_mezcla_otra_entidad(
    service_client, seed_drogueria, seed_proceso_comercial, seed_usuario_sistema
):
    batch_id = registrar_cambios(
        service_client,
        entidad="proceso_comercial",
        entidad_id=seed_proceso_comercial["id"],
        drogueria_id=seed_drogueria["id"],
        cambios={"estado": ("abierto", "cerrado")},
        origen="usuario",
        usuario_id=seed_usuario_sistema["id"],
    )

    historial = _listar(service_client, entidad="evento", entidad_id=seed_proceso_comercial["id"])
    assert historial == []

    service_client.table("historial_cambios").delete().eq("batch_id", batch_id).execute()
