import secrets
import uuid

import pytest

from services.shared.config import get_settings
from tests.oc_entregas.fixtures import caso_planificacion


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/oc_presupuesto/conftest.py::crear_usuario_con_token
    -- conftest.py de un árbol hermano no es visible acá (pytest solo
    descubre conftest.py en directorios ancestros del test). Un JWT real para
    ejercitar `Depends(require_roles(...))` a través de un ciclo HTTP
    completo, no invocando el endpoint directamente en Python."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"oc-entregas-router-test-{uuid.uuid4()}@seed.local"
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
def seed_caso_planificacion(service_client, seed_drogueria):
    """Siembra el caso de integración (2 renglones confirmados + 1
    descartado, sin pendientes) y lo limpia en el `finally` del teardown,
    corra o no el test sin error."""
    caso = caso_planificacion.sembrar(service_client, drogueria_id=seed_drogueria["id"])
    try:
        yield caso
    finally:
        caso_planificacion.limpiar(service_client, caso)
