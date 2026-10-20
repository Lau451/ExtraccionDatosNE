"""tests/usuarios/test_paridad_permisos.py -- el blanqueo de contraseña tiene la
misma autorización que activar/desactivar (odd/tasks/login-usuario-alta-admin.md
S4, S10c). Para cada combinación de rol del creador y objetivo de la matriz,
blanquear_password y cambiar_activo lanzan el mismo tipo de excepción (o ninguna).
Unitario: el repositorio se reemplaza por un almacén en memoria."""

import pytest

from services.presupuestacion.core.auth import UsuarioPerfil
from services.presupuestacion.usuarios import repository as repo
from services.presupuestacion.usuarios import service

DROGUERIA = "d-propia"
OTRA_DROGUERIA = "d-otra"

ROLES_CREADOR = ("superadmin", "admin", "gerencia", "lider_comercial", "comercial", "compras")

# objetivo -> (rol, droguería); "yo" es el propio creador, "no-existe" no está en el almacén.
OBJETIVOS = {
    "yo": None,
    "superadmin": ("superadmin", None),
    "sistema": ("sistema", DROGUERIA),
    "admin-propio": ("admin", DROGUERIA),
    "gerencia-propio": ("gerencia", DROGUERIA),
    "lider-propio": ("lider_comercial", DROGUERIA),
    "comercial-propio": ("comercial", DROGUERIA),
    "compras-propio": ("compras", DROGUERIA),
    "admin-otra": ("admin", OTRA_DROGUERIA),
    "comercial-otra": ("comercial", OTRA_DROGUERIA),
    "no-existe": None,
}


def _fila(usuario_id: str, rol: str, drogueria_id: str | None) -> dict:
    return {
        "id": usuario_id,
        "drogueria_id": drogueria_id,
        "rol": rol,
        "activo": True,
        "username": usuario_id,
        "debe_cambiar_password": False,
    }


@pytest.fixture
def almacen(monkeypatch) -> dict[str, dict]:
    filas: dict[str, dict] = {}

    def _actualizar(usuario_id, **campos):
        filas[usuario_id] = {**filas[usuario_id], **campos}
        return filas[usuario_id]

    monkeypatch.setattr(repo, "obtener_usuario", lambda client, *, usuario_id: filas.get(usuario_id))
    monkeypatch.setattr(
        repo,
        "actualizar_activo",
        lambda client, *, usuario_id, activo: _actualizar(usuario_id, activo=activo),
    )
    monkeypatch.setattr(
        repo,
        "actualizar_perfil",
        lambda client, *, usuario_id, campos: _actualizar(usuario_id, **campos),
    )
    monkeypatch.setattr(repo, "actualizar_password_auth", lambda client, *, usuario_id, password: None)
    return filas


def _resultado(funcion) -> type[Exception] | None:
    try:
        funcion()
    except Exception as exc:  # noqa: BLE001 -- se compara el tipo
        return type(exc)
    return None


@pytest.mark.parametrize("objetivo", list(OBJETIVOS))
@pytest.mark.parametrize("rol", ROLES_CREADOR)
def test_blanqueo_y_activo_tienen_la_misma_autorizacion(almacen, rol, objetivo):
    drogueria = None if rol == "superadmin" else DROGUERIA
    creador = UsuarioPerfil(id="yo", drogueria_id=drogueria, rol=rol)
    almacen["yo"] = _fila("yo", rol, drogueria)
    for usuario_id, datos in OBJETIVOS.items():
        if datos is not None:
            almacen[usuario_id] = _fila(usuario_id, *datos)

    blanqueo = _resultado(
        lambda: service.blanquear_password(
            None, creador=creador, usuario_id=objetivo, password="temporal2"
        )
    )
    activo = _resultado(
        lambda: service.cambiar_activo(None, creador=creador, usuario_id=objetivo, activo=False)
    )

    assert blanqueo is activo
