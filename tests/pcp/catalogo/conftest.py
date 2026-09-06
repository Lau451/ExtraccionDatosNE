import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/pcp/renglones/conftest.py::crear_usuario_con_token
    -- mismo motivo (conftest.py de un árbol hermano no es visible acá,
    pytest solo descubre conftest.py en directorios ancestros del test).
    Necesaria para el test de router: un JWT real para ejercitar
    `Depends(require_roles(...))` a través de un ciclo HTTP completo."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"pcp-catalogo-router-test-{uuid.uuid4()}@seed.local"
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
def seed_proveedores_pcp_factory(service_client, seed_drogueria, limpiar_pcp_terceros):
    """Copia local de tests/pcp/renglones/conftest.py::seed_proveedores_pcp_factory
    -- mismo motivo que crear_usuario_con_token arriba (árbol hermano no
    visible). `limpiar_pcp_terceros` (tests/pcp/conftest.py) ya limpia todos
    los `terceros` de la droguería de test al finalizar, cascadeando a
    `proveedores` (fk_prov_tercero)."""

    def _seed(cantidad: int) -> list[dict]:
        proveedores = []
        for i in range(cantidad):
            tercero = (
                service_client.table("terceros")
                .insert(
                    {"drogueria_id": seed_drogueria["id"], "razon_social": f"Proveedor Catálogo Test {i}"}
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
