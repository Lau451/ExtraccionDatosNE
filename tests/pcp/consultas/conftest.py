import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/pcp/negociacion/conftest.py::crear_usuario_con_token
    -- mismo motivo que el resto de las copias locales en tests/pcp/*/conftest.py
    (conftest.py de un árbol hermano no es visible acá)."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"pcp-consultas-router-test-{uuid.uuid4()}@seed.local"
        password = secrets.token_urlsafe(24)
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        creados.append(usuario_id)
        service_client.table("usuarios").insert(
            {"id": usuario_id, "drogueria_id": drogueria_id, "rol": rol, "nombre": "Router test"}
        ).execute()

        cliente_temporal = create_client(settings.supabase_url, settings.supabase_anon_key)
        sesion = cliente_temporal.auth.sign_in_with_password({"email": email, "password": password})
        return usuario_id, sesion.session.access_token

    yield _crear
    for usuario_id in creados:
        service_client.auth.admin.delete_user(usuario_id)


@pytest.fixture
def seed_item_proceso(service_client, seed_proceso_comercial, seed_producto, seed_drogueria):
    """Copia local de tests/pcp/renglones/conftest.py::seed_item_proceso --
    mismo motivo (árbol hermano no visible). `producto_id` seteado: el test
    de PDF (9.6) necesita un renglón con producto ya matcheado para poder
    aparecer identificado por nombre en el documento."""
    fila = {
        "proceso_comercial_id": seed_proceso_comercial["id"],
        "drogueria_id": seed_drogueria["id"],
        "numero_renglon": 1,
        "descripcion": "Renglón de test",
        "cantidad": "10",
        "producto_id": seed_producto["id"],
    }
    item = service_client.table("items_proceso").insert(fila).execute().data[0]
    yield item
    service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def seed_item_proceso_factory(service_client, seed_proceso_comercial, seed_producto, seed_drogueria):
    """Copia local de tests/pcp/negociacion/conftest.py::seed_item_proceso_factory
    -- mismo motivo (árbol hermano no visible). 9.3/9.4 necesitan varios
    renglones (uno o más por PCP, en uno o varios PCPs distintos)."""
    creados: list[dict] = []

    def _seed(*, numero_renglon: int, producto_id: str | None = None):
        fila = {
            "proceso_comercial_id": seed_proceso_comercial["id"],
            "drogueria_id": seed_drogueria["id"],
            "numero_renglon": numero_renglon,
            "descripcion": f"Renglón de test {numero_renglon}",
            "cantidad": "10",
            "producto_id": producto_id if producto_id is not None else seed_producto["id"],
        }
        item = service_client.table("items_proceso").insert(fila).execute().data[0]
        creados.append(item)
        return item

    yield _seed
    for item in creados:
        service_client.table("items_proceso").delete().eq("id", item["id"]).execute()


@pytest.fixture
def seed_proveedores_pcp_factory(service_client, seed_drogueria, limpiar_pcp_terceros):
    """Copia local de tests/pcp/negociacion/conftest.py::seed_proveedores_pcp_factory
    -- mismo motivo (árbol hermano no visible). `limpiar_pcp_terceros`
    (tests/pcp/conftest.py) ya limpia todos los `terceros` de la droguería de
    test al finalizar, cascadeando a `proveedores` (fk_prov_tercero)."""

    def _seed(cantidad: int) -> list[dict]:
        proveedores = []
        for i in range(cantidad):
            tercero = (
                service_client.table("terceros")
                .insert(
                    {"drogueria_id": seed_drogueria["id"], "razon_social": f"Proveedor Consultas Test {i}"}
                )
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
            proveedores.append(proveedor)
        return proveedores

    return _seed
