import secrets
import uuid

import pytest

from services.presupuestacion.core.auth import UserClaims, get_current_user
from services.presupuestacion.core.exceptions import AuthenticationError


@pytest.fixture
def _seed_usuario(service_client, seed_drogueria):
    creados = []

    def _seed(*, activo: bool) -> str:
        email = f"activo-test-{uuid.uuid4()}@seed.local"
        auth_response = service_client.auth.admin.create_user(
            {"email": email, "password": secrets.token_urlsafe(24), "email_confirm": True}
        )
        usuario_id = auth_response.user.id
        service_client.table("usuarios").insert(
            {
                "id": usuario_id,
                "drogueria_id": seed_drogueria["id"],
                "rol": "comercial",
                "nombre": "Usuario de test",
                "activo": activo,
            }
        ).execute()
        creados.append(usuario_id)
        return usuario_id

    yield _seed
    for usuario_id in creados:
        service_client.table("usuarios").delete().eq("id", usuario_id).execute()
        service_client.auth.admin.delete_user(usuario_id)


@pytest.mark.integration
def test_get_current_user_rechaza_usuario_desactivado(service_client, _seed_usuario):
    usuario_id = _seed_usuario(activo=False)
    claims = UserClaims(sub=usuario_id, exp=0)
    with pytest.raises(AuthenticationError):
        get_current_user(claims=claims, client=service_client)


@pytest.mark.integration
def test_get_current_user_acepta_usuario_activo(service_client, _seed_usuario):
    usuario_id = _seed_usuario(activo=True)
    claims = UserClaims(sub=usuario_id, exp=0)
    perfil = get_current_user(claims=claims, client=service_client)
    assert perfil.activo is True
    assert perfil.id == usuario_id
