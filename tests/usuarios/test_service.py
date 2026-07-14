import secrets
import uuid

import pytest

from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from services.presupuestacion.usuarios.models import UsuarioCreate
from services.presupuestacion.usuarios.service import cambiar_rol, crear_usuario


def _perfil(usuario: dict) -> UsuarioPerfil:
    return UsuarioPerfil(id=usuario["id"], drogueria_id=usuario["drogueria_id"], rol=usuario["rol"])


def _body(**overrides) -> UsuarioCreate:
    base = {
        "email": f"nuevo-{uuid.uuid4()}@seed.local",
        "password": "clave-segura-123",
        "nombre": "Usuario Nuevo",
        "rol": "comercial",
    }
    base.update(overrides)
    return UsuarioCreate(**base)


# ---------------------------------------------------------------------------
# crear_usuario
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_admin_crea_usuario_fuerza_su_propia_drogueria(
    service_client, seed_admin, seed_drogueria, limpiar_usuario_creado
):
    otra_drogueria_id = "00000000-0000-0000-0000-000000000000"
    resultado = crear_usuario(
        service_client,
        creador=_perfil(seed_admin),
        body=_body(rol="comercial", drogueria_id=otra_drogueria_id),
    )
    limpiar_usuario_creado.append(resultado["id"])

    assert resultado["drogueria_id"] == seed_drogueria["id"]
    assert resultado["drogueria_id"] != otra_drogueria_id


@pytest.mark.integration
def test_admin_no_puede_crear_superadmin(service_client, seed_admin):
    with pytest.raises(ForbiddenError):
        crear_usuario(service_client, creador=_perfil(seed_admin), body=_body(rol="superadmin"))


@pytest.mark.integration
def test_superadmin_crea_usuario_con_drogueria_explicita(
    service_client, seed_superadmin, seed_drogueria, limpiar_usuario_creado
):
    resultado = crear_usuario(
        service_client,
        creador=_perfil(seed_superadmin),
        body=_body(rol="gerencia", drogueria_id=seed_drogueria["id"]),
    )
    limpiar_usuario_creado.append(resultado["id"])

    assert resultado["drogueria_id"] == seed_drogueria["id"]
    assert resultado["rol"] == "gerencia"


@pytest.mark.integration
def test_superadmin_crea_otro_superadmin_sin_drogueria(
    service_client, seed_superadmin, limpiar_usuario_creado
):
    resultado = crear_usuario(
        service_client, creador=_perfil(seed_superadmin), body=_body(rol="superadmin")
    )
    limpiar_usuario_creado.append(resultado["id"])

    assert resultado["drogueria_id"] is None
    assert resultado["rol"] == "superadmin"


@pytest.mark.integration
def test_superadmin_crea_usuario_no_superadmin_sin_drogueria_lanza_validation_error(
    service_client, seed_superadmin
):
    with pytest.raises(ValidationError):
        crear_usuario(
            service_client,
            creador=_perfil(seed_superadmin),
            body=_body(rol="comercial", drogueria_id=None),
        )


@pytest.mark.integration
def test_rol_no_autorizado_no_puede_crear_usuario(service_client, seed_drogueria):
    creador = UsuarioPerfil(id="x", drogueria_id=seed_drogueria["id"], rol="comercial")
    with pytest.raises(ForbiddenError):
        crear_usuario(service_client, creador=creador, body=_body())


# ---------------------------------------------------------------------------
# cambiar_rol
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_admin_cambia_rol_de_usuario_de_su_drogueria(
    service_client, seed_admin, seed_drogueria, limpiar_usuario_creado
):
    creado = crear_usuario(
        service_client, creador=_perfil(seed_admin), body=_body(rol="comercial")
    )
    limpiar_usuario_creado.append(creado["id"])

    resultado = cambiar_rol(
        service_client, creador=_perfil(seed_admin), usuario_id=creado["id"], nuevo_rol="lider_comercial"
    )
    assert resultado["rol"] == "lider_comercial"


@pytest.mark.integration
def test_admin_no_puede_cambiar_rol_de_usuario_de_otra_drogueria(
    service_client, seed_admin, seed_superadmin, seed_drogueria, limpiar_usuario_creado
):
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra", "razon_social": "Otra SA",
            "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
            "ciudad": "Rosario", "provincia": "Santa Fe",
            "contacto_email": f"otra-usuarios-{uuid.uuid4()}@seed.local", "contacto_telefono": "0",
        }
    ).execute().data[0]
    try:
        de_otra = crear_usuario(
            service_client,
            creador=_perfil(seed_superadmin),
            body=_body(rol="comercial", drogueria_id=otra_drogueria["id"]),
        )
        limpiar_usuario_creado.append(de_otra["id"])

        with pytest.raises(ForbiddenError):
            cambiar_rol(
                service_client, creador=_perfil(seed_admin), usuario_id=de_otra["id"], nuevo_rol="compras"
            )
    finally:
        # borrar el usuario ANTES que la droguería (FK), sin esperar al teardown
        # diferido de limpiar_usuario_creado que corre después de este finally.
        service_client.table("usuarios").delete().eq("id", de_otra["id"]).execute()
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_cambiar_rol_no_permite_hacia_superadmin(
    service_client, seed_admin, limpiar_usuario_creado
):
    creado = crear_usuario(
        service_client, creador=_perfil(seed_admin), body=_body(rol="comercial")
    )
    limpiar_usuario_creado.append(creado["id"])

    with pytest.raises(ForbiddenError):
        cambiar_rol(
            service_client, creador=_perfil(seed_admin), usuario_id=creado["id"], nuevo_rol="superadmin"
        )


@pytest.mark.integration
def test_cambiar_rol_no_permite_desde_superadmin(
    service_client, seed_superadmin, seed_drogueria
):
    creador = UsuarioPerfil(id=seed_superadmin["id"], drogueria_id=None, rol="superadmin")
    with pytest.raises(ForbiddenError):
        cambiar_rol(
            service_client, creador=creador, usuario_id=seed_superadmin["id"], nuevo_rol="admin"
        )


@pytest.mark.integration
def test_cambiar_rol_usuario_inexistente_lanza_not_found(service_client, seed_admin):
    with pytest.raises(NotFoundError):
        cambiar_rol(
            service_client,
            creador=_perfil(seed_admin),
            usuario_id="00000000-0000-0000-0000-000000000000",
            nuevo_rol="compras",
        )
