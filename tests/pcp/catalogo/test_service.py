"""6.2-6.4 (openspec/changes/gestor-pcp/tasks.md Fase 6) -- pcp-catalogo-proveedores:
listado de proveedores asociados a un producto, alta ad-hoc, rechazo de
duplicados y aislamiento por tenant (spec `pcp-catalogo-proveedores`).

RED hasta que 6.5 cree services/pcp/catalogo/service.py.
"""

from postgrest.exceptions import APIError
import pytest

from services.pcp.catalogo.models import ProductoProveedorCreate
from services.pcp.catalogo.service import agregar_proveedor, listar_proveedores_producto
from services.shared.exceptions import ConflictError

# ---------------------------------------------------------------------------
# 6.2 -- listar proveedores asociados a un producto; catálogo vacío -> []
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_proveedores_producto_devuelve_ambos_proveedores_asociados(
    service_client, seed_drogueria, seed_usuario_sistema, seed_producto, seed_proveedores_pcp_factory
):
    proveedores = seed_proveedores_pcp_factory(2)
    creadas: list[str] = []
    try:
        for proveedor in proveedores:
            asociacion = agregar_proveedor(
                service_client,
                drogueria_id=seed_drogueria["id"],
                producto_id=seed_producto["id"],
                body=ProductoProveedorCreate(proveedor_id=proveedor["id"]),
                usuario_id=seed_usuario_sistema["id"],
            )
            creadas.append(asociacion["id"])

        resultado = listar_proveedores_producto(
            service_client, producto_id=seed_producto["id"], drogueria_id=seed_drogueria["id"]
        )

        assert len(resultado) == 2
        assert {fila["proveedor_id"] for fila in resultado} == {p["id"] for p in proveedores}
    finally:
        for asociacion_id in creadas:
            service_client.table("producto_proveedores").delete().eq("id", asociacion_id).execute()


@pytest.mark.integration
def test_listar_proveedores_producto_sin_asociaciones_devuelve_lista_vacia(
    service_client, seed_drogueria, seed_producto
):
    resultado = listar_proveedores_producto(
        service_client, producto_id=seed_producto["id"], drogueria_id=seed_drogueria["id"]
    )

    assert resultado == []


# ---------------------------------------------------------------------------
# 6.3 -- alta ad-hoc desde la vista del renglón; duplicado -> ConflictError
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_agregar_proveedor_lo_hace_inmediatamente_seleccionable(
    service_client, seed_drogueria, seed_usuario_sistema, seed_producto, seed_proveedor_pcp
):
    asociacion = agregar_proveedor(
        service_client,
        drogueria_id=seed_drogueria["id"],
        producto_id=seed_producto["id"],
        body=ProductoProveedorCreate(proveedor_id=seed_proveedor_pcp["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        assert asociacion["producto_id"] == seed_producto["id"]
        assert asociacion["proveedor_id"] == seed_proveedor_pcp["id"]
        assert asociacion["activo"] is True

        resultado = listar_proveedores_producto(
            service_client, producto_id=seed_producto["id"], drogueria_id=seed_drogueria["id"]
        )
        assert any(fila["proveedor_id"] == seed_proveedor_pcp["id"] for fila in resultado)
    finally:
        service_client.table("producto_proveedores").delete().eq("id", asociacion["id"]).execute()


@pytest.mark.integration
def test_agregar_proveedor_duplicado_lanza_conflict_error(
    service_client, seed_drogueria, seed_usuario_sistema, seed_producto, seed_proveedor_pcp
):
    asociacion = agregar_proveedor(
        service_client,
        drogueria_id=seed_drogueria["id"],
        producto_id=seed_producto["id"],
        body=ProductoProveedorCreate(proveedor_id=seed_proveedor_pcp["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        with pytest.raises(ConflictError):
            agregar_proveedor(
                service_client,
                drogueria_id=seed_drogueria["id"],
                producto_id=seed_producto["id"],
                body=ProductoProveedorCreate(proveedor_id=seed_proveedor_pcp["id"]),
                usuario_id=seed_usuario_sistema["id"],
            )

        en_bd = (
            service_client.table("producto_proveedores")
            .select("id")
            .eq("producto_id", seed_producto["id"])
            .eq("proveedor_id", seed_proveedor_pcp["id"])
            .execute()
            .data
        )
        assert len(en_bd) == 1
    finally:
        service_client.table("producto_proveedores").delete().eq("id", asociacion["id"]).execute()


# ---------------------------------------------------------------------------
# 6.4 -- una asociación de otra droguería nunca se devuelve
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_listar_proveedores_producto_no_devuelve_asociacion_de_otra_drogueria(
    service_client, seed_drogueria, seed_usuario_sistema, seed_producto, seed_proveedor_pcp
):
    asociacion = agregar_proveedor(
        service_client,
        drogueria_id=seed_drogueria["id"],
        producto_id=seed_producto["id"],
        body=ProductoProveedorCreate(proveedor_id=seed_proveedor_pcp["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    try:
        otra_drogueria_id = "00000000-0000-0000-0000-000000000000"

        resultado = listar_proveedores_producto(
            service_client, producto_id=seed_producto["id"], drogueria_id=otra_drogueria_id
        )

        assert resultado == []
    finally:
        service_client.table("producto_proveedores").delete().eq("id", asociacion["id"]).execute()


def test_agregar_proveedor_con_proveedor_id_invalido_no_pasa_el_check_de_postgres():
    """Triangulación de 6.3: el modelo exige `proveedor_id` (no acepta un
    valor vacío/ausente) antes de siquiera llegar a la capa de servicio."""
    with pytest.raises(Exception):
        ProductoProveedorCreate()
