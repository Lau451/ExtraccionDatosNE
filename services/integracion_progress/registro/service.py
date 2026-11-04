"""Registro de archivos intercambiados con Progress (odd/tasks/integracion-progress.md S3).

Todo archivo que entra o sale queda en progress_archivos. El mismo contenido
(SHA-256 de los bytes crudos, por droguería, sentido y tipo) nunca se procesa dos
veces: la garantía la da uq_parch_contenido (0043), no el lookup previo, así que
una carrera entre la recepción automática y la manual se resuelve releyendo la
fila ganadora tras el 23505.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any

from postgrest.exceptions import APIError
from supabase import Client

from services.integracion_progress.registro import repository as repo
from services.integracion_progress.registro.models import (
    ErrorLinea,
    EstadoArchivo,
    Origen,
    RegistroArchivo,
    Sentido,
)
from services.shared.exceptions import ConflictError, NotFoundError, ValidationError

_UNIQUE_VIOLATION = "23505"
_ORIGENES = ("carpeta", "manual")
_LIMITE_MAXIMO = 500
# Reintentos del CAS por `intentos` de marcar_error antes de rendirse.
_REINTENTOS_CAS = 3


def _sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validar_texto(nombre: str, valor: str) -> None:
    if not valor or not valor.strip():
        raise ValidationError(f"'{nombre}' no puede estar vacío")


def _insertar_o_releer(
    client: Client, fila: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Inserta `fila`; si otro proceso ganó la carrera (23505 sobre
    uq_parch_contenido) devuelve la fila existente. El bool indica si insertó."""
    try:
        return repo.insertar(client, fila), True
    except APIError as exc:
        if exc.code != _UNIQUE_VIOLATION:
            raise
    existente = repo.buscar_por_contenido(
        client,
        drogueria_id=fila["drogueria_id"],
        sentido=fila["sentido"],
        tipo=fila["tipo"],
        sha256=fila["sha256"],
    )
    if existente is None:
        # 23505 sin fila visible: la ganadora se borró entre medio. No se
        # reintenta en silencio para no ocultar el caso.
        raise ConflictError(
            f"El archivo '{fila['nombre_archivo']}' chocó con un registro que ya no existe"
        )
    return existente, False


def registrar_entrada(
    client: Client,
    *,
    drogueria_id: str,
    tipo: str,
    nombre_archivo: str,
    contenido: bytes,
    origen: Origen,
    usuario_id: str,
) -> tuple[RegistroArchivo, bool]:
    """Registra un archivo recibido. Devuelve (registro, es_duplicado).

    - Contenido nuevo: inserta en estado 'recibido' (es_duplicado=False).
    - Mismo contenido ya 'recibido' o 'procesado': lo devuelve con
      es_duplicado=True y no escribe nada.
    - Mismo contenido en 'error': lo devuelve con es_duplicado=False para que el
      llamador lo reprocese; tampoco escribe nada.
    """
    if origen not in _ORIGENES:
        raise ValidationError(f"Origen inválido '{origen}': debe ser carpeta o manual")
    _validar_texto("tipo", tipo)
    _validar_texto("nombre_archivo", nombre_archivo)

    sha256 = _sha256(contenido)
    existente = repo.buscar_por_contenido(
        client, drogueria_id=drogueria_id, sentido="entrada", tipo=tipo, sha256=sha256
    )
    if existente is None:
        existente, insertado = _insertar_o_releer(
            client,
            {
                "drogueria_id": drogueria_id,
                "sentido": "entrada",
                "tipo": tipo,
                "nombre_archivo": nombre_archivo,
                "sha256": sha256,
                "origen": origen,
                "estado": "recibido",
                "usuario_id": usuario_id,
            },
        )
        if insertado:
            return RegistroArchivo.model_validate(existente), False

    registro = RegistroArchivo.model_validate(existente)
    return registro, registro.estado != "error"


def registrar_salida(
    client: Client,
    *,
    drogueria_id: str,
    tipo: str,
    nombre_archivo: str,
    contenido: bytes,
    usuario_id: str,
    filas: int | None = None,
) -> RegistroArchivo:
    """Registra un archivo ya escrito en la carpeta de Progress. Nace 'procesado'
    y sin origen (ck_parch_origen). Si el mismo contenido ya estaba registrado,
    devuelve ese registro sin escribir."""
    _validar_texto("tipo", tipo)
    _validar_texto("nombre_archivo", nombre_archivo)

    sha256 = _sha256(contenido)
    existente = repo.buscar_por_contenido(
        client, drogueria_id=drogueria_id, sentido="salida", tipo=tipo, sha256=sha256
    )
    if existente is None:
        existente, _ = _insertar_o_releer(
            client,
            {
                "drogueria_id": drogueria_id,
                "sentido": "salida",
                "tipo": tipo,
                "nombre_archivo": nombre_archivo,
                "sha256": sha256,
                "origen": None,
                "estado": "procesado",
                "filas": filas,
                "usuario_id": usuario_id,
                "procesado_at": _ahora(),
            },
        )
    return RegistroArchivo.model_validate(existente)


def marcar_procesado(client: Client, *, registro_id: str, filas: int) -> RegistroArchivo:
    """Cierra el registro como 'procesado'. Limpia los errores del intento anterior;
    `intentos` conserva cuántas veces falló antes."""
    if filas < 0:
        raise ValidationError("'filas' no puede ser negativo")
    fila = repo.actualizar(
        client,
        registro_id=registro_id,
        campos={"estado": "procesado", "filas": filas, "errores": None, "procesado_at": _ahora()},
    )
    if fila is None:
        raise NotFoundError(f"No se encontró el registro de archivo '{registro_id}'")
    return RegistroArchivo.model_validate(fila)


def marcar_error(
    client: Client, *, registro_id: str, errores: list[ErrorLinea | dict[str, Any]]
) -> RegistroArchivo:
    """Marca el registro en 'error', guarda los errores por línea y suma un intento.

    El incremento es un CAS sobre `intentos` (leer, actualizar solo si no cambió),
    para que dos fallos concurrentes no pisen el conteo."""
    errores_json = [ErrorLinea.model_validate(e).model_dump() for e in errores]
    for _ in range(_REINTENTOS_CAS):
        actual = repo.buscar_por_id(client, registro_id=registro_id)
        if actual is None:
            raise NotFoundError(f"No se encontró el registro de archivo '{registro_id}'")
        fila = repo.actualizar(
            client,
            registro_id=registro_id,
            campos={
                "estado": "error",
                "errores": errores_json,
                "intentos": actual["intentos"] + 1,
                "procesado_at": None,
            },
            intentos_esperados=actual["intentos"],
        )
        if fila is not None:
            return RegistroArchivo.model_validate(fila)
    raise ConflictError(
        f"El registro de archivo '{registro_id}' cambió mientras se marcaba el error"
    )


def listar(
    client: Client,
    *,
    drogueria_id: str,
    sentido: Sentido | None = None,
    estado: EstadoArchivo | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[RegistroArchivo]:
    if not 1 <= limit <= _LIMITE_MAXIMO:
        raise ValidationError(f"'limit' debe estar entre 1 y {_LIMITE_MAXIMO}")
    if offset < 0:
        raise ValidationError("'offset' no puede ser negativo")
    filas = repo.listar(
        client,
        drogueria_id=drogueria_id,
        sentido=sentido,
        estado=estado,
        limit=limit,
        offset=offset,
    )
    return [RegistroArchivo.model_validate(f) for f in filas]
