import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/pcp/catalogo/conftest.py::crear_usuario_con_token
    -- mismo motivo (conftest.py de un árbol hermano no es visible acá,
    pytest solo descubre conftest.py en directorios ancestros del test).
    Necesaria para el test de router: un JWT real para ejercitar
    `Depends(require_roles(...))` a través de un ciclo HTTP completo."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"pcp-imports-router-test-{uuid.uuid4()}@seed.local"
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
def seed_cliente_pcp_factory(service_client, seed_drogueria, limpiar_pcp_terceros):
    """Crea un `tercero` con `codigo_interno` conocido + su fila de rol
    `clientes` (D8: `_resolver_cliente_id` busca por
    `terceros.codigo_interno`, luego confirma la fila de rol). `terceros.id`
    == `clientes.id` (fk_cli_tercero) -- alta en dos pasos, mismo criterio
    que `tests/pcp/conftest.py::seed_proveedor_pcp`. `limpiar_pcp_terceros`
    (tests/pcp/conftest.py) ya borra todos los `terceros` de la droguería de
    test al finalizar, cascadeando a `clientes` (ON DELETE CASCADE)."""

    def _seed(*, codigo_interno: str, razon_social: str = "Cliente Import Legado Test") -> dict:
        tercero = (
            service_client.table("terceros")
            .insert(
                {
                    "drogueria_id": seed_drogueria["id"],
                    "codigo_interno": codigo_interno,
                    "razon_social": razon_social,
                }
            )
            .execute()
            .data[0]
        )
        cliente = (
            service_client.table("clientes")
            .insert({"id": tercero["id"], "drogueria_id": seed_drogueria["id"], "tipo": "otro"})
            .execute()
            .data[0]
        )
        return cliente

    return _seed
