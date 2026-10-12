import secrets
import uuid

import pytest

from services.shared.config import get_settings
from tests.oc_entregas.fixtures import caso_planificacion


@pytest.fixture
def crear_usuario_con_token(service_client):
    """Copia local de tests/oc_entregas/conftest.py::crear_usuario_con_token
    -- conftest.py de un árbol hermano no es visible acá. Un JWT real para
    ejercitar `Depends(require_roles(...))` en un ciclo HTTP completo."""
    from supabase import create_client

    creados: list[str] = []

    def _crear(*, rol: str, drogueria_id: str | None) -> tuple[str, str]:
        settings = get_settings()
        email = f"oc-resumen-router-test-{uuid.uuid4()}@seed.local"
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
def seed_caso_resumen(service_client, seed_drogueria):
    """Reusa el caso de oc_entregas (2 renglones confirmados + 1 descartado, con
    cliente) y le agrega un plan de 2 entregas. `limpiar` borra `entregas_oc`
    (y por cascada sus items) antes que las OC."""
    caso = caso_planificacion.sembrar(service_client, drogueria_id=seed_drogueria["id"])
    try:
        for numero, cantidad in ((1, "60"), (2, "50")):
            entrega = (
                service_client.table("entregas_oc")
                .insert(
                    {
                        "orden_compra_id": caso["orden_compra_id"],
                        "drogueria_id": seed_drogueria["id"],
                        "numero_entrega": numero,
                        "fecha_entrega_planificada": f"2026-12-0{numero}",
                    }
                )
                .execute()
                .data[0]
            )
            service_client.table("entregas_oc_items").insert(
                {
                    "entrega_oc_id": entrega["id"],
                    "oc_item_id": caso["oc_item_con_pack"]["id"],
                    "drogueria_id": seed_drogueria["id"],
                    "cantidad_planificada": cantidad,
                    "cantidad_entregada": "0",
                }
            ).execute()
        yield caso
    finally:
        caso_planificacion.limpiar(service_client, caso)
