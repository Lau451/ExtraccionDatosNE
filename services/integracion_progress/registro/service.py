"""Registro de archivos intercambiados con Progress (odd/tasks/integracion-progress.md S3).

Todo archivo que entra o sale queda en progress_archivos. El mismo contenido
(SHA-256 de los bytes crudos, por droguería, sentido y tipo) nunca se procesa dos
veces: la garantía la da uq_parch_contenido (0043), no el lookup previo, así que
una carrera entre la recepción automática y la manual se resuelve releyendo la
fila ganadora tras el 23505.
"""

import hashlib
from datetime import datetime, timedelta, timezone
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
from services.shared.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

_UNIQUE_VIOLATION = "23505"
_ORIGENES = ("carpeta", "manual")
_LIMITE_MAXIMO = 500
# Reintentos del CAS por `intentos` de marcar_error antes de rendirse.
_REINTENTOS_CAS = 3
# Un registro que sigue en 'recibido' más de este tiempo sin actualizarse quedó
# colgado (el proceso que lo estaba procesando murió): la próxima llegada del mismo
# contenido lo reprocesa en lugar de reportarlo como duplicado. Procesar un archivo
# normal tarda segundos; una hora deja margen para archivos grandes sin pisar a un
# proceso vivo. Reprocesar reclama el registro con un CAS (`repo.reclamar`), así
# que de dos llegadas simultáneas solo una lo reprocesa y la otra es duplicado.
_RECIBIDO_COLGADO = timedelta(hours=1)


def _sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validar_texto(nombre: str, valor: str) -> None:
    if not valor or not valor.strip():
        raise ValidationError(f"'{nombre}' no puede estar vacío")


def _validar_filas(filas: int | None) -> None:
    if filas is not None and filas < 0:
        raise ValidationError("'filas' no puede ser negativo")


def _no_esta_en_curso(
    client: Client, *, drogueria_id: str, registro_id: str
) -> DomainError:
    """Error para un cierre que no actualizó nada: el registro no existe en la
    droguería o ya no está en 'recibido' (otro proceso lo cerró)."""
    actual = repo.buscar_por_id(client, drogueria_id=drogueria_id, registro_id=registro_id)
    if actual is None:
        return NotFoundError(f"No se encontró el registro de archivo '{registro_id}'")
    return ConflictError(
        f"El registro de archivo '{registro_id}' no está en curso (estado {actual['estado']})"
    )


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
    - Mismo contenido ya 'procesado', o 'recibido' hace menos de
      `_RECIBIDO_COLGADO` (otro proceso lo está procesando): lo devuelve con
      es_duplicado=True y no escribe nada.
    - Mismo contenido en 'error', o 'recibido' sin actualizarse desde hace más de
      `_RECIBIDO_COLGADO`: lo reclama (vuelve a 'recibido', renovando updated_at)
      y lo devuelve con es_duplicado=False para que el llamador lo reprocese. Si
      otro proceso lo reclamó primero, devuelve el registro actual como duplicado.
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
    if not _reprocesable(registro):
        return registro, True
    reclamado = repo.reclamar(
        client,
        drogueria_id=drogueria_id,
        registro_id=registro.id,
        estado_esperado=registro.estado,
        updated_at_esperado=registro.updated_at,
    )
    if reclamado is not None:
        return RegistroArchivo.model_validate(reclamado), False
    actual = repo.buscar_por_id(client, drogueria_id=drogueria_id, registro_id=registro.id)
    if actual is None:
        raise ConflictError(
            f"El archivo '{nombre_archivo}' chocó con un registro que ya no existe"
        )
    return RegistroArchivo.model_validate(actual), True


def buscar_entrada(
    client: Client, *, drogueria_id: str, tipo: str, contenido: bytes
) -> RegistroArchivo | None:
    """Registro de entrada de este contenido, o None si nunca se registró."""
    fila = repo.buscar_por_contenido(
        client, drogueria_id=drogueria_id, sentido="entrada", tipo=tipo, sha256=_sha256(contenido)
    )
    return RegistroArchivo.model_validate(fila) if fila else None


def _reprocesable(registro: RegistroArchivo) -> bool:
    if registro.estado == "error":
        return True
    return (
        registro.estado == "recibido"
        and datetime.now(timezone.utc) - registro.updated_at > _RECIBIDO_COLGADO
    )


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
    _validar_filas(filas)

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


def marcar_procesado(
    client: Client, *, drogueria_id: str, registro_id: str, filas: int
) -> RegistroArchivo:
    """Cierra como 'procesado' un registro en curso ('recibido'). Limpia los errores
    del intento anterior; `intentos` conserva cuántas veces falló antes. Un registro
    que ya se cerró no se toca (ConflictError)."""
    if filas < 0:
        raise ValidationError("'filas' no puede ser negativo")
    fila = repo.actualizar(
        client,
        drogueria_id=drogueria_id,
        registro_id=registro_id,
        campos={"estado": "procesado", "filas": filas, "errores": None, "procesado_at": _ahora()},
        estado_esperado="recibido",
    )
    if fila is None:
        raise _no_esta_en_curso(client, drogueria_id=drogueria_id, registro_id=registro_id)
    return RegistroArchivo.model_validate(fila)


def marcar_error(
    client: Client,
    *,
    drogueria_id: str,
    registro_id: str,
    errores: list[ErrorLinea | dict[str, Any]],
) -> RegistroArchivo:
    """Marca en 'error' un registro en curso ('recibido'), guarda los errores por
    línea y suma un intento. Un registro que ya se cerró no se toca (ConflictError).

    El incremento es un CAS sobre `estado` e `intentos` (leer, actualizar solo si no
    cambiaron), para que dos fallos concurrentes no pisen el conteo."""
    errores_json = [ErrorLinea.model_validate(e).model_dump() for e in errores]
    for _ in range(_REINTENTOS_CAS):
        actual = repo.buscar_por_id(client, drogueria_id=drogueria_id, registro_id=registro_id)
        if actual is None:
            raise NotFoundError(f"No se encontró el registro de archivo '{registro_id}'")
        if actual["estado"] != "recibido":
            raise ConflictError(
                f"El registro de archivo '{registro_id}' no está en curso "
                f"(estado {actual['estado']})"
            )
        fila = repo.actualizar(
            client,
            drogueria_id=drogueria_id,
            registro_id=registro_id,
            campos={
                "estado": "error",
                "errores": errores_json,
                "intentos": actual["intentos"] + 1,
                "procesado_at": None,
            },
            estado_esperado="recibido",
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
