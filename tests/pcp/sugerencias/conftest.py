import secrets
import uuid

import pytest

from services.shared.config import get_settings


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/pcp/catalogo/conftest.py::crear_usuario_con_token
    -- mismo motivo que el resto de las copias locales en tests/pcp/*/conftest.py
    (conftest.py de un árbol hermano no es visible acá). Necesaria para el
    test de router: un JWT real para ejercitar `Depends(require_roles(...))`
    a través de un ciclo HTTP completo."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"pcp-sugerencias-router-test-{uuid.uuid4()}@seed.local"
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
def seed_item_proceso_factory(service_client, seed_proceso_comercial, seed_producto, seed_drogueria):
    """Copia local de tests/pcp/negociacion/conftest.py::seed_item_proceso_factory
    -- mismo motivo (árbol hermano no visible). A diferencia de las copias
    hermanas, acepta un `cantidad` explícito: 10.2 necesita dos renglones
    sobre el mismo producto con cantidades distintas para que la suma
    agregada de la sugerencia (10 + 15 = 25) no sea un caso degenerado
    (2 * la misma cantidad)."""
    creados: list[dict] = []

    def _seed(*, numero_renglon: int, producto_id: str | None = None, cantidad: str = "10"):
        fila = {
            "proceso_comercial_id": seed_proceso_comercial["id"],
            "drogueria_id": seed_drogueria["id"],
            "numero_renglon": numero_renglon,
            "descripcion": f"Renglón de test {numero_renglon}",
            "cantidad": cantidad,
            "producto_id": producto_id if producto_id is not None else seed_producto["id"],
        }
        item = service_client.table("items_proceso").insert(fila).execute().data[0]
        creados.append(item)
        return item

    yield _seed
    for item in creados:
        service_client.table("items_proceso").delete().eq("id", item["id"]).execute()
